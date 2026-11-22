#!/bin/sh
# WORKER_MODE=queue (default): Runpod queue-based Serverless worker (handler.py)
# WORKER_MODE=http: OpenAI-compatible HTTP server for load-balancing endpoints / Pods (server.py)
set -e
cd /app
if [ "${WORKER_MODE:-queue}" = "http" ]; then
  exec python -u server.py
fi
exec python -u handler.py
