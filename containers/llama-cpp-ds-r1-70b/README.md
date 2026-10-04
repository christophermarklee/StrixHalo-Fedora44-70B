# DeepSeek-R1-Distill-Llama-70B with llama.cpp HIP

This container builds [llama.cpp release `b11379`](https://github.com/ggml-org/llama.cpp/releases/tag/b11379) for the GMKtec EVO-X2's Radeon 8060S (`gfx1151`). It uses AMD's `rocm/dev-ubuntu-24.04:7.14.1-full` image for ROCm user-space libraries, even though the host runs Fedora 44. The host supplies the GPU kernel driver. Podman supplies GPU access through AMD Container Runtime Toolkit CDI.

The model is [DeepSeek-R1-Distill-Llama-70B Q4_K_M](https://huggingface.co/bartowski/DeepSeek-R1-Distill-Llama-70B-GGUF), a 42.52 GB GGUF file. Keep it on the host so rebuilding the image does not download it again:

```sh
mkdir -p "$HOME/models/ds-r1-70b"
curl -fL --retry 5 --continue-at - \
  -o "$HOME/models/ds-r1-70b/DeepSeek-R1-Distill-Llama-70B-Q4_K_M.gguf" \
  https://huggingface.co/bartowski/DeepSeek-R1-Distill-Llama-70B-GGUF/resolve/main/DeepSeek-R1-Distill-Llama-70B-Q4_K_M.gguf
```

Build from the repository root:

```sh
podman build --format docker -t llama-cpp-ds-r1-70b \
  -f containers/llama-cpp-ds-r1-70b/Dockerfile \
  containers/llama-cpp-ds-r1-70b
```

Check the CDI device names with `amd-ctk cdi list`. The following commands use `amd.com/gpu=all`, as this host has one GPU. Check GPU visibility before loading the model:

```sh
podman run --rm --device amd.com/gpu=all --group-add keep-groups \
  llama-cpp-ds-r1-70b --list-devices
```

Run a short inference check:

```sh
podman run --rm --device amd.com/gpu=all --group-add keep-groups \
  -v "$HOME/models/ds-r1-70b:/models:ro,Z" \
  llama-cpp-ds-r1-70b \
  -m /models/DeepSeek-R1-Distill-Llama-70B-Q4_K_M.gguf \
  -ngl 99 -fa on --threads 8 -c 4096 -n 64 \
  -p 'What is 2 + 2? Reply with only the number.'
```

The image also builds `llama-server`. To serve locally, replace the image entrypoint and publish the port on host loopback only:

```sh
podman run --rm --device amd.com/gpu=all --group-add keep-groups \
  -v "$HOME/models/ds-r1-70b:/models:ro,Z" \
  -p 127.0.0.1:8080:8080 \
  --entrypoint /opt/llama.cpp/build/bin/llama-server \
  llama-cpp-ds-r1-70b \
  -m /models/DeepSeek-R1-Distill-Llama-70B-Q4_K_M.gguf \
  -ngl 99 -fa on --threads 8 -c 4096 \
  --host 0.0.0.0 --port 8080
```

Once loaded, check `curl -fsS http://127.0.0.1:8080/health`. The host port is bound to `127.0.0.1`; require an API key before publishing it to other machines.

## Fedora host notes

- AMD Container Runtime Toolkit CDI is installed on the host. `amd-ctk cdi list` reports `amd.com/gpu=all`, and the `--list-devices` Podman CDI command above detects the Radeon 8060S. The direct-device fallback is `--device /dev/kfd --device /dev/dri/renderD128`; confirm the actual render node with `ls /dev/dri/render*`.
- Rootless Podman may need membership in the host `render` and `video` groups. `--group-add keep-groups` passes existing supplementary group access to the container. Fedora SELinux may require an additional container option if device access fails; add `--security-opt label=disable` only after observing that problem.
- The Dockerfile compiles HIP for `gfx1151` and enables llama.cpp Flash Attention kernels. `-fa on` selects them at run time. `GGML_CUDA_ENABLE_UNIFIED_MEMORY=1` enables llama.cpp's UMA fallback and can be overridden with `-e GGML_CUDA_ENABLE_UNIFIED_MEMORY=0` for comparison.
- `NEXT.md` gives conflicting `HSA_OVERRIDE_GFX_VERSION` values (`11.0.0` and `11.5.1`). This image uses native `gfx1151` support in ROCm 7.14.1 and sets neither override. CDI selects the GPU, so it does not hardcode `HIP_VISIBLE_DEVICES` either.
- The pasted script suggested `--no-mmap`, but this host has about 30 GiB of ordinary RAM after its 96 GiB GPU reservation. Disabling mmap for a 42.52 GB file may prevent loading or raise RAM pressure. Start with mmap enabled; compare `--no-mmap` only after checking actual memory use.

The image built successfully on this host from llama.cpp commit `1537a0a`. `llama-cli --version` ran, and `--list-devices` found `ROCm0: AMD Radeon 8060S Graphics (98304 MiB)` through both direct-device Podman access and Toolkit CDI. The 70B model has not yet been downloaded or loaded, so output quality, speed, and full-context behavior remain unverified. The next check is a complete model load and a coherent short answer before changing context size or memory settings.
