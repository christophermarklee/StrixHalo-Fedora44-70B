#!/bin/sh
set -eu

volume=${MODEL_VOLUME:-deepseek-v4-flash-models}
model=DeepSeek-V4-Flash-IQ2XXS-w2Q2K-AProjQ8-SExpQ8-OutQ8-chat-v2-imatrix.gguf
mtp=DeepSeek-V4-Flash-MTP-Q4K-Q8_0-F32.gguf

podman volume inspect "$volume" >/dev/null 2>&1 || podman volume create "$volume" >/dev/null
podman run --rm --network pasta:--ipv4-only \
    -v "$volume:/models" \
    docker.io/library/python:3.12-slim \
    sh -c "python -m pip install --no-cache-dir 'huggingface_hub[hf_xet]==2.1.1' && HF_XET_HIGH_PERFORMANCE=1 hf download antirez/deepseek-v4-gguf '$model' '$mtp' --local-dir /models"
