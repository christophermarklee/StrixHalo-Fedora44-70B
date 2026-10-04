"""Loopback dashboard for the repository's Podman inference containers."""

from __future__ import annotations

import json
import re
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = Path(__file__).resolve().parent / "static"


@dataclass(frozen=True)
class Service:
    id: str
    name: str
    description: str
    container: str
    image: str
    volume: str
    host_port: int
    api_kind: str = "llama"
    extra_podman_args: tuple[str, ...] = ()
    podman_args: tuple[str, ...] = ()
    command: tuple[str, ...] = ()

    @property
    def endpoint(self) -> str:
        return f"http://127.0.0.1:{self.host_port}"

    def run_args(self) -> list[str]:
        mount_path = f"{self.volume}:/data" if self.api_kind == "strata" else f"{self.volume}:/models"
        if self.api_kind not in {"strata", "qwen_mtp"}:
            mount_path += ":ro"
        args = [
            "run", "-d", "--pull=never", "--name", self.container,
            "--label", "io.strixhalo.web-managed=true",
            "--device", "amd.com/gpu=all", "--group-add", "keep-groups",
            *self.extra_podman_args,
            *self.podman_args,
            "-p", f"127.0.0.1:{self.host_port}:8080",
            "-v", mount_path,
        ]
        if self.api_kind == "strata":
            args.extend(("-e", "FAMILY=qwen", "-e", "MODEL=IQ3_S", "-e", "CONTEXT=32768", "-e", "LOW_RAM=auto"))
        elif self.api_kind == "qwen_mtp":
            env_file = PROJECT_ROOT / ".env"
            if env_file.is_file():
                args.extend(("--env-file", str(env_file)))
        args.extend((self.image, *self.command))
        return args


SERVICES: tuple[Service, ...] = (
    Service(
        id="strata-qwen-flash-next-iq3-s",
        name="Strata · Qwen3.8 Flash Next IQ3_S",
        description="Experimental Strata HIP server; first start downloads about 84 GB.",
        container="strata-iq3-s",
        image="localhost/strata-gfx1151:latest",
        volume="strata-iq3-s-data",
        host_port=8081,
        api_kind="strata",
        extra_podman_args=("--security-opt", "seccomp=unconfined", "--security-opt", "label=disable"),
    ),
    Service(
        id="llama-cpp-ds-r1-70b",
        name="DeepSeek R1 Distill Llama 70B · Q4_K_M",
        description="llama.cpp server; requires the 42.52 GB model in its volume.",
        container="llama-cpp-ds-r1-70b-server",
        image="localhost/llama-cpp-ds-r1-70b:latest",
        volume="ds-r1-70b-q4-k-m-model",
        host_port=8082,
        podman_args=("--unsetenv", "GGML_CUDA_ENABLE_UNIFIED_MEMORY", "--entrypoint", "/opt/llama.cpp/build/bin/llama-server"),
        command=(
            "-m", "/models/DeepSeek-R1-Distill-Llama-70B-Q4_K_M.gguf",
            "-ngl", "99", "-fa", "on", "--threads", "8", "-c", "8192",
            "--host", "0.0.0.0", "--port", "8080",
        ),
    ),
    Service(
        id="llama-cpp-qwen2.5-72b-q4-k-m",
        name="Qwen2.5 72B Instruct · Q4_K_M",
        description="llama.cpp server; requires the 47.42 GB model in its volume.",
        container="llama-cpp-qwen2.5-72b-q4-k-m-server",
        image="localhost/llama-cpp-qwen2.5-72b-q4-k-m:latest",
        volume="qwen2.5-72b-q4-k-m-model",
        host_port=8083,
        podman_args=("--unsetenv", "GGML_CUDA_ENABLE_UNIFIED_MEMORY", "--entrypoint", "/opt/llama.cpp/build/bin/llama-server"),
        command=(
            "-m", "/models/Qwen2.5-72B-Instruct-Q4_K_M.gguf",
            "-ngl", "99", "-fa", "on", "--threads", "8", "-c", "8192",
            "--host", "0.0.0.0", "--port", "8080",
        ),
    ),
    Service(
        id="llama-cpp-ds-r1-distill-qwen-32b-q8",
        name="DeepSeek R1 Distill Qwen 32B · Q8_0",
        description="llama.cpp server; requires the 34.82 GB model in its volume.",
        container="llama-cpp-ds-r1-distill-qwen-32b-q8-server",
        image="localhost/llama-cpp-ds-r1-distill-qwen-32b-q8:latest",
        volume="ds-r1-distill-qwen-32b-q8-model",
        host_port=8084,
        extra_podman_args=("--security-opt", "label=disable"),
        podman_args=("--unsetenv", "GGML_CUDA_ENABLE_UNIFIED_MEMORY", "--entrypoint", "/opt/llama.cpp/build/bin/llama-server"),
        command=(
            "-m", "/models/DeepSeek-R1-Distill-Qwen-32B-Q8_0.gguf",
            "-ngl", "99", "-fa", "on", "--threads", "8", "-c", "8192",
            "--host", "0.0.0.0", "--port", "8080",
        ),
    ),
    Service(
        id="llama-cpp-qwen3.8-27b-bf16-mtp",
        name="Qwen3.8 27B BF16 · MTP",
        description="llama.cpp HF download on first start; about 57–58 GB plus projector.",
        container="qwen3.8-27b-bf16-mtp",
        image="localhost/llama-cpp-qwen3.8-27b-bf16-mtp:latest",
        volume="qwen3.8-27b-bf16-mtp-model",
        host_port=8085,
        api_kind="qwen_mtp",
        extra_podman_args=("--network", "pasta:--ipv4-only", "--security-opt", "label=disable"),
        command=(
            "-hf", "unsloth/Qwen3.8-27B-GGUF:BF16",
            "--model-draft", "/models/MTP/mtp-Qwen3.8-27B-Q4_0.gguf",
            "--spec-type", "draft-mtp", "--spec-draft-n-max", "2",
            "-ngl", "99", "-fa", "on", "--threads", "8", "-c", "262144", "--parallel", "1",
            "--temp", "1.0", "--top-p", "0.95", "--top-k", "20", "--min-p", "0.0",
            "--host", "0.0.0.0", "--port", "8080",
        ),
    ),
)
SERVICE_BY_ID = {service.id: service for service in SERVICES}
MANAGEMENT_LOCK = threading.Lock()

app = FastAPI(title="Strix Halo Containers", docs_url="/api/docs", redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def podman(*args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["podman", *args], capture_output=True, text=True,
            timeout=timeout, check=False,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="Podman is not installed or is not on PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="Podman did not respond in time.") from exc


def read_containers() -> dict[str, dict[str, Any]]:
    result = podman("ps", "-a", "--format", "json")
    if result.returncode:
        detail = result.stderr.strip() or "Could not read Podman containers."
        raise HTTPException(status_code=503, detail=detail)
    try:
        rows = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="Podman returned invalid container data.") from exc
    found: dict[str, dict[str, Any]] = {}
    for row in rows:
        names = row.get("Names", [])
        if isinstance(names, str):
            names = [names]
        for name in names:
            found[str(name).lstrip("/")] = row
    return found


def get_service(service_id: str) -> Service:
    service = SERVICE_BY_ID.get(service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="Unknown service.")
    return service


def require_local_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if not origin:
        return
    origin_url = urlsplit(origin)
    host = request.headers.get("host", "")
    host_url = urlsplit(f"//{host}")
    if (
        origin_url.scheme != "http"
        or origin_url.netloc.lower() != host.lower()
        or host_url.hostname not in {"127.0.0.1", "localhost"}
    ):
        raise HTTPException(status_code=403, detail="Container actions are accepted only from this local dashboard.")


def present(service: Service, containers: dict[str, dict[str, Any]]) -> dict[str, Any]:
    row = containers.get(service.container)
    state = str(row.get("State", "unknown")).lower() if row else "not_created"
    status = str(row.get("Status", "")) if row else ""
    host_port = service.host_port
    if row:
        for port in row.get("Ports", []) or []:
            if isinstance(port, dict):
                if int(port.get("container_port", 0) or 0) == 8080 and port.get("host_port"):
                    host_port = int(port["host_port"])
                    break
            elif isinstance(port, str):
                match = re.search(r"(?:^|:)(\d+)->8080/tcp", port)
                if match:
                    host_port = int(match.group(1))
                    break
    endpoint = f"http://127.0.0.1:{host_port}"
    return {
        "id": service.id,
        "name": service.name,
        "description": service.description,
        "container": service.container,
        "image": service.image,
        "state": state,
        "status": status,
        "endpoint": endpoint,
        "health_url": endpoint + "/health",
        "api_url": endpoint + "/v1/chat/completions",
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/containers")
def list_containers() -> dict[str, Any]:
    containers = read_containers()
    return {"services": [present(service, containers) for service in SERVICES]}


@app.post("/api/containers/{service_id}/start")
def start_container(service_id: str, request: Request) -> dict[str, str]:
    require_local_origin(request)
    service = get_service(service_id)
    with MANAGEMENT_LOCK:
        containers = read_containers()
        existing = containers.get(service.container)
        if existing and str(existing.get("State", "")).lower() == "running":
            return {"message": f"{service.name} is already running."}
        if existing:
            result = podman("start", service.container)
        else:
            image_check = podman("image", "exists", service.image)
            if image_check.returncode:
                raise HTTPException(
                    status_code=409,
                    detail=f"Image {service.image} is not available. Build it using the commands in its container README.",
                )
            volume_result = podman("volume", "create", service.volume)
            if volume_result.returncode:
                raise HTTPException(status_code=502, detail=volume_result.stderr.strip() or "Could not create the model volume.")
            result = podman(*service.run_args(), timeout=120)
        if result.returncode:
            raise HTTPException(status_code=502, detail=result.stderr.strip() or "Podman could not start the service.")
    return {"message": f"Starting {service.name}. Model loading may take a while; use the logs with `podman logs -f {service.container}`."}


@app.post("/api/containers/{service_id}/stop")
def stop_container(service_id: str, request: Request) -> dict[str, str]:
    require_local_origin(request)
    service = get_service(service_id)
    with MANAGEMENT_LOCK:
        containers = read_containers()
        existing = containers.get(service.container)
        if not existing or str(existing.get("State", "")).lower() != "running":
            return {"message": f"{service.name} is already stopped."}
        result = podman("stop", "--time", "20", service.container, timeout=45)
        if result.returncode:
            raise HTTPException(status_code=502, detail=result.stderr.strip() or "Podman could not stop the service.")
    return {"message": f"Stopped {service.name}. Its model volume is preserved."}
