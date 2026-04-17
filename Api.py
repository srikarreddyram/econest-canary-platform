"""
Econest Canary Platform — Backend API
Bridges the React dashboard to Jenkins + MLflow local tracking.
Run with: python3 api.py
Listens on: http://localhost:5001
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
import os
import glob
import time
import json
from datetime import datetime

app = Flask(__name__)
CORS(app)

# ── Config ───────────────────────────────────────────────────────────────────
JENKINS_URL  = "http://localhost:8080"
JOB_NAME     = "Adaptive-Canary-Core"
MLRUNS_PATHS = [
    "/Users/tejsr/.jenkins/workspace/Adaptive-Canary-Core/mlruns",
    os.path.expanduser("~/mlruns"),
    "./mlruns",
]

# In-memory deployment log (survives the API session)
_history = []


# ── Helpers ───────────────────────────────────────────────────────────────────
def jenkins_crumb():
    """Fetch Jenkins CSRF crumb (returns {} if Jenkins has CSRF disabled)."""
    try:
        r = requests.get(f"{JENKINS_URL}/crumbIssuer/api/json", timeout=5)
        if r.status_code == 200:
            d = r.json()
            return {d["crumbRequestField"]: d["crumb"]}
    except Exception:
        pass
    return {}


def read_mlflow_metrics():
    """Parse local mlruns directory tree and return list of run dicts."""
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
                    "run_id":    os.path.basename(run_dir),
                    "exp_id":    os.path.basename(exp_dir),
                    "metrics":   {},
                    "params":    {},
                    "timestamp": None,
                }
                # Read metrics
                m_dir = os.path.join(run_dir, "metrics")
                if os.path.isdir(m_dir):
                    for mf in glob.glob(f"{m_dir}/*"):
                        key = os.path.basename(mf)
                        try:
                            with open(mf) as f:
                                parts = f.read().strip().split()
                                # MLflow metric file format: <timestamp> <value> <step>
                                if len(parts) >= 2:
                                    run["metrics"][key] = float(parts[1])
                                    if run["timestamp"] is None:
                                        run["timestamp"] = int(parts[0])
                        except Exception:
                            pass
                # Read params
                p_dir = os.path.join(run_dir, "params")
                if os.path.isdir(p_dir):
                    for pf in glob.glob(f"{p_dir}/*"):
                        key = os.path.basename(pf)
                        try:
                            with open(pf) as f:
                                run["params"][key] = f.read().strip()
                        except Exception:
                            pass
                if run["metrics"]:
                    runs.append(run)
        if runs:
            break   # Use first path that has data
    return runs


def jenkins_stages():
    """Pull stage data from Jenkins Pipeline workflow API."""
    try:
        r = requests.get(
            f"{JENKINS_URL}/job/{JOB_NAME}/lastBuild/wfapi/describe",
            timeout=5,
        )
        if r.status_code == 200:
            return r.json().get("stages", [])
    except Exception:
        pass
    return []


# ── Routes ───────────────────────────────────────────────────────────────────
@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "time": datetime.utcnow().isoformat()})


@app.route("/api/deploy", methods=["POST"])
def deploy():
    """Trigger a Jenkins build. Accepts optional repo_url in JSON body."""
    body     = request.get_json(silent=True) or {}
    repo_url = body.get("repo_url", "").strip() or \
               "https://github.com/srikarreddyram/econest-canary-platform.git"

    crumb = jenkins_crumb()
    try:
        r = requests.post(
            f"{JENKINS_URL}/job/{JOB_NAME}/buildWithParameters",
            params={"REPO_URL": repo_url},
            headers=crumb,
            timeout=10,
        )
        if r.status_code in (200, 201):
            entry = {
                "id":        str(int(time.time())),
                "repo_url":  repo_url,
                "triggered": datetime.utcnow().isoformat(),
                "status":    "running",
            }
            _history.insert(0, entry)
            return jsonify({"success": True, "entry": entry})
        return jsonify({"success": False,
                        "message": f"Jenkins HTTP {r.status_code}"}), 502
    except requests.exceptions.ConnectionError:
        return jsonify({"success": False,
                        "message": "Cannot reach Jenkins on localhost:8080"}), 503
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/status")
def status():
    """Return current build status + stage breakdown."""
    try:
        r = requests.get(
            f"{JENKINS_URL}/job/{JOB_NAME}/lastBuild/api/json",
            timeout=5,
        )
        if r.status_code == 200:
            d = r.json()
            result   = d.get("result")
            building = d.get("building", False)

            # Sync history entry
            if _history:
                _history[0]["status"] = (
                    "running" if building else
                    "success" if result == "SUCCESS" else "failed"
                )

            return jsonify({
                "building":  building,
                "result":    result,
                "number":    d.get("number"),
                "timestamp": d.get("timestamp"),
                "duration":  d.get("duration"),
                "stages":    jenkins_stages(),
            })
        return jsonify({"error": f"Jenkins HTTP {r.status_code}"}), r.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Jenkins unreachable"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/metrics")
def metrics():
    """Return MLflow run metrics from local mlruns store."""
    try:
        return jsonify(read_mlflow_metrics())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/history")
def history():
    """Return in-memory deployment history for this API session."""
    return jsonify(_history)


@app.route("/api/rollback", methods=["POST"])
def rollback():
    """Trigger deploy_script.sh 0 via a new Jenkins build."""
    crumb = jenkins_crumb()
    try:
        r = requests.post(
            f"{JENKINS_URL}/job/{JOB_NAME}/buildWithParameters",
            params={"REPO_URL": "ROLLBACK", "FORCE_ROLLBACK": "true"},
            headers=crumb,
            timeout=10,
        )
        entry = {
            "id":        str(int(time.time())),
            "repo_url":  "ROLLBACK",
            "triggered": datetime.utcnow().isoformat(),
            "status":    "running",
        }
        _history.insert(0, entry)
        return jsonify({"success": True, "message": "Rollback build triggered"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/console")
def console():
    """Tail the last 200 lines of the Jenkins console log."""
    try:
        r = requests.get(
            f"{JENKINS_URL}/job/{JOB_NAME}/lastBuild/consoleText",
            timeout=5,
        )
        if r.status_code == 200:
            lines = r.text.splitlines()
            return jsonify({"log": "\n".join(lines[-200:])})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"log": ""})


# ── Entry ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("🚀 Econest Canary API running on http://localhost:5001")
    app.run(port=5001, debug=False)