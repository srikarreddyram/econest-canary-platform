"""
Econest Canary Platform — Backend API (V3 with WebSockets)
Bridges the React dashboard to Jenkins + MLflow local tracking.
Run with: python3 Api.py
Listens on: http://localhost:5001
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO
import requests
import os
import glob
import time
from datetime import datetime
import sqlite3
import threading

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# ── Config ───────────────────────────────────────────────────────────────────
JENKINS_URL = "http://localhost:8080"
JOB_NAME = "Adaptive-Canary-Core"

USERNAME = os.environ.get("JENKINS_USER", "tejsr")
API_TOKEN = os.environ.get("JENKINS_TOKEN", "")

MLRUNS_PATHS = [
    "/Users/tejsr/.jenkins/workspace/Adaptive-Canary-Core/mlruns",
    os.path.expanduser("~/mlruns"),
    "./mlruns",
]

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

# ── Jenkins Auth Helpers ──────────────────────────────────────────────────────
def get_crumb():
    try:
        r = requests.get(
            f"{JENKINS_URL}/crumbIssuer/api/json",
            auth=(USERNAME, API_TOKEN),
            timeout=5
        )
        if r.status_code == 200:
            data = r.json()
            return {data["crumbRequestField"]: data["crumb"]}
    except Exception:
        pass
    return {}

def jenkins_request(method, url, **kwargs):
    headers = kwargs.pop("headers", {})
    headers.update(get_crumb())

    return requests.request(
        method,
        url,
        auth=(USERNAME, API_TOKEN),
        headers=headers,
        timeout=10,
        **kwargs
    )

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

                p_dir = os.path.join(run_dir, "params")
                if os.path.isdir(p_dir):
                    for pf in glob.glob(f"{p_dir}/*"):
                        try:
                            with open(pf) as f:
                                run["params"][os.path.basename(pf)] = f.read().strip()
                        except:
                            pass

                if run["metrics"]:
                    runs.append(run)

        if runs:
            break

    return runs

# ── Jenkins Helpers ───────────────────────────────────────────────────────────
def jenkins_stages():
    try:
        r = jenkins_request(
            "GET",
            f"{JENKINS_URL}/job/{JOB_NAME}/lastBuild/wfapi/describe"
        )
        if r.status_code == 200:
            return r.json().get("stages", [])
    except:
        pass
    return []

# ── Routes ───────────────────────────────────────────────────────────────────
@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/api/deploy", methods=["POST"])
def deploy():
    body = request.get_json(silent=True) or {}
    repo_url = body.get("repo_url", "").strip() or \
        "https://github.com/srikarreddyram/econest-canary-platform.git"

    try:
        r = jenkins_request(
            "POST",
            f"{JENKINS_URL}/job/{JOB_NAME}/buildWithParameters",
            params={"REPO_URL": repo_url}
        )

        if r.status_code in (200, 201):
            entry_id = str(int(time.time()))
            triggered = datetime.utcnow().isoformat()
            insert_deployment(entry_id, repo_url, triggered, "running")
            socketio.emit('refresh', {'type': 'history'})
            return jsonify({"success": True})

        return jsonify({"success": False, "message": f"Jenkins {r.status_code}"}), 500

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/status")
def status():
    # Still available for manual polling if needed, but background thread emits via WS
    return jsonify(get_status_data())

def get_status_data():
    try:
        r = jenkins_request(
            "GET",
            f"{JENKINS_URL}/job/{JOB_NAME}/lastBuild/api/json"
        )

        if r.status_code == 200:
            d = r.json()
            result = d.get("result")
            building = d.get("building", False)

            deps = get_deployments()
            if deps:
                latest_id = deps[0]["id"]
                new_status = (
                    "running" if building else
                    "success" if result == "SUCCESS" else "failed"
                )
                if deps[0]["status"] != new_status:
                    update_deployment_status(latest_id, new_status)
                    socketio.emit('refresh', {'type': 'history'})

            return {
                "building": building,
                "result": result,
                "number": d.get("number"),
                "stages": jenkins_stages(),
            }
    except Exception:
        pass
    return None

@app.route("/api/metrics")
def metrics():
    return jsonify(read_mlflow_metrics())

@app.route("/api/history")
def history():
    return jsonify(get_deployments())

@app.route("/api/rollback", methods=["POST"])
def rollback():
    try:
        jenkins_request(
            "POST",
            f"{JENKINS_URL}/job/{JOB_NAME}/buildWithParameters",
            params={"FORCE_ROLLBACK": "true"}
        )
        socketio.emit('refresh', {'type': 'history'})
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/console")
def console():
    try:
        r = jenkins_request(
            "GET",
            f"{JENKINS_URL}/job/{JOB_NAME}/lastBuild/consoleText"
        )
        if r.status_code == 200:
            lines = r.text.splitlines()
            return jsonify({"log": "\n".join(lines[-200:])})
    except:
        pass
    return jsonify({"log": ""})

@app.route("/api/update", methods=["POST"])
def update():
    """Receive live deployment stage updates from deploy_script.sh"""
    data = request.get_json(silent=True) or {}
    print(f"📡 Stage update: {data.get('stage')} → {data.get('message')}")
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
    payload = request.get_json(silent=True) or {}
    if payload.get("ref") == "refs/heads/main":
        repo_url = payload.get("repository", {}).get("clone_url")
        if repo_url:
            try:
                r = jenkins_request(
                    "POST",
                    f"{JENKINS_URL}/job/{JOB_NAME}/buildWithParameters",
                    params={"REPO_URL": repo_url}
                )
                if r.status_code in (200, 201):
                    entry_id = str(int(time.time()))
                    triggered = datetime.utcnow().isoformat()
                    insert_deployment(entry_id, repo_url, triggered, "running")
                    socketio.emit('refresh', {'type': 'history'})
                    return jsonify({"success": True, "message": "Triggered via Webhook"})
            except Exception as e:
                return jsonify({"success": False, "message": str(e)}), 500
    return jsonify({"status": "ignored"})

# ── Background Polling for WebSocket Emit ─────────────────────────────────────
def background_poll():
    while True:
        socketio.sleep(3)
        status_data = get_status_data()
        if status_data:
            socketio.emit('status', status_data)
        
        metrics_data = read_mlflow_metrics()
        if metrics_data:
            socketio.emit('metrics', metrics_data)

        try:
            r = jenkins_request("GET", f"{JENKINS_URL}/job/{JOB_NAME}/lastBuild/consoleText")
            if r.status_code == 200:
                lines = r.text.splitlines()
                socketio.emit('console', {"log": "\n".join(lines[-200:])})
        except:
            pass

@socketio.on('connect')
def handle_connect():
    print("Client connected via WebSocket")

# ── Entry ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("🚀 Econest Canary API running on http://localhost:5001")
    socketio.start_background_task(background_poll)
    socketio.run(app, port=5001, debug=False, allow_unsafe_werkzeug=True)