#!/usr/bin/env bash
set -euo pipefail

model_dir=/models/MTP
model_file=mtp-Qwen3.8-27B-Q4_0.gguf
model_path="$model_dir/$model_file"
partial_path="$model_path.partial"
model_url="https://huggingface.co/unsloth/Qwen3.8-27B-GGUF/resolve/main/MTP/$model_file"

mkdir -p "$model_dir"
if [[ -s "$model_path" ]]; then
    printf 'MTP draft model already present: %s\n' "$model_path"
    exit 0
fi

curl_options=(-fL --retry 5 --retry-all-errors --continue-at - --output "$partial_path")
if [[ -n "${HUGGINGFACE_API_KEY:-}" ]]; then
    printf 'Authorization: Bearer %s\n' "$HUGGINGFACE_API_KEY" |
        curl "${curl_options[@]}" --header @- "$model_url"
else
    curl "${curl_options[@]}" "$model_url"
fi
mv "$partial_path" "$model_path"
printf 'Downloaded MTP draft model: %s\n' "$model_path"
