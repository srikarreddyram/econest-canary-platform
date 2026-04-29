import http.server
import socketserver
import urllib.request
import json
import random
import time
import os
from http import HTTPStatus
import http.cookies

PORT = 9000
WEIGHT_FILE = '/tmp/econest_traffic_weight'
METRICS_FILE = '/tmp/econest_proxy_metrics.json'
CHAOS_FILE = '/tmp/econest_chaos_mode'

metrics_history = []

class ProxyHandler(http.server.BaseHTTPRequestHandler):
    def do_request(self):
        start_time = time.time()
        
        try:
            with open(WEIGHT_FILE, 'r') as f:
                weight = int(f.read().strip())
        except:
            weight = 0
            
        try:
            with open(CHAOS_FILE, 'r') as f:
                chaos_mode = f.read().strip() == "1"
        except:
            chaos_mode = False
            
        target = "stable"
        
        cookies = http.cookies.SimpleCookie(self.headers.get('Cookie'))
        cohort_cookie = cookies.get('Econest-Cohort')
        set_cookie = False
        
        if cohort_cookie:
            if cohort_cookie.value == "canary" and weight > 0:
                target = "canary"
            else:
                target = "stable"
        else:
            if weight > 0 and random.randint(1, 100) <= weight:
                target = "canary"
            else:
                target = "stable"
            set_cookie = True
            
        target_port = 8002 if target == "canary" else 8001
        
        if self.path == '/__econest/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "canary_weight": weight}).encode())
            return
            
        if self.path == '/__econest/metrics':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            try:
                with open(METRICS_FILE, 'r') as f:
                    self.wfile.write(f.read().encode())
            except:
                self.wfile.write(json.dumps([]).encode())
            return

        url = f"http://127.0.0.1:{target_port}{self.path}"
        req = urllib.request.Request(url, method=self.command)
        
        for k, v in self.headers.items():
            if k.lower() not in ['host', 'connection']:
                req.add_header(k, v)
                
        if 'Content-Length' in self.headers:
            length = int(self.headers['Content-Length'])
            req.data = self.rfile.read(length)
            
        status_code = 502
        response_headers = []
        response_body = b"Bad Gateway"
        
        # Inject Chaos only for Canary
        if chaos_mode and target == "canary":
            time.sleep(random.uniform(0.3, 0.8)) # Artificial latency 300-800ms
            if random.random() < 0.15: # 15% error rate
                status_code = 500
                response_body = b"Chaos Error"
                chaos_error = True
            else:
                chaos_error = False
        else:
            chaos_error = False

        if not chaos_error:
            try:
                with urllib.request.urlopen(req, timeout=10) as response:
                    status_code = response.status
                    response_headers = response.getheaders()
                    response_body = response.read()
            except urllib.error.HTTPError as e:
                status_code = e.code
                response_headers = e.headers.items()
                response_body = e.read()
            except Exception as e:
                status_code = 502
                response_body = b"Bad Gateway"
            
        latency = (time.time() - start_time) * 1000
        
        self.send_response(status_code)
        for k, v in response_headers:
            if k.lower() not in ['transfer-encoding']:
                self.send_header(k, v)
        self.send_header('X-Econest-Target', target)
        self.send_header('X-Econest-Latency', f"{latency:.2f}")
        if set_cookie:
            self.send_header('Set-Cookie', f"Econest-Cohort={target}; Path=/; HttpOnly; Max-Age=3600")
        self.end_headers()
        self.wfile.write(response_body)
        
        metrics_history.append({
            "target": target,
            "latency_ms": latency,
            "status_code": status_code,
            "timestamp": time.time()
        })
        
        while len(metrics_history) > 100:
            metrics_history.pop(0)
            
        with open(METRICS_FILE, 'w') as f:
            json.dump(metrics_history, f)

    def do_GET(self): self.do_request()
    def do_POST(self): self.do_request()
    def do_PUT(self): self.do_request()
    def do_DELETE(self): self.do_request()
    def do_PATCH(self): self.do_request()
    def do_HEAD(self): self.do_request()

class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    pass

if __name__ == '__main__':
    with open(WEIGHT_FILE, 'w') as f:
        f.write("0")
    with open(CHAOS_FILE, 'w') as f:
        f.write("0")
    server = ThreadedHTTPServer(('0.0.0.0', PORT), ProxyHandler)
    print(f"Proxy listening on port {PORT}")
    server.serve_forever()
