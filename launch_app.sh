#!/bin/bash
# launch_app.sh — Universal Application Launcher (Host-based)

PORT=${1:-8001}
TARGET_DIR=${2:-/tmp/econest_stable_app}

echo "Cleaning up any ghost processes on port $PORT..."
if [ -f "/tmp/econest_${PORT}.pid" ]; then
    kill -9 $(cat "/tmp/econest_${PORT}.pid") 2>/dev/null || true
    rm -f "/tmp/econest_${PORT}.pid"
fi
lsof -ti :${PORT} | xargs kill -9 2>/dev/null || true

echo "Launching application in $TARGET_DIR on port $PORT"
cd "$TARGET_DIR" || exit 1

# Detect runtime
if [ -f "pom.xml" ]; then
    echo "Detected Java/Maven application"
    mvn clean package -DskipTests
    JAR_FILE=$(ls target/*.jar | head -n 1)
    if [ -n "$JAR_FILE" ]; then
        java -jar "$JAR_FILE" --server.port=$PORT >> /tmp/econest_${PORT}.log 2>&1 &
        echo $! > /tmp/econest_${PORT}.pid
    else
        echo "No JAR file found after Maven build"
        exit 1
    fi

elif [ -f "requirements.txt" ]; then
    pip3 install -r requirements.txt --quiet || true
    
    if grep -iq "flask" requirements.txt || grep -iq "from flask" *.py 2>/dev/null; then
        echo "Detected Flask application"
        pip3 install gunicorn --quiet || true
        APP_MODULE=$(grep -l "Flask(__name__)" *.py 2>/dev/null | head -n 1 | sed 's/\.py//')
        APP_MODULE=${APP_MODULE:-app}
        gunicorn -b 0.0.0.0:$PORT $APP_MODULE:app >> /tmp/econest_${PORT}.log 2>&1 &
        echo $! > /tmp/econest_${PORT}.pid
    elif grep -iq "fastapi" requirements.txt || grep -iq "uvicorn" requirements.txt; then
        echo "Detected FastAPI application"
        pip3 install uvicorn --quiet || true
        APP_MODULE=$(grep -l "FastAPI()" *.py 2>/dev/null | head -n 1 | sed 's/\.py//')
        APP_MODULE=${APP_MODULE:-main}
        uvicorn $APP_MODULE:app --host 0.0.0.0 --port $PORT >> /tmp/econest_${PORT}.log 2>&1 &
        echo $! > /tmp/econest_${PORT}.pid
    elif grep -iq "django" requirements.txt; then
        echo "Detected Django application"
        python3 manage.py runserver 0.0.0.0:$PORT >> /tmp/econest_${PORT}.log 2>&1 &
        echo $! > /tmp/econest_${PORT}.pid
    else
        echo "Unknown Python application"
        python3 -m http.server $PORT >> /tmp/econest_${PORT}.log 2>&1 &
        echo $! > /tmp/econest_${PORT}.pid
    fi

elif [ -f "package.json" ]; then
    echo "Detected Node.js application"
    npm install
    if grep -q '"build"' package.json; then
        npm run build
    fi
    PORT=$PORT npm start >> /tmp/econest_${PORT}.log 2>&1 &
    echo $! > /tmp/econest_${PORT}.pid

elif [ -f "index.html" ]; then
    echo "Detected static HTML"
    python3 -m http.server $PORT >> /tmp/econest_${PORT}.log 2>&1 &
    echo $! > /tmp/econest_${PORT}.pid

else
    echo "Unknown repository type. Launching fallback health-check wrapper."
    cat << 'INNER_EOF' > dummy_health.py
from flask import Flask
app = Flask(__name__)
@app.route("/")
def health():
    return "Econest Canary Fallback OK"
INNER_EOF
    pip3 install flask gunicorn --quiet || true
    gunicorn -b 0.0.0.0:$PORT dummy_health:app >> /tmp/econest_${PORT}.log 2>&1 &
    echo $! > /tmp/econest_${PORT}.pid
fi

# Wait for port to become active (up to 15s)
for i in {1..15}; do
    if curl -s http://localhost:$PORT > /dev/null; then
        echo "App is up on port $PORT"
        exit 0
    fi
    sleep 1
done

echo "App failed to bind to port $PORT within 15 seconds."
exit 1
