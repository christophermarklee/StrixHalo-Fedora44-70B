#!/usr/bin/env bash
set -euo pipefail

: "${MODEL_FILE:?MODEL_FILE must be set}"
: "${MODEL_URL:?MODEL_URL must be set}"

mkdir -p /models
model_path="/models/$MODEL_FILE"
partial_path="$model_path.partial"

if [[ -s "$model_path" ]]; then
    printf 'Model already present: %s\n' "$model_path"
    exit 0
fi

curl_options=(-fL --retry 5 --retry-all-errors --continue-at -
    --output "$partial_path")
if [[ -n "${HUGGINGFACE_API_KEY:-}" ]]; then
    printf 'Authorization: Bearer %s\n' "$HUGGINGFACE_API_KEY" |
        curl "${curl_options[@]}" --header @- "$MODEL_URL"
else
    curl "${curl_options[@]}" "$MODEL_URL"
fi
mv "$partial_path" "$model_path"
printf 'Downloaded model: %s\n' "$model_path"
