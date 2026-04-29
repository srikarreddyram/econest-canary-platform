import time
import random
import threading
import requests

PROXY_URL = "http://localhost:9000/"

def generate_traffic():
    while True:
        try:
            time.sleep(random.uniform(0.1, 0.5))
            # Don't maintain session so we generate varied cohort tracking
            requests.get(PROXY_URL, timeout=5)
            print(".", end="", flush=True)
        except Exception:
            print("x", end="", flush=True)

if __name__ == "__main__":
    print(f"Starting background traffic generator to {PROXY_URL}...")
    threads = []
    # 5 concurrent users
    for i in range(5):
        t = threading.Thread(target=generate_traffic, daemon=True)
        t.start()
        threads.append(t)
        
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping traffic generator.")
