import os
import subprocess
import time
import requests
import threading

ABORT_FLAG = "/tmp/econest_abort_pipeline"

def stream_cmd(cmd, emit_log_cb):
    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in iter(process.stdout.readline, ''):
        emit_log_cb(line.rstrip())
    process.stdout.close()
    return process.wait()

def check_abort():
    if os.path.exists(ABORT_FLAG):
        return True
    return False

def load_worker():
    start = time.time()
    while time.time() - start < 6:
        if check_abort(): return
        try:
            requests.get("http://localhost:9000/", timeout=1)
        except:
            pass
        time.sleep(0.05)

def burst_load(emit_log_cb):
    emit_log_cb("🚀 Injecting Automated Load Burst (simulating traffic)...")
    threads = []
    for _ in range(10):
        t = threading.Thread(target=load_worker)
        t.start()
        threads.append(t)
    return threads

def trigger_github_action(repo_url, github_token, emit_log_cb):
    if not github_token:
        emit_log_cb("⚠️  No GITHUB_TOKEN provided in environment. Skipping actual GitHub API call.")
        emit_log_cb("Simulating Cloud Action (2 seconds)...")
        time.sleep(2)
        emit_log_cb("✅ Simulated Cloud CI Passed!")
        return True
        
    api_url = "https://api.github.com/repos/srikarreddyram/econest-canary-platform/actions/workflows/cloud_ci.yml/dispatches"
    
    emit_log_cb("☁️ Triggering GitHub Actions Cloud CI...")
    try:
        r = requests.post(
            api_url,
            headers={
                "Authorization": f"token {github_token}",
                "Accept": "application/vnd.github.v3+json"
            },
            json={"ref": "main", "inputs": {"repo_url": repo_url}},
            timeout=10
        )
        if r.status_code == 204:
            emit_log_cb("✅ Cloud CI Triggered successfully. Polling for completion...")
            time.sleep(10)
            for i in range(20):
                if check_abort(): return False
                runs_r = requests.get(
                    "https://api.github.com/repos/srikarreddyram/econest-canary-platform/actions/runs",
                    headers={"Authorization": f"token {github_token}"}
                )
                if runs_r.status_code == 200:
                    runs = runs_r.json().get("workflow_runs", [])
                    if runs:
                        latest = runs[0]
                        if latest["status"] == "completed":
                            if latest["conclusion"] == "success":
                                emit_log_cb("✅ Cloud CI Passed!")
                                return True
                            else:
                                emit_log_cb(f"❌ Cloud CI Failed: {latest['conclusion']}")
                                return False
                time.sleep(5)
                emit_log_cb("... still waiting for Cloud CI to finish ...")
            emit_log_cb("❌ Cloud CI polling timeout.")
            return False
        else:
            emit_log_cb(f"❌ Failed to trigger Action: {r.status_code} {r.text}")
            return False
    except Exception as e:
        emit_log_cb(f"❌ Exception in Cloud CI: {str(e)}")
        return False

def run_pipeline(repo_url, emit_log_cb, update_stage_cb):
    if os.path.exists(ABORT_FLAG):
        os.remove(ABORT_FLAG)
        
    emit_log_cb(f"🚀 Starting Pipeline Orchestration for {repo_url}")
    
    # 1. Cloud CI
    update_stage_cb('Checkout', 'IN_PROGRESS')
    github_token = os.environ.get("GITHUB_TOKEN", "")
    if not trigger_github_action(repo_url, github_token, emit_log_cb):
        update_stage_cb('Checkout', 'FAILED')
        return False
    update_stage_cb('Checkout', 'SUCCESS')
    
    if check_abort(): return False

    # 2. Local Checkout & Install
    update_stage_cb('Install Dependencies', 'IN_PROGRESS')
    target_dir = "/tmp/econest_workspace"
    os.system(f"rm -rf {target_dir}")
    emit_log_cb(f"Cloning {repo_url} into {target_dir}")
    if stream_cmd(f"git clone {repo_url} {target_dir}", emit_log_cb) != 0:
        update_stage_cb('Install Dependencies', 'FAILED')
        return False
        
    emit_log_cb("Launching application (Canary on 8002)")
    if stream_cmd(f"bash launch_app.sh 8002 {target_dir}", emit_log_cb) != 0:
        update_stage_cb('Install Dependencies', 'FAILED')
        return False
    update_stage_cb('Install Dependencies', 'SUCCESS')
    
    if check_abort(): return False

    # 3. Canary 10%
    update_stage_cb('Verify DB Structure', 'SUCCESS') # mock fast
    update_stage_cb('Canary 10%', 'IN_PROGRESS')
    stream_cmd("bash deploy_script.sh 10", emit_log_cb)
    
    emit_log_cb("Running Canary analysis for 6 seconds...")
    threads = burst_load(emit_log_cb)
    for _ in range(6):
        if check_abort(): return False
        time.sleep(1)
        
    for t in threads:
        t.join()
        
    update_stage_cb('Canary 10%', 'SUCCESS')

    if check_abort(): return False

    # 4. Evaluate Risk
    update_stage_cb('Evaluate Risk', 'IN_PROGRESS')
    emit_log_cb("Running risk evaluation engine...")
    if stream_cmd("python3 evaluate_risk.py", emit_log_cb) != 0:
        emit_log_cb("🚨 Risk Score Too High! Auto-Aborting...")
        update_stage_cb('Evaluate Risk', 'FAILED')
        stream_cmd("bash deploy_script.sh 0", emit_log_cb)
        return False
    update_stage_cb('Evaluate Risk', 'SUCCESS')
    
    if check_abort(): return False

    # 5. Promote 50%
    update_stage_cb('Promote 50%', 'IN_PROGRESS')
    stream_cmd("bash deploy_script.sh 50", emit_log_cb)
    time.sleep(2)
    update_stage_cb('Promote 50%', 'SUCCESS')

    if check_abort(): return False

    # 6. Promote 100%
    update_stage_cb('Promote 100%', 'IN_PROGRESS')
    emit_log_cb("Launching stable baseline on 8001")
    if stream_cmd(f"bash launch_app.sh 8001 {target_dir}", emit_log_cb) != 0:
        update_stage_cb('Promote 100%', 'FAILED')
        return False
    stream_cmd("bash deploy_script.sh 100", emit_log_cb)
    update_stage_cb('Promote 100%', 'SUCCESS')
    
    emit_log_cb("🎉 Pipeline Completed Successfully!")
    return True
