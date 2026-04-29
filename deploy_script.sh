#!/bin/bash
# deploy_script.sh — Econest Adaptive Canary Traffic Controller

set -e

TRAFFIC=${1:-0}
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
API_URL="http://127.0.0.1:5001/api/update"

# ── Function to send updates to dashboard ─────────────────────────────
send_update() {
    curl -s -X POST $API_URL \
        -H "Content-Type: application/json" \
        -d "{\"traffic\": \"$TRAFFIC\", \"stage\": \"$1\", \"message\": \"$2\", \"time\": \"$TIMESTAMP\"}" > /dev/null || true
}

# ── Validate input ───────────────────────────────────────────────────
if [[ ! "$TRAFFIC" =~ ^(0|10|50|100)$ ]]; then
    echo "❌ ERROR: Invalid traffic value '$TRAFFIC'."
    exit 1
fi

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  ECONEST ADAPTIVE CANARY — TRAFFIC CONTROLLER"
echo "  Timestamp : $TIMESTAMP"
echo "  Target    : ${TRAFFIC}%"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo $TRAFFIC > /tmp/econest_traffic_weight


# ── Route logic ──────────────────────────────────────────────────────
if [ "$TRAFFIC" -eq 0 ]; then

    send_update "ROLLBACK" "Rollback initiated"

    echo "🔴 ROLLBACK MODE — Routing 0% traffic to canary version."
    sleep 1

    send_update "ROLLBACK" "Restoring stable system"


    echo "   → Restoring stable baseline..."
    if [ -f /tmp/econest_8002.pid ]; then kill -9 $(cat /tmp/econest_8002.pid) 2>/dev/null || true; fi
    sleep 1

    send_update "ROLLBACK" "Rollback complete"

    echo "✅ Rollback complete."

elif [ "$TRAFFIC" -eq 10 ]; then

    send_update "CANARY_START" "Starting 10% canary"

    echo "🟡 CANARY PHASE — Initiating 10% traffic shift."
    sleep 1

    send_update "CANARY_PROGRESS" "10% traffic routing"

    echo "   → Configuring load balancer: 90/10"
    sleep 1

    send_update "CANARY_ACTIVE" "Canary live at 10%"

    echo "✅ Canary live at 10%."

elif [ "$TRAFFIC" -eq 50 ]; then

    send_update "PROMOTE_START" "Promoting to 50%"

    echo "🟠 PROMOTE PHASE — Shifting to 50% traffic."
    sleep 1

    send_update "PROMOTE_PROGRESS" "50% traffic split"

    echo "   → Updating load balancer: 50/50"
    sleep 1

    send_update "PROMOTE_DONE" "Stable at 50%"

    echo "✅ Traffic split at 50/50."

elif [ "$TRAFFIC" -eq 100 ]; then

    send_update "FINAL_START" "Full rollout started"

    echo "🟢 FULL ROLLOUT — Promoting to 100%."
    sleep 1

    send_update "FINAL_PROGRESS" "100% traffic routing"


    echo "   → Updating load balancer: 100% canary"
    if [ -f /tmp/econest_8001.pid ]; then kill -9 $(cat /tmp/econest_8001.pid) 2>/dev/null || true; fi
    sleep 1

    send_update "FINAL_DONE" "Deployment complete"

    echo "✅ Deployment complete."

fi

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  Traffic shift to ${TRAFFIC}% — COMPLETE"
echo "════════════════════════════════════════════════════════════════"
echo ""

exit 0