#!/bin/sh
set -eu
if [ -n "${HUGGINGFACE_API_KEY:-}" ] && [ -z "${HF_TOKEN:-}" ]; then
    export HF_TOKEN="$HUGGINGFACE_API_KEY"
fi
exec /opt/llama.cpp/build/bin/llama-server "$@"
