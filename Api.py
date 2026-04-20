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
from datetime import datetime

app = Flask(__name__)
CORS(app)

# ── Config ───────────────────────────────────────────────────────────────────
JENKINS_URL = "http://localhost:8080"
JOB_NAME = "Adaptive-Canary-Core"

# 🔐 ADD YOUR CREDS HERE
USERNAME = "tejsr"
API_TOKEN = "11c622dcc660bb45b95d7d0d882b1b8b5f"

MLRUNS_PATHS = [
    "/Users/tejsr/.jenkins/workspace/Adaptive-Canary-Core/mlruns",
    os.path.expanduser("~/mlruns"),
    "./mlruns",
]

_history = []


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
    """Wrapper to ALWAYS include auth + crumb"""
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
            entry = {
                "id": str(int(time.time())),
                "repo_url": repo_url,
                "triggered": datetime.utcnow().isoformat(),
                "status": "running",
            }
            _history.insert(0, entry)
            return jsonify({"success": True})

        return jsonify({"success": False, "message": f"Jenkins {r.status_code}"}), 500

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/status")
def status():
    try:
        r = jenkins_request(
            "GET",
            f"{JENKINS_URL}/job/{JOB_NAME}/lastBuild/api/json"
        )

        if r.status_code == 200:
            d = r.json()

            result = d.get("result")
            building = d.get("building", False)

            if _history:
                _history[0]["status"] = (
                    "running" if building else
                    "success" if result == "SUCCESS" else "failed"
                )

            return jsonify({
                "building": building,
                "result": result,
                "number": d.get("number"),
                "stages": jenkins_stages(),
            })

        return jsonify({"error": "Failed"}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/metrics")
def metrics():
    return jsonify(read_mlflow_metrics())


@app.route("/api/history")
def history():
    return jsonify(_history)


@app.route("/api/rollback", methods=["POST"])
def rollback():
    try:
        jenkins_request(
            "POST",
            f"{JENKINS_URL}/job/{JOB_NAME}/buildWithParameters",
            params={"FORCE_ROLLBACK": "true"}
        )
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


# ── Entry ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("🚀 Econest Canary API running on http://localhost:5001")
    app.run(port=5001, debug=False)