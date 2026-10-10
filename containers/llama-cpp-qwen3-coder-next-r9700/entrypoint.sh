#!/usr/bin/env bash
set -euo pipefail

unset GGML_CUDA_ENABLE_UNIFIED_MEMORY
if [[ $# -eq 0 ]]; then
    exec /opt/llama.cpp/build/bin/llama-server \
        --model /models/Qwen3-Coder-Next-Q4_K_M.gguf \
        --alias qwen3-coder-next \
        --host 0.0.0.0 --port 8080 \
        --n-gpu-layers 99 --cpu-moe \
        --ctx-size 4096 --parallel 1 --threads 8 \
        --batch-size 256 --ubatch-size 128 \
        --flash-attn on --jinja \
        --temp 1.0 --top-p 0.95 --top-k 40
fi
exec /opt/llama.cpp/build/bin/llama-server "$@"
