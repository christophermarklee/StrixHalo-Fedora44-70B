# Hugging Face Chat UI for a local DS4 server

This project packages Hugging Face's self-hosted [Chat UI](https://github.com/huggingface/chat-ui) as the browser front end from AMD's [DeepSeek V4 Flash playbook](https://developer.amd.com/playbooks/deepseek-v4-flash-ds4/#connecting-a-web-ui). It connects to an already-running DS4 OpenAI-compatible API; model inference and ROCm stay in the DS4 server container.

The image is pinned to upstream Chat UI commit `f0e7d24` (`ghcr.io/huggingface/chat-ui-db:sha-f0e7d24`) and its amd64 image digest. This container is a Node.js web app with bundled MongoDB, not a GPU workload, so it does not use a ROCm base image or need CDI GPU devices. The DS4 server supplies ROCm user-space libraries and must be built for `gfx1151` as described by the AMD playbook.

## Build

From the repository root:

```sh
podman build --format docker \
  -t huggingface-chat-ui \
  -f containers/huggingface-chat-ui/Dockerfile \
  containers/huggingface-chat-ui
```

## Connect it to DS4

For the paired Fedora setup, use the [DS4 server project](../ds4-deepseek-v4-flash/README.md), which runs this UI and DS4 in one Podman pod. The UI and model API are published on host loopback only; the UI also reaches DS4 through pod loopback. For a DS4 server running outside that pod, use the host-gateway configuration below and ensure the API is reachable only from local containers; the playbook's placeholder key is not authentication.

Create a named volume for Chat UI's MongoDB and conversation data, then run the UI:

```sh
podman volume create chat-ui-data
podman run -d --name chat-ui \
  --add-host=host.docker.internal:host-gateway \
  -p 127.0.0.1:3000:3000 \
  -e OPENAI_BASE_URL=http://host.docker.internal:8000/v1 \
  -e OPENAI_API_KEY=dummy \
  -v chat-ui-data:/data \
  localhost/huggingface-chat-ui:latest
```

The UI listens only on host loopback. Open <http://127.0.0.1:3000>. The `dummy` key follows AMD's example; DS4 does not use it as access control. The named volume persists conversations and database state when the container is removed or rebuilt.

Check that the web app responds:

```sh
curl -fsS -o /dev/null -w 'Chat UI HTTP %{http_code}\n' http://127.0.0.1:3000/
```

The UI discovers model names from the DS4 `/v1/models` endpoint. Check the backend API and make a short inference request from the host:

```sh
curl -fsS http://127.0.0.1:8000/v1/models
curl -fsS http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"deepseek-v4-flash","messages":[{"role":"user","content":"What is 2 + 2? Reply with only the number."}],"max_tokens":32,"stream":false}'
```

The model download, `gfx1151` device check, context sizing, and optional KV disk cache setup are documented in the [DS4 server project](../ds4-deepseek-v4-flash/README.md). The IQ2_XXS model is about 80.8 GB; its separate model volume also holds the optional MTP weights.

### Optional MTP speculative decoding

The optional DeepSeek V4 Flash MTP weights are about 3.6 GB. The DS4 download script stores them alongside the main model in the persistent volume; rerun it if the MTP file is missing:

```sh
containers/ds4-deepseek-v4-flash/download-models.sh
```

With the pinned ROCm 10.0 DS4 toolbox, pass the external MTP file as `--mtp-model FILE` when starting the server:

```sh
ds4-server \
  -m /models/DeepSeek-V4-Flash-IQ2XXS-w2Q2K-AProjQ8-SExpQ8-OutQ8-chat-v2-imatrix.gguf \
  --mtp-model /models/DeepSeek-V4-Flash-MTP-Q4K-Q8_0-F32.gguf \
  --ctx 131072 --prefill-chunk 512
```

The standalone `--mtp` option enables only model-embedded MTP. The external MTP mode currently cannot be combined with `--ssd-streaming`; see the [tested DS4 launch](../ds4-deepseek-v4-flash/README.md) for the working host configuration. The MTP weights remain in `deepseek-v4-flash-models` across container restarts. Generation speed gains depend on the workload.

## Limits

- Tested hardware: GMKtec EVO-X2 with Radeon 8060S on Fedora 44. The UI returned HTTP 200 in the paired Podman pod and its configured backend returned inference; GPU visibility and model inference details are recorded in the DS4 project. The UI image itself has no GPU code.
- The DS4 server must implement OpenAI-compatible `/v1/models` and `/v1/chat/completions` and be reachable from this container.
- Chat UI's bundled MongoDB and conversation state persist in `chat-ui-data`; the DS4 model files are separate and must remain in the inference container's model volume.
- The UI and the playbook's placeholder API key are intended for local use. For access from another machine, configure proper authentication and an API key at the model-serving layer before exposing either service.
- Fedora's default SELinux labeling is retained. This UI does not access GPU devices, so it does not need the DS4 container's ROCm-related device or SELinux options.
