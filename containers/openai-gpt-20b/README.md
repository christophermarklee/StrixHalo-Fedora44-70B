# OpenAI GPT-OSS-20B MXFP4 with llama.cpp HIP

This project serves OpenAI's [GPT-OSS-20B](https://huggingface.co/openai/gpt-oss-20b) using the MXFP4 GGUF published by [ggml-org](https://huggingface.co/ggml-org/gpt-oss-20b-GGUF). The image builds llama.cpp release `b11390` against AMD ROCm `7.14.1-full` for the GMKtec EVO-X2's Radeon 8060S (`gfx1151`). Fedora supplies the kernel driver; AMD Container Runtime Toolkit CDI provides GPU access to Podman.

The model download is about 12.1 GB. The image contains no weights; a named Podman volume stores the model separately from the image.

## Build and download

From the repository root:

```sh
podman build --format docker -t openai-gpt-20b \
  -f containers/openai-gpt-20b/Dockerfile \
  containers/openai-gpt-20b
podman volume create openai-gpt-20b-model
podman run --rm -v openai-gpt-20b-model:/models \
  --entrypoint /usr/local/bin/download-model \
  localhost/openai-gpt-20b:latest
```

The downloader resumes an interrupted `.partial` file and skips a completed download. Hugging Face serves this model publicly, so no token or `.env` file is required. Keep the named volume when rebuilding the image to avoid downloading the model again.

## Check GPU and serve locally

Check the CDI device name with `amd-ctk cdi list`, then confirm that the container sees the Radeon 8060S:

```sh
podman run --rm --device amd.com/gpu=all --group-add keep-groups \
  localhost/openai-gpt-20b:latest --list-devices
```

Start the OpenAI-compatible server on host loopback. The initial run uses the downloaded model from the persistent volume:

```sh
podman run -d --name openai-gpt-20b \
  --device amd.com/gpu=all --group-add keep-groups \
  --unsetenv GGML_CUDA_ENABLE_UNIFIED_MEMORY \
  -v openai-gpt-20b-model:/models:ro \
  -p 127.0.0.1:8080:8080 \
  --entrypoint /opt/llama.cpp/build/bin/llama-server \
  localhost/openai-gpt-20b:latest \
  -m /models/gpt-oss-20b-MXFP4.gguf \
  -ngl 99 -fa on --jinja --threads 8 -c 8192 \
  --host 0.0.0.0 --port 8080
```

`--jinja` enables the model's chat template. Check server health and make a short inference request:

```sh
curl -fsS http://127.0.0.1:8080/health
curl -fsS -H 'Content-Type: application/json' \
  -d '{"model":"gpt-oss-20b-MXFP4.gguf","messages":[{"role":"user","content":"What is 2 + 2? Reply with only the number."}],"max_tokens":64,"stream":false}' \
  http://127.0.0.1:8080/v1/chat/completions
```

The API is bound to loopback and has no API-key protection. Do not publish it to other machines without adding API-key protection. Stop the server without deleting the model volume with `podman stop openai-gpt-20b && podman rm openai-gpt-20b`.

## Hardware notes and limits

- ROCm `7.14.1-full` is pinned, and HIP is compiled explicitly for `gfx1151`; Fedora's host `amdgpu`/KFD driver is shared with the container. The model's MXFP4 weights are about 12.1 GB, leaving room in the host's 96 GiB GPU allocation for inference buffers and KV cache. This README starts with an 8192-token context; larger contexts consume more GPU memory.
- Rootless Podman may need membership in the host `render` and `video` groups; `--group-add keep-groups` passes supplementary group access through. Keep Fedora SELinux labeling enabled by default. If a model-load or device-access failure is observed, retry with `--security-opt label=disable`; this relaxes SELinux isolation for the container.
- If the host's CDI spec uses a different device name, replace `amd.com/gpu=all` with the name shown by `amd-ctk cdi list`.
- The image and GPT-OSS-20B model have not been built or loaded on the target host as part of this change. Inference quality, performance, context limits, and long-running stability remain unverified.
