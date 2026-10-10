# Qwen3-Coder-Next on Radeon AI PRO R9700 / 64 GB DDR5

This project targets **one AMD Radeon AI PRO R9700, 32 GB dedicated VRAM,
`gfx1201` (RDNA 4), and 64 GB host DDR5**, running Fedora 44 and Podman.
Unlike the repository's Strix Halo machine, these are separate memory pools.
This image is not a `gfx1151` build.

## Versions and model updates

- Runtime: [llama.cpp commit `8345f333951c661d166b00e6f9362e553768f292`](https://github.com/ggml-org/llama.cpp/commit/8345f333951c661d166b00e6f9362e553768f292),
  from October 5, 2026, immediately after v0.6.0. This pins the source
  commit, not the release tag (which points to a different commit).
- User space: `docker.io/rocm/dev-ubuntu-24.04:7.2.3-complete`.
  The Dockerfile also pins its verified manifest digest
  `sha256:ec1b59bf75ec1122e7a091c0be82301ba12458b038499ef96a5c115876bd78d2`.
  [AMD's Radeon compatibility matrix](https://rocm.docs.amd.com/projects/radeon-ryzen/en/latest/docs/compatibility/compatibilityrad/linux/linux_compatibility.html)
  lists the R9700 as `gfx1201`. The build explicitly targets that architecture.
  The pinned llama.cpp HIP backend accepts CMake HIP architectures, classifies
  GFX12 as RDNA 4, and includes the Qwen3Next hybrid attention model implementation.
  No architecture override or compatibility patch is used.
- Model: [Qwen/Qwen3-Coder-Next](https://huggingface.co/Qwen/Qwen3-Coder-Next),
  an 80B-total / 3B-active-parameter coding MoE, using
  [Unsloth's Q4_K_M GGUF](https://huggingface.co/unsloth/Qwen3-Coder-Next-GGUF).
  Planning estimate for the download: **45–50 GB (42–47 GiB)**; reserve at least
  55 GB of free disk for the model, plus separate image/build storage.
  The exact current size and update date could not be verified because Hugging
  Face DNS was unavailable in the task sandbox. The downloader checks the exact
  filename and checksum against live metadata before downloading any weights.

To pick up the recently updated quantization without inventing an unverified
model commit, the downloader resolves the current Hugging Face commit **once
per volume**, saves it in `/models/model-revision.txt`, and downloads the single
`Qwen3-Coder-Next-Q4_K_M.gguf` from that immutable revision. It validates the
file against the revision's LFS SHA256 and saves its metadata. Repeated downloads
use the saved revision and resume a `.partial` file, not a moving `main`.
If a checksum fails, remove the damaged `.partial` file from the volume before
retrying; an existing completed file with a failed checksum must also be removed.
For reproducibility across machines, supply `MODEL_REVISION` with the same full
40-character commit SHA on the first download. To adopt a later model update,
use a new named volume; the downloader rejects changing an existing volume's pin.
No claim is made that Qwen released a new base model on October 10.

## Host prerequisites and build

The host must already have working `amdgpu`/KFD device access. Containers share
the host kernel; this image installs **no kernel driver**. Fedora 44 is not an
AMD-certified Radeon ROCm host distribution; treat this setup as experimental.
Do not assume this repository's Strix Halo Salt state provisions an R9700 host.

Install AMD Container Runtime Toolkit for Podman CDI following
[AMD's container guide](https://rocm.docs.amd.com/projects/install-on-linux/en/develop/how-to/docker.html#docker-with-toolkit),
then generate and verify the host spec:

```sh
sudo amd-ctk cdi generate --output=/etc/cdi/amd.json
sudo amd-ctk cdi validate --path=/etc/cdi/amd.json
amd-ctk cdi list
```

The commands below assume this is a single-GPU host. On a host with multiple GPUs,
replace `amd.com/gpu=all` with the R9700's device name printed by `amd-ctk cdi list`.
Rootless Podman needs the host user's `render`/`video` supplementary groups;
log in again after changing membership. Do not use `--runtime=amd` with Podman.

From the repository root:

```sh
podman build --format docker -t llama-cpp-qwen3-coder-next-r9700 \
  -f containers/llama-cpp-qwen3-coder-next-r9700/Dockerfile \
  containers/llama-cpp-qwen3-coder-next-r9700
podman volume create qwen3-coder-next-r9700-model
podman run --rm -v qwen3-coder-next-r9700-model:/models \
  --entrypoint /usr/local/bin/download-model llama-cpp-qwen3-coder-next-r9700
```

Model downloads happen inside the container, never in the build or repository.
The public model needs no token. For authenticated downloads, add
`--env-file .env` to the download command with `HF_TOKEN` or
`HUGGINGFACE_API_KEY` in that Git-ignored file; do not pass download credentials
to the inference server. Add `-e MODEL_REVISION=<full-commit-sha>` when selecting
an explicit model revision. The downloader needs Hugging Face metadata access
as well as access to its weight-download CDN.

## Device visibility and serving

```sh
podman run --rm --device amd.com/gpu=all --group-add keep-groups \
  llama-cpp-qwen3-coder-next-r9700 --list-devices

podman run -d --name qwen3-coder-next-r9700 \
  --device amd.com/gpu=all --group-add keep-groups \
  -v qwen3-coder-next-r9700-model:/models:ro \
  -p 127.0.0.1:8080:8080 \
  llama-cpp-qwen3-coder-next-r9700
podman logs -f qwen3-coder-next-r9700
```

Check that `--list-devices` detects the R9700 before loading weights. The image
starts `llama-server` with all non-expert layers eligible for GPU offload,
**`--cpu-moe`** (expert tensors remain in DDR5), mmap enabled, 4096 context,
one concurrent slot, eight CPU threads, batch/microbatch sizes 256/128, Flash Attention and the embedded Jinja
chat template. The entrypoint unsets `GGML_CUDA_ENABLE_UNIFIED_MEMORY`; setting
it to `0` is not sufficient in llama.cpp releases that test its existence.
There is no automatic model download on server startup.

SELinux isolation remains enabled by default. If device access fails, inspect
host AVC denials before retrying with `--security-opt label=disable`; this
relaxes isolation and is an observed workaround on the repository's Strix Halo
host, **not yet verified on an R9700**. Do not add `seccomp=unconfined` unless an
observed workload memory-mapping restriction requires it.

Any arguments after the image name **replace all default server arguments**.
For example, after confirming memory headroom, move only some expert layers
to GPU instead of all expert tensors remaining on CPU:

```sh
podman stop qwen3-coder-next-r9700
podman rm qwen3-coder-next-r9700
podman run -d --name qwen3-coder-next-r9700 \
  --device amd.com/gpu=all --group-add keep-groups \
  -v qwen3-coder-next-r9700-model:/models:ro \
  -p 127.0.0.1:8080:8080 \
  llama-cpp-qwen3-coder-next-r9700 \
  -m /models/Qwen3-Coder-Next-Q4_K_M.gguf --alias qwen3-coder-next \
  -ngl 99 --n-cpu-moe 32 -c 4096 --parallel 1 --threads 8 \
  --batch-size 256 --ubatch-size 128 \
  -fa on --jinja --temp 1.0 --top-p 0.95 --top-k 40 \
  --host 0.0.0.0 --port 8080
```

`--n-cpu-moe 32` keeps the first 32 layers' experts on CPU; this is a tuning
starting point, not a verified fit. Increase it (or return to `--cpu-moe`) if
VRAM runs out. Avoid treating `-ngl 99` alone as a full-model fit: the Q4_K_M
weights exceed 32 GB VRAM.

The host API is loopback-only even though the process listens on all interfaces
inside the container. For access from another machine, require an inference
API key **before** publishing a non-loopback port: create a Podman secret
`qwen-next-api-key`, mount it with `--secret qwen-next-api-key`, and supply
`--api-key-file /run/secrets/qwen-next-api-key` along with the complete server
arguments above. Use TLS via a trusted reverse proxy for remote access. Never
reuse a Hugging Face token as the inference key.

## Health, coding smoke check, and evaluation

Wait for model loading to finish, then:

```sh
curl -fsS http://127.0.0.1:8080/health
curl -fsS http://127.0.0.1:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3-coder-next","messages":[{"role":"user","content":"Write a Python function that returns the first n Fibonacci numbers. Include a test for n=0."}],"max_tokens":256,"temperature":0}'
python3 tests/run_eval.py --label qwen3-coder-next-r9700 \
  --base-url http://127.0.0.1:8080/v1
```

Inspect the generated code; this smoke request does not execute or prove it.
The shared evaluation harness can target this manually started endpoint.
This project is deliberately not added to the Strix Halo all-model registry:
that runner assumes all-GPU llama.cpp offload and different memory/hardware.

## Memory and validation limits

- Approximately 45 GiB of quantized weights cannot fit entirely in 32 GB VRAM.
  With `--cpu-moe`, most expert weights reside in system RAM; GPU memory holds
  non-expert weights, attention/recurrent state, KV cache and compute buffers.
  The 3B active count reduces computation, **not** stored weight size.
- Budget roughly 45 GiB for model-backed host pages before GPU duplication,
  runtime buffers and the OS. 64 GB DDR5 leaves limited headroom; close other
  memory-heavy applications and keep mmap enabled. Do not assume VRAM simply
  extends host RAM, use managed-memory overrides, lock all pages, disable mmap,
  or set a low container memory cap.
- CPU expert execution depends heavily on DDR5 bandwidth. Partial expert offload
  may improve speed, but must be measured; no tokens/second guarantee is made.
  Watch server allocation logs, host RAM/swap and GPU use before raising context
  or concurrency. The model's advertised maximum context is not the default
  memory budget for this machine.
- Hardware inference, the full weight download, output quality and performance
  have not been validated on an R9700/64 GB host. The sandbox has no KFD device.
  Build/download validation status is reported with the task; the configuration
  remains experimental until the device and application checks above pass.
