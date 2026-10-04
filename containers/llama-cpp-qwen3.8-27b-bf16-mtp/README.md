# Qwen3.8-27B BF16 with MTP on the GMKtec EVO-X2

This Podman project serves Unsloth's [Qwen3.8-27B GGUF](https://huggingface.co/unsloth/Qwen3.8-27B-GGUF) in BF16 and enables its separate MTP draft GGUF, following [Unsloth's Qwen3.8 guidance](https://unsloth.ai/docs/models/qwen3.8) and [MTP guide](https://unsloth.ai/docs/models/mtp). It builds llama.cpp `b11390` against AMD ROCm `7.14.1-full` for the Radeon 8060S (`gfx1151`). Fedora supplies the kernel driver; AMD Container Runtime Toolkit CDI supplies container GPU access.

Unsloth lists the BF16 target at about 56 GB and recommends another 1–2 GB of memory headroom for MTP. The target is split across two BF16 GGUF shards, and the repo has a separate 1.37 GB Q4_0 MTP file. This host's 96 GiB GPU reservation has room for the target, MTP draft, projector, and a moderate context. Begin at 8192 context; increase it after checking memory use.

## Build and prepare the MTP draft

From the repository root:

```sh
podman build --format docker -t llama-cpp-qwen3.8-27b-bf16-mtp \
  -f containers/llama-cpp-qwen3.8-27b-bf16-mtp/Dockerfile \
  containers/llama-cpp-qwen3.8-27b-bf16-mtp
podman volume create qwen3.8-27b-bf16-mtp-model
```

Download the MTP draft inside a container to the named volume:

```sh
podman run --rm --env-file .env \
  -v qwen3.8-27b-bf16-mtp-model:/models \
  --entrypoint /usr/local/bin/download-mtp \
  localhost/llama-cpp-qwen3.8-27b-bf16-mtp:latest
```

The script resumes `.partial` downloads and leaves the completed 1.37 GB draft at `/models/MTP/mtp-Qwen3.8-27B-Q4_0.gguf`. If the public download does not need the root `.env` token, omit `--env-file .env`.

## Run with MTP

The first server start downloads the BF16 target and its multimodal projector from Hugging Face. `LLAMA_CACHE=/models` places those downloads in the same persistent Podman volume. The entrypoint maps `HUGGINGFACE_API_KEY` from `.env` to llama.cpp's `HF_TOKEN` when supplied. `.env` is optional for this public model; omit `--env-file .env` from the command if the file is absent.

```sh
podman run -d --name qwen3.8-27b-bf16-mtp \
  --device amd.com/gpu=all --group-add keep-groups \
  -p 127.0.0.1:8080:8080 \
  --env-file .env \
  -v qwen3.8-27b-bf16-mtp-model:/models \
  localhost/llama-cpp-qwen3.8-27b-bf16-mtp:latest \
  -hf unsloth/Qwen3.8-27B-GGUF:BF16 \
  --model-draft /models/MTP/mtp-Qwen3.8-27B-Q4_0.gguf \
  --spec-type draft-mtp --spec-draft-n-max 2 \
  -ngl 99 -fa on --threads 8 -c 8192 \
  --temp 1.0 --top-p 0.95 --top-k 20 --min-p 0.0 \
  --host 0.0.0.0 --port 8080
```

This uses llama.cpp's `llama-server` executable with the requested `-hf unsloth/Qwen3.8-27B-GGUF:BF16` target and adds the separate draft-model flags for MTP. The server's `-hf` option automatically fetches an available multimodal projector. The HF target download, projector, and separately downloaded MTP file all persist in `qwen3.8-27b-bf16-mtp-model` under Podman storage. The first target download is about 55–56 GB, plus about 1.37 GB for the MTP file and about 0.93 GB for the projector. See [llama.cpp server options](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md) for the `-hf`, `--model-draft`, and speculative decoding flags.

Check model loading and the local API:

```sh
podman logs -f qwen3.8-27b-bf16-mtp
curl -fsS http://127.0.0.1:8080/health
curl -fsS -H 'Content-Type: application/json' \
  -d '{"model":"unsloth/Qwen3.8-27B-GGUF:BF16","messages":[{"role":"user","content":"What is 2 + 2? Reply with only the number."}],"max_tokens":64,"stream":false}' \
  http://127.0.0.1:8080/v1/chat/completions
```

Stop and remove the serving container without deleting its model volume:

```sh
podman stop qwen3.8-27b-bf16-mtp
podman rm qwen3.8-27b-bf16-mtp
```

## Notes and limits

- `--spec-draft-n-max 2` follows Unsloth's recommended starting point; test values 1–6 on this GPU to compare speed. MTP needs extra memory and may not improve throughput for every prompt.
- The image explicitly enables llama.cpp Flash Attention and compiles HIP for `gfx1151`. It leaves `GGML_CUDA_ENABLE_UNIFIED_MEMORY` unset so HIP uses GPU VRAM allocations rather than the much smaller GTT path observed on this host.
- The build includes OpenSSL development headers and sets `LLAMA_OPENSSL=ON`; llama.cpp needs this backend for `-hf` to resolve Hugging Face over HTTPS.
- The model supports image and video input, and the HF server path automatically downloads the repo's `mmproj-BF16.gguf` when available. This project has not yet been built or run on the target host; the first build, BF16 model load, MTP acceptance rate, and speed remain to be verified.
- The project uses CDI. If model loading hits the same Fedora ROCm `Memory in use` failure observed with Strata and the 32B model, retry with `--security-opt label=disable` after confirming SELinux is the cause.
