import sys
import random
import mlflow

# Point to your local MLflow server
mlflow.set_tracking_uri("http://localhost:5000")

def evaluate_telemetry():
    with mlflow.start_run(run_name="Canary_Risk_Evaluation"):
        latency_p95 = random.uniform(50.0, 150.0) 
        error_rate = random.uniform(0.0, 0.05)
        
        mlflow.log_metric("latency_p95", latency_p95)
        mlflow.log_metric("error_rate", error_rate)
        
        print(f"Evaluated Latency: {latency_p95:.2f}ms | Error Rate: {error_rate:.3f}")
        
        if latency_p95 > 130.0 or error_rate > 0.04:
            mlflow.log_param("decision", "ABORT")
            print("HIGH RISK DETECTED. Recommending Rollback.")
            return 1 
        else:
            mlflow.log_param("decision", "PROMOTE")
            print("Risk Score LOW. Safe to promote.")
            return 0 

if __name__ == "__main__":
    sys.exit(evaluate_telemetry())