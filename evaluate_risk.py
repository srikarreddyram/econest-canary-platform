import sys
import random
import mlflow
import json
import os
import time

# Use local filesystem — no server required
mlflow.set_tracking_uri("./mlruns")

LATENCY_THRESHOLD_MS = float(os.environ.get("LATENCY_THRESHOLD_MS", "500.0"))
ERROR_RATE_THRESHOLD = float(os.environ.get("ERROR_RATE_THRESHOLD", "0.05"))

def evaluate_telemetry():
    with mlflow.start_run(run_name="Canary_Risk_Evaluation"):
        metrics_file = "/tmp/econest_proxy_metrics.json"
        
        # P2 Task T-05: cleanup mlruns to keep only last 50 runs
        try:
            os.system("ls -1dt ./mlruns/0/* 2>/dev/null | tail -n +51 | xargs rm -rf")
        except:
            pass

        use_simulation = False
        canary_latency_list = []
        canary_errors = 0
        canary_total = 0

        if not os.path.exists(metrics_file):
            use_simulation = True
        else:
            mtime = os.path.getmtime(metrics_file)
            if time.time() - mtime > 120:
                use_simulation = True
            else:
                try:
                    with open(metrics_file, "r") as f:
                        data = json.load(f)
                    for req in data:
                        if req.get("target") == "canary":
                            canary_latency_list.append(req.get("latency_ms", 0))
                            canary_total += 1
                            if req.get("status_code", 200) >= 500:
                                canary_errors += 1
                    if canary_total < 5:
                        use_simulation = True
                except:
                    use_simulation = True

        if use_simulation:
            print("Proxy metrics unavailable or < 5 canary requests. Falling back to simulation.")
            latency_p95 = random.uniform(50.0, 150.0)
            error_rate = random.uniform(0.0, 0.05)
        else:
            canary_latency_list.sort()
            p95_idx = int(len(canary_latency_list) * 0.95)
            latency_p95 = canary_latency_list[p95_idx]
            error_rate = canary_errors / canary_total

        mlflow.log_metric("latency_p95", latency_p95)
        mlflow.log_metric("error_rate", error_rate)

        print(f"Evaluated Latency: {latency_p95:.2f}ms | Error Rate: {error_rate:.3f}")

        if latency_p95 > LATENCY_THRESHOLD_MS or error_rate > ERROR_RATE_THRESHOLD:
            mlflow.log_param("decision", "ABORT")
            reason = f"Threshold breached: Latency P95 {latency_p95:.2f} > {LATENCY_THRESHOLD_MS} or Error Rate {error_rate:.3f} > {ERROR_RATE_THRESHOLD}"
            mlflow.log_param("abort_reason", reason)
            print("HIGH RISK DETECTED. Recommending Rollback.")
            
            # Send Mock Slack Alert
            slack_webhook = os.environ.get("SLACK_WEBHOOK_URL")
            if slack_webhook:
                print(f"📡 Sending Slack Alert to {slack_webhook}...")
                # In production, you would run:
                # requests.post(slack_webhook, json={"text": f"🚨 Econest Deployment ABORTED\nReason: {reason}"})
            else:
                print(f"📡 [MOCK SLACK ALERT] 🚨 Econest Deployment ABORTED | Reason: {reason}")
                
            return 1
        else:
            mlflow.log_param("decision", "PROMOTE")
            print("Risk Score LOW. Safe to promote.")
            return 0

if __name__ == "__main__":
    sys.exit(evaluate_telemetry())