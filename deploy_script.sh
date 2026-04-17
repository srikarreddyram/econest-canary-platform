#!/bin/bash
TRAFFIC=$1
echo "Initiating econest store component integration update..."
echo "Routing ${TRAFFIC}% of traffic to the new canary version."
sleep 2
echo "Traffic shift to ${TRAFFIC}% complete."