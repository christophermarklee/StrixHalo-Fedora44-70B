# DeepSeek V4 Flash with DS4 on Strix Halo

This project serves the AMD playbook's DeepSeek V4 Flash IQ2_XXS imatrix GGUF with `ds4-server`, then connects the [Hugging Face Chat UI](../huggingface-chat-ui/README.md) in the same Podman pod. The server image is the amd64 `rocm-10.0` build from [kyuz0/strix-halo-ds4-toolbox](https://github.com/kyuz0/strix-halo-ds4-toolbox), pinned by OCI digest `sha256:77b4d029894c576f654e3050dc9bcb84590e0b95db3679a5ffdca607a8ed6c96`. Its ROCm runtime detects the Radeon 8060S as `gfx1151`; Fedora supplies the kernel driver and AMD Container Runtime Toolkit CDI passes the GPU into the container.

The main model is about 80.8 GB and the optional MTP support file about 3.6 GB. On this host's 96 GiB GPU allocation, the pinned ROCm 10.0 image loads the MTP model at a 131,072-token context with a 512-token prefill chunk. Disk KV checkpoints do not reduce the active context's memory requirement.

## Build and download

From the repository root:

```sh
podman build --format docker -t ds4-deepseek-v4-flash \
  -f containers/ds4-deepseek-v4-flash/Dockerfile \
  containers/ds4-deepseek-v4-flash
```

Download both public GGUFs inside a temporary Python container into the persistent model volume:

```sh
containers/ds4-deepseek-v4-flash/download-models.sh
```

The script creates `deepseek-v4-flash-models`, resumes Hugging Face downloads through the Hub client, and stores both files there rather than in this repository or the image.

## GPU visibility and start

Check the CDI device name and confirm the image sees `gfx1151`:

```sh
amd-ctk cdi list
podman run --rm --device amd.com/gpu=all --group-add keep-groups \
  --security-opt seccomp=unconfined \
  --entrypoint /opt/rocm/bin/rocminfo \
  localhost/ds4-deepseek-v4-flash:latest | rg 'gfx1151'
```

Create a named KV disk cache and a pod. Publish the UI and API on host loopback only so local browsers and Copilot can reach them:

```sh
podman volume create ds4-kv-cache
podman pod create --name ds4-chat \
  -p 127.0.0.1:3000:3000 \
  -p 127.0.0.1:8000:8000
```

Start the DS4 API with MTP speculative decoding, a 131,072-token context, and an 8 GiB on-disk KV checkpoint budget:

```sh
podman run -d --name ds4-server --pod ds4-chat \
  --device amd.com/gpu=all --group-add keep-groups \
  --ipc=host --cap-add=SYS_PTRACE \
  --security-opt seccomp=unconfined \
  -v deepseek-v4-flash-models:/models:ro \
  -v ds4-kv-cache:/var/cache/ds4-kv \
  localhost/ds4-deepseek-v4-flash:latest \
  -m /models/DeepSeek-V4-Flash-IQ2XXS-w2Q2K-AProjQ8-SExpQ8-OutQ8-chat-v2-imatrix.gguf \
  --mtp-model /models/DeepSeek-V4-Flash-MTP-Q4K-Q8_0-F32.gguf \
  --ctx 131072 --prefill-chunk 512 --host 0.0.0.0 --port 8000 \
  --kv-disk-dir /var/cache/ds4-kv --kv-disk-space-mb 8192
```

The ROCm 10.0 toolbox uses `--mtp-model FILE` for an external MTP GGUF; `--mtp` alone enables only model-embedded MTP. Its current `--ssd-streaming` mode cannot be combined with `--mtp-model`, so this setup keeps the model resident. The server log confirms the 3.55 GiB MTP support model loaded and the 131,072-token context initialized.

`seccomp=unconfined`, `--ipc=host`, and `SYS_PTRACE` follow the DS4 toolbox's documented ROCm container launch options for GPU memory mapping and allocation. SELinux labeling stays enabled unless a device access failure is observed.

Start Chat UI in the same pod so it can reach the server through pod loopback:

```sh
podman volume create chat-ui-data
podman run -d --name chat-ui --pod ds4-chat \
  -e OPENAI_BASE_URL=http://127.0.0.1:8000/v1 \
  -e OPENAI_API_KEY=dummy \
  -v chat-ui-data:/data \
  localhost/huggingface-chat-ui:latest
```

The UI is at <http://127.0.0.1:3000> and the OpenAI-compatible API at <http://127.0.0.1:8000/v1>. Both ports are published only on host loopback. The dummy UI key follows AMD's example; it is not authentication.

## VS Code Copilot Chat

The host's VS Code custom endpoint is configured in `~/.config/Code/User/chatLanguageModels.json` as the `ds4.c local` model group. Its entry uses `http://localhost:8000/v1/chat/completions`, tool calling, reasoning effort, a 131,072-token context window, and a 65,536-token output limit. The `dsv4-local` key is a placeholder; the DS4 server does not authenticate requests, so keep the published API bound to host loopback.

Follow the server startup and check the OpenAI-compatible API from inside the DS4 container:

```sh
podman logs -f ds4-server
podman exec ds4-server curl -fsS http://127.0.0.1:8000/v1/models
podman exec ds4-server curl -fsS http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"deepseek-v4-flash","messages":[{"role":"user","content":"What is 2 + 2? Reply with only the number."}],"max_tokens":32,"stream":false}'
```

Stop the stack while retaining models, conversations, and KV checkpoints:

```sh
podman pod stop ds4-chat
podman pod start ds4-chat
```

## MTP and limits

The model volume includes the optional 3.6 GB MTP file, which is loaded with `--mtp-model`. A short inference completed with the MTP model loaded; generation speed gains have not been benchmarked. The external MTP mode is not yet compatible with this runtime's SSD model-streaming option.

On the GMKtec EVO-X2 with Radeon 8060S, the pinned image initialized the 131,072-token context, loaded MTP support, served an OpenAI-compatible inference (`2 + 2` returned `4`), handled a tool call through the host loopback API, and exposed the Chat UI successfully. A repeated 3,132-token system prompt restored 3,122 tokens from the named KV volume after the server container was recreated. This setup was tested with the host's 96 GiB GPU allocation, default SELinux labels, and after stopping the Strata inference container to free GPU memory. Full-context prompt speed and MTP throughput gains have not been benchmarked.
