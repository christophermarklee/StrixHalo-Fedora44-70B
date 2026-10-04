# DeepSeek-R1-Distill-Qwen-32B Q8_0 with llama.cpp HIP

This project builds [llama.cpp release `b11379`](https://github.com/ggml-org/llama.cpp/releases/tag/b11379) for the GMKtec EVO-X2's Radeon 8060S (`gfx1151`). It uses AMD's `rocm/dev-ubuntu-24.04:7.14.1-full` image for ROCm user-space libraries; Fedora 44 supplies the GPU kernel driver. Podman supplies GPU access through AMD Container Runtime Toolkit CDI.

The model is [bartowski's DeepSeek-R1-Distill-Qwen-32B Q8_0 GGUF](https://huggingface.co/bartowski/DeepSeek-R1-Distill-Qwen-32B-GGUF), a single 34.82 GB file. This is the 32B distillation based on Qwen, rather than the full DeepSeek-R1 model. The image contains a downloader, but no model weights. Run the downloader in a container with a named Podman volume mounted at `/models`; the file stays in Podman storage when the container or image is removed.

From the repository root, build the image and create its model volume:

```sh
podman build --format docker -t llama-cpp-ds-r1-distill-qwen-32b-q8 \
  -f containers/llama-cpp-ds-r1-distill-qwen-32b-q8/Dockerfile \
  containers/llama-cpp-ds-r1-distill-qwen-32b-q8
podman volume create ds-r1-distill-qwen-32b-q8-model
```

Download the model **inside a container** into that volume. Re-running this command skips a completed file and resumes a `.partial` download. The download container does not need GPU access:

```sh
podman run --rm -v ds-r1-distill-qwen-32b-q8-model:/models \
  --entrypoint /usr/local/bin/download-model \
  llama-cpp-ds-r1-distill-qwen-32b-q8
```

Confirm that AMD Container Runtime Toolkit CDI exposes the GPU to the image:

```sh
amd-ctk cdi list
podman run --rm --device amd.com/gpu=all --group-add keep-groups \
  llama-cpp-ds-r1-distill-qwen-32b-q8 --list-devices
```

Run a short inference check with the model volume mounted read-only:

```sh
podman run --rm --device amd.com/gpu=all --group-add keep-groups \
  -v ds-r1-distill-qwen-32b-q8-model:/models:ro \
  llama-cpp-ds-r1-distill-qwen-32b-q8 \
  -m /models/DeepSeek-R1-Distill-Qwen-32B-Q8_0.gguf \
  -ngl 99 -fa on --threads 8 -c 4096 -n 64 \
  -p 'What is 2 + 2? Reply with only the number.'
```

To serve locally instead, use the same volume and the image's `llama-server` binary:

```sh
podman run --rm --device amd.com/gpu=all --group-add keep-groups \
  -v ds-r1-distill-qwen-32b-q8-model:/models:ro \
  -p 127.0.0.1:8080:8080 \
  --entrypoint /opt/llama.cpp/build/bin/llama-server \
  llama-cpp-ds-r1-distill-qwen-32b-q8 \
  -m /models/DeepSeek-R1-Distill-Qwen-32B-Q8_0.gguf \
  -ngl 99 -fa on --threads 8 -c 4096 \
  --host 0.0.0.0 --port 8080
```

Check `curl -fsS http://127.0.0.1:8080/health` after loading. The host port is bound to loopback; require an API key before exposing it to other machines. Run one server on port 8080 at a time, or change the host-side port.

This image compiles HIP for `gfx1151` and enables llama.cpp Flash Attention kernels; `-fa on` selects them at run time. It sets `GGML_CUDA_ENABLE_UNIFIED_MEMORY=1` and no `HSA_OVERRIDE_GFX_VERSION`. Start at 4096 context and inspect memory use before increasing it. The 96 GiB GPU reservation leaves about 30 GiB for ordinary Fedora processes, so begin with mmap enabled rather than `--no-mmap`. Rootless Podman may need a new login session for the host `render` and `video` groups. If SELinux blocks GPU access, test `--security-opt label=disable` only after observing the failure.

The same llama.cpp/ROCm build pattern detected this GPU in the existing DeepSeek 70B image. This model's image and 34.82 GB download have not yet been exercised here; GPU visibility, complete model load, output quality, and speed need verification.
