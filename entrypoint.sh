#!/bin/sh

# Exit immediately if a command exits with a non-zero status
set -e

# Calculate workers based on CPU cores, default to 2*cores + 1
CPU_CORES=$(nproc)
DEFAULT_WORKERS=$((2 * CPU_CORES + 1))

# Use WORKERS env var if set, otherwise use the calculated default
WORKERS=${WORKERS:-$DEFAULT_WORKERS}

# Start the FastAPI server
echo "🚀 Starting FastAPI server with $WORKERS workers..."
exec gunicorn app.main:app \
    --workers $WORKERS --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000