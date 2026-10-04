# Local container dashboard

This small FastAPI app shows and starts/stops the five inference containers in this repository. It talks to the user's local Podman CLI and serves its browser UI and API on loopback.

## Run it

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) first. Then, from this directory:

```sh
uv sync
uv run uvicorn app:app --host 127.0.0.1 --port 8090
```

The dependencies are declared in `pyproject.toml`; `uv sync` creates the local environment and lockfile.

Open <http://127.0.0.1:8090>. Keep `--host 127.0.0.1`; the dashboard has no login and can start/stop local containers. Do not bind it to a LAN address. Its read API is at `/api/containers`, and interactive API docs are at `/api/docs`.

## What it manages

The dashboard has a fixed list of services and does not accept image names, shell commands, ports, or Podman arguments from the browser. It starts services with AMD Container Runtime Toolkit CDI (`amd.com/gpu=all`), keeps the host endpoint on loopback, and preserves each named model volume when stopping a container.

| Service | Host port | Image to build first | Model volume |
| --- | ---: | --- | --- |
| Strata Qwen3.8 Flash Next IQ3_S | 8081 | `localhost/strata-gfx1151:latest` | `strata-iq3-s-data` |
| DeepSeek R1 Distill Llama 70B Q4_K_M | 8082 | `localhost/llama-cpp-ds-r1-70b:latest` | `ds-r1-70b-q4-k-m-model` |
| Qwen2.5 72B Instruct Q4_K_M | 8083 | `localhost/llama-cpp-qwen2.5-72b-q4-k-m:latest` | `qwen2.5-72b-q4-k-m-model` |
| DeepSeek R1 Distill Qwen 32B Q8_0 | 8084 | `localhost/llama-cpp-ds-r1-distill-qwen-32b-q8:latest` | `ds-r1-distill-qwen-32b-q8-model` |
| Qwen3.8 27B BF16 MTP | 8085 | `localhost/llama-cpp-qwen3.8-27b-bf16-mtp:latest` | `qwen3.8-27b-bf16-mtp-model` |

Build images and prepare/download model data using each project's README under `containers/`. The dashboard creates a missing named volume when it creates a container. llama.cpp services expect their model files to already be in that volume. The Qwen3.8 MTP service downloads its target and projector on first start and may read `.env` from the repository root to pass the Hugging Face token. Strata downloads its model on first start.

The status cards show the local endpoint, `/health`, and `/v1/chat/completions`. A container started outside the dashboard is also listed by its configured container name; for those containers the dashboard reports the host port Podman currently publishes. Newly created dashboard containers use the dedicated ports in the table.

The service run settings follow the project READMEs, including the Strata SELinux/seccomp options and the observed SELinux workaround for the 32B model. The remaining llama.cpp services do not disable SELinux by default. Only start a model your available GPU memory can hold; model starts can take a long time and a missing or incomplete model can cause a container to exit. Use `podman logs -f <container-name>` to follow download, load, and startup output.

Stopping a service preserves its container and model volume. Start brings back an existing stopped container; it does not recreate it with new settings. To discard a container and have the dashboard create it again with its current recipe, remove that container with Podman while keeping its model volume.
