"""
Econest Canary Platform — Backend API (V4 - Cloud Hybrid Orchestrator)
Bridges the React dashboard to GitHub Actions + Local Native Orchestrator.
Run with: python3 Api.py
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO
import os
from dotenv import load_dotenv
load_dotenv()
import glob
import time
from datetime import datetime
import sqlite3
import threading

import orchestrator

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

MLRUNS_PATHS = [
    os.path.expanduser("~/mlruns"),
    "./mlruns",
]

pipeline_state = {
    "building": False,
    "result": None,
    "number": 0,
    "stages": [
        {"name": "Checkout", "status": "PENDING"},
        {"name": "Install Dependencies", "status": "PENDING"},
        {"name": "Verify DB Structure", "status": "PENDING"},
        {"name": "Canary 10%", "status": "PENDING"},
        {"name": "Evaluate Risk", "status": "PENDING"},
        {"name": "Promote 50%", "status": "PENDING"},
        {"name": "Promote 100%", "status": "PENDING"}
    ]
}

console_logs = []

# ── DB Setup ──────────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect('deployments.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS deployments
                 (id TEXT PRIMARY KEY, repo_url TEXT, triggered TEXT, status TEXT)''')
    conn.commit()
    conn.close()

init_db()

def insert_deployment(id, repo_url, triggered, status):
    conn = sqlite3.connect('deployments.db')
    c = conn.cursor()
    c.execute("INSERT INTO deployments (id, repo_url, triggered, status) VALUES (?, ?, ?, ?)",
              (id, repo_url, triggered, status))
    conn.commit()
    conn.close()

def update_deployment_status(id, status):
    conn = sqlite3.connect('deployments.db')
    c = conn.cursor()
    c.execute("UPDATE deployments SET status = ? WHERE id = ?", (status, id))
    conn.commit()
    conn.close()

def get_deployments():
    conn = sqlite3.connect('deployments.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM deployments ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return [{"id": r["id"], "repo_url": r["repo_url"], "triggered": r["triggered"], "status": r["status"]} for r in rows]

# ── MLflow ────────────────────────────────────────────────────────────────────
def read_mlflow_metrics():
    runs = []
    for base in MLRUNS_PATHS:
        if not os.path.isdir(base):
            continue
        for exp_dir in sorted(glob.glob(f"{base}/*")):
            if not os.path.isdir(exp_dir):
                continue
            for run_dir in sorted(glob.glob(f"{exp_dir}/*"), reverse=True):
                if not os.path.isdir(run_dir):
                    continue

                run = {
                    "run_id": os.path.basename(run_dir),
                    "metrics": {},
                    "params": {},
                    "timestamp": None,
                }

                m_dir = os.path.join(run_dir, "metrics")
                if os.path.isdir(m_dir):
                    for mf in glob.glob(f"{m_dir}/*"):
                        try:
                            with open(mf) as f:
                                parts = f.read().strip().split()
                                if len(parts) >= 2:
                                    run["metrics"][os.path.basename(mf)] = float(parts[1])
                                    if run["timestamp"] is None:
                                        run["timestamp"] = int(parts[0])
                        except:
                            pass

                if run["metrics"]:
                    runs.append(run)
        if runs:
            break
    return runs

# ── Pipeline Callbacks ────────────────────────────────────────────────────────
def emit_log(msg):
    print(msg)
    console_logs.append(msg)
    if len(console_logs) > 200:
        console_logs.pop(0)
    socketio.emit('console', {"log": "\n".join(console_logs)})

def update_stage(stage_name, status):
    for s in pipeline_state["stages"]:
        if s["name"] == stage_name:
            s["status"] = status
    socketio.emit('status', pipeline_state)

def pipeline_thread(repo_url, entry_id):
    pipeline_state["building"] = True
    pipeline_state["result"] = None
    for s in pipeline_state["stages"]:
        s["status"] = "PENDING"
    
    socketio.emit('status', pipeline_state)
    socketio.emit('refresh', {'type': 'history'})
    
    success = orchestrator.run_pipeline(repo_url, emit_log, update_stage)
    
    pipeline_state["building"] = False
    pipeline_state["result"] = "SUCCESS" if success else "FAILED"
    update_deployment_status(entry_id, "success" if success else "failed")
    
    socketio.emit('status', pipeline_state)
    socketio.emit('refresh', {'type': 'history'})

# ── Routes ───────────────────────────────────────────────────────────────────
@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/api/deploy", methods=["POST"])
def deploy():
    if pipeline_state["building"]:
        return jsonify({"success": False, "message": "Pipeline already running"}), 400
        
    body = request.get_json(silent=True) or {}
    repo_url = body.get("repo_url", "").strip() or \
        "https://github.com/srikarreddyram/econest-canary-platform.git"

    pipeline_state["number"] += 1
    console_logs.clear()
    emit_log(f"Received deployment request for {repo_url}")
    
    entry_id = str(int(time.time()))
    triggered = datetime.utcnow().isoformat()
    insert_deployment(entry_id, repo_url, triggered, "running")
    
    # Start Orchestrator Thread
    threading.Thread(target=pipeline_thread, args=(repo_url, entry_id), daemon=True).start()

    return jsonify({"success": True})

@app.route("/api/history")
def history():
    return jsonify(get_deployments())

@app.route("/api/rollback", methods=["POST"])
def rollback():
    with open(orchestrator.ABORT_FLAG, "w") as f:
        f.write("1")
    emit_log("🛑 Manual Rollback Triggered!")
    return jsonify({"success": True})

@app.route("/api/update", methods=["POST"])
def update():
    data = request.get_json(silent=True) or {}
    socketio.emit('stage_update', data)
    return jsonify({"status": "received"})

CHAOS_FILE = '/tmp/econest_chaos_mode'

@app.route("/api/chaos/toggle", methods=["POST"])
def toggle_chaos():
    try:
        with open(CHAOS_FILE, 'r') as f:
            current = f.read().strip() == "1"
    except:
        current = False
    new_state = not current
    with open(CHAOS_FILE, 'w') as f:
        f.write("1" if new_state else "0")
    socketio.emit('chaos_status', {"chaos_mode": new_state})
    return jsonify({"chaos_mode": new_state})

@app.route("/api/chaos/status")
def chaos_status():
    try:
        with open(CHAOS_FILE, 'r') as f:
            current = f.read().strip() == "1"
    except:
        current = False
    return jsonify({"chaos_mode": current})

@app.route("/api/webhook/github", methods=["POST"])
def github_webhook():
    if pipeline_state["building"]:
        return jsonify({"status": "ignored", "message": "already running"})
        
    payload = request.get_json(silent=True) or {}
    if payload.get("ref") == "refs/heads/main":
        repo_url = payload.get("repository", {}).get("clone_url")
        if repo_url:
            pipeline_state["number"] += 1
            console_logs.clear()
            entry_id = str(int(time.time()))
            triggered = datetime.utcnow().isoformat()
            insert_deployment(entry_id, repo_url, triggered, "running")
            threading.Thread(target=pipeline_thread, args=(repo_url, entry_id), daemon=True).start()
            return jsonify({"success": True, "message": "Triggered via Webhook"})
    return jsonify({"status": "ignored"})

# ── Background Polling for WebSocket Emit ─────────────────────────────────────
def background_poll():
    while True:
        socketio.sleep(3)
        # Emit state and metrics continuously
        socketio.emit('status', pipeline_state)
        metrics_data = read_mlflow_metrics()
        if metrics_data:
            socketio.emit('metrics', metrics_data)

@socketio.on('connect')
def handle_connect():
    socketio.emit('status', pipeline_state)
    socketio.emit('console', {"log": "\n".join(console_logs)})

if __name__ == "__main__":
    print("🚀 Econest Native API & Orchestrator running on http://localhost:5001")
    socketio.start_background_task(background_poll)
    socketio.run(app, port=5001, debug=False, allow_unsafe_werkzeug=True)