#!/usr/bin/env bash

# ==============================================================================
# llama-server launch script for mle-agent
# Model: Qwen2.5-Coder-32B-Instruct GGUF
# Zero-download policy: Requires local model path via LOCAL_MODEL_PATH env var.
# ==============================================================================

set -e

if [ -z "$LOCAL_MODEL_PATH" ]; then
    echo "====================================================================="
    echo "[ERROR] LOCAL_MODEL_PATH environment variable is not set."
    echo "Please set LOCAL_MODEL_PATH to point to your local GGUF weight file."
    echo "Example: export LOCAL_MODEL_PATH=\"/path/to/qwen2.5-coder-32b-instruct-q4_k_m.gguf\""
    echo "Note: Automatic model downloading is strictly disabled."
    echo "====================================================================="
    exit 1
fi

if [ ! -f "$LOCAL_MODEL_PATH" ]; then
    echo "====================================================================="
    echo "[ERROR] Specified model file does not exist at: $LOCAL_MODEL_PATH"
    echo "Please verify the file path and try again."
    echo "====================================================================="
    exit 1
fi

N_GPU_LAYERS="${N_GPU_LAYERS:-999}"
CTX_SIZE="${CTX_SIZE:-8192}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

echo "[launch_llama_server] Starting llama-server with GGUF weights..."
echo "  Model Path:    $LOCAL_MODEL_PATH"
echo "  GPU Offload:   --n-gpu-layers $N_GPU_LAYERS"
echo "  Context Size:  --ctx-size $CTX_SIZE"
echo "  Host/Port:     $HOST:$PORT"

exec ./llama-server \
  -m "$LOCAL_MODEL_PATH" \
  --n-gpu-layers "$N_GPU_LAYERS" \
  --ctx-size "$CTX_SIZE" \
  --host "$HOST" \
  --port "$PORT"
