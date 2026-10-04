#!/usr/bin/env python3
"""Run the shared evaluation suite against configured Podman model containers, one at a time."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "models.json"
EVALUATOR = ROOT / "run_eval.py"
SUMMARIZER = ROOT / "summarize.py"


def load_models() -> list[dict[str, Any]]:
    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    models = data.get("models")
    if not isinstance(models, list) or not models:
        raise ValueError(f"{CONFIG} must contain a non-empty models array")
    ids = [item.get("id") for item in models]
    if len(set(ids)) != len(ids) or any(not isinstance(item, str) or not item for item in ids):
        raise ValueError("Each configured model needs a unique, non-empty id")
    return models


def command(args: list[str], *, capture: bool = False, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=capture, timeout=timeout, check=False)


def podman_exists(podman: str, kind: str, name: str) -> bool:
    result = command([podman, kind, "exists", name], capture=True)
    return result.returncode == 0


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        try:
            listener.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def volume_has_data(podman: str, model: dict[str, Any]) -> bool:
    mountpoint = model["mountpoint"]
    image = model["image"]
    volume = model["volume"]
    if model["kind"] == "llama_cpp":
        check = f"test -s {mountpoint}/{model['model_file']}"
    elif model["kind"] == "llama_hf":
        draft = f"test -s {mountpoint}/{model['draft_file']}"
        targets = " && ".join(
            f"find {mountpoint} -type f -name '{item['name']}' -size +{item['min_size']}c -print -quit | grep -q ."
            for item in model["target_files"]
        )
        check = f"{draft} && {targets}"
    else:
        check = f"test -n \"$(find {mountpoint} -mindepth 1 -print -quit)\""
    result = command([
        podman, "run", "--rm", "--pull=never", "--volume", f"{volume}:{mountpoint}:ro",
        "--entrypoint", "/bin/sh", image, "-c", check,
    ], capture=True, timeout=60)
    return result.returncode == 0


def container_args(model: dict[str, Any], name: str, port: int) -> list[str]:
    args = [
        "run", "--detach", "--name", name,
        "--device", "amd.com/gpu=all",
        "--group-add", "keep-groups",
        "--publish", f"127.0.0.1:{port}:8080",
    ]
    if model.get("selinux_label_disable"):
        args[1:1] = ["--security-opt", "label=disable"]
    if model["kind"] == "llama_cpp":
        args.extend([
            "--unsetenv", "GGML_CUDA_ENABLE_UNIFIED_MEMORY",
            "--volume", f"{model['volume']}:/models:ro",
            "--entrypoint", "/opt/llama.cpp/build/bin/llama-server",
            model["image"],
            "-m", f"/models/{model['model_file']}",
            "-ngl", "99", "-fa", "on",
            "--threads", str(model.get("threads", 8)),
            "-c", str(model.get("context", 4096)),
            "--host", "0.0.0.0", "--port", "8080",
        ])
    elif model["kind"] == "llama_hf":
        args.extend([
            "--unsetenv", "GGML_CUDA_ENABLE_UNIFIED_MEMORY",
            "--volume", f"{model['volume']}:/models:rw",
            "--env", "LLAMA_CACHE=/models",
            "--entrypoint", "/opt/llama.cpp/build/bin/llama-server",
            model["image"],
            "-hf", f"{model['hf_repo']}:{model['hf_quant']}",
            "--model-draft", f"/models/{model['draft_file']}",
            "--spec-type", "draft-mtp",
            "--spec-draft-n-max", str(model.get("draft_tokens", 2)),
            "-ngl", "99", "-fa", "on",
            "--threads", str(model.get("threads", 8)),
            "-c", str(model.get("context", 8192)),
            "--host", "0.0.0.0", "--port", "8080",
        ])
    elif model["kind"] == "strata":
        args[1:1] = ["--security-opt", "seccomp=unconfined", "--security-opt", "label=disable"]
        args.extend([
            "--volume", f"{model['volume']}:/data",
            "--env", f"FAMILY={model['family']}",
            "--env", f"MODEL={model['model']}",
            "--env", f"CONTEXT={model['context']}",
            "--env", f"LOW_RAM={model.get('low_ram', 'auto')}",
            model["image"],
        ])
    else:
        raise ValueError(f"Unsupported container kind: {model['kind']}")
    return args


def wait_until_ready(podman: str, name: str, port: int, timeout: int, interval: float) -> None:
    deadline = time.monotonic() + timeout
    url = f"http://127.0.0.1:{port}/health"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                if 200 <= response.status < 300:
                    return
        except (OSError, urllib.error.URLError, urllib.error.HTTPError):
            pass
        state = command([podman, "inspect", "--format", "{{.State.Running}}", name], capture=True, timeout=10)
        if state.returncode == 0 and state.stdout.strip().lower() == "false":
            logs = command([podman, "logs", "--tail", "60", name], capture=True, timeout=15)
            raise RuntimeError("container exited before its health endpoint became ready:\n" + logs.stdout + logs.stderr)
        time.sleep(interval)
    logs = command([podman, "logs", "--tail", "60", name], capture=True, timeout=15)
    raise TimeoutError(f"health endpoint did not become ready within {timeout}s:\n{logs.stdout}{logs.stderr}")


def cleanup_container(podman: str, name: str) -> None:
    try:
        command([podman, "stop", "--time", "30", name], capture=True, timeout=45)
    except (OSError, subprocess.SubprocessError):
        pass
    removed = command([podman, "rm", "--force", name], capture=True, timeout=30)
    if removed.returncode != 0:
        raise RuntimeError("could not remove the model container: " + (removed.stderr or removed.stdout).strip())


class SkipModel(Exception):
    """A configured image or its model data is not ready for evaluation."""


def run_model(
    model: dict[str, Any], *, podman: str, port: int, run_id: str, outdir: Path,
    suite: Path, startup_timeout: int, poll_interval: float, request_timeout: int,
    max_tokens: int, python_image: str, api_key_env: str | None, allow_strata_download: bool,
) -> dict[str, Any]:
    result: dict[str, Any] = {"id": model["id"], "label": model["label"], "status": "pending"}
    name = f"strixhalo-eval-{run_id}-{model['id']}"
    result["started_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    did_start = False
    try:
        if not podman_exists(podman, "image", model["image"]):
            raise SkipModel(f"Podman image is not present: {model['image']}")
        if not podman_exists(podman, "volume", model["volume"]):
            raise SkipModel(f"Podman model volume is not present: {model['volume']}")
        has_data = volume_has_data(podman, model)
        if model["kind"] == "strata" and not has_data and not allow_strata_download:
            raise SkipModel(
                f"Strata data volume {model['volume']} is empty; rerun with --allow-strata-download to permit its in-container download"
            )
        if model["kind"] == "llama_cpp" and not has_data:
            raise SkipModel(f"Expected model file is missing from Podman volume {model['volume']}")
        if model["kind"] == "llama_hf" and not has_data:
            target_names = ", ".join(item["name"] for item in model["target_files"])
            raise SkipModel(
                f"Expected cached Hugging Face target shards ({target_names}) and MTP draft "
                f"{model['draft_file']} are missing/incomplete in Podman volume {model['volume']}; "
                "start the container from its README once to download them before running the audit suite"
            )

        print(f"\n=== {model['label']} ({model['image']}) ===", flush=True)
        started_container = command([podman, *container_args(model, name, port)], capture=True, timeout=120)
        if started_container.returncode != 0:
            raise RuntimeError((started_container.stderr or started_container.stdout).strip())
        did_start = True
        result["container"] = name
        print(f"Waiting for http://127.0.0.1:{port}/health (up to {startup_timeout}s)...", flush=True)
        wait_until_ready(podman, name, port, startup_timeout, poll_interval)

        eval_command = [
            sys.executable, str(EVALUATOR), "--label", model["label"],
            "--base-url", f"http://127.0.0.1:{port}/v1", "--suite", str(suite),
            "--outdir", str(outdir), "--timeout", str(request_timeout),
            "--max-tokens", str(max_tokens), "--python-image", python_image,
        ]
        if api_key_env:
            eval_command.extend(["--api-key-env", api_key_env])
        evaluated = command(eval_command)
        result["evaluation_exit_code"] = evaluated.returncode
        result["status"] = "completed" if evaluated.returncode == 0 else "evaluation_failed"
        reports = sorted(outdir.glob("*.json"))
        if reports:
            result["report"] = str(reports[-1])
        else:
            result["status"] = "evaluation_failed"
            result["reason"] = "Evaluation runner did not produce a JSON report"
    except SkipModel as exc:
        result.update(status="skipped", reason=str(exc))
    except (OSError, subprocess.SubprocessError, RuntimeError, TimeoutError, ValueError) as exc:
        result.update(status="container_failed", reason=f"{type(exc).__name__}: {exc}")
    finally:
        if did_start:
            print(f"Stopping {name}...", flush=True)
            try:
                cleanup_container(podman, name)
            except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
                result.update(status="container_failed", reason=f"container cleanup failed: {exc}")
    result["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    print(f"Run status: {result['status']}" + (f" — {result['reason']}" if result.get("reason") else ""), flush=True)
    return result

def write_batch_summary(outdir: Path, outcomes: list[dict[str, Any]]) -> None:
    reports = sorted(path for path in outdir.glob("*.json") if path.name != "orchestration.json")
    summary_path = outdir / "summary.md"
    if reports:
        command([sys.executable, str(SUMMARIZER), *map(str, reports), "--out", str(summary_path)])
        existing = summary_path.read_text(encoding="utf-8")
    else:
        existing = "# Model evaluation batch\n\nNo model evaluation reports were produced.\n"
    rows = ["", "## Container run status", "", "| Model | Status | Details |", "|---|---|---|"]
    for item in outcomes:
        details = item.get("reason") or item.get("report") or ""
        label = item['label'].replace('|', '\\|')
        details = str(details).replace('|', '\\|')
        rows.append(f"| {label} | {item['status']} | {details} |")
    summary_path.write_text(existing.rstrip() + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    batch = {
        "schema_version": 1,
        "started_at": outdir.name,
        "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "results": outcomes,
    }
    (outdir / "orchestration.json").write_text(json.dumps(batch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", action="append", help="Model id from models.json; repeat to select multiple (default: all)")
    parser.add_argument("--suite", type=Path, default=ROOT / "suites" / "smoke.jsonl")
    parser.add_argument("--port", type=int, default=8080, help="Host loopback port used for one model at a time")
    parser.add_argument("--startup-timeout", type=int, default=3600, help="Maximum seconds to wait for model loading")
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--timeout", type=int, default=1800, help="Per-question model request timeout")
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--python-image", default="python:3.13-slim-bookworm")
    parser.add_argument("--api-key-env", help="Environment variable containing API key; its value is not recorded")
    parser.add_argument("--reports-root", type=Path, default=ROOT / "reports")
    parser.add_argument("--podman", default="podman", help="Podman executable")
    parser.add_argument("--allow-strata-download", action="store_true", help="Allow Strata to fetch missing model data into its named Podman volume")
    parser.add_argument("--dry-run", action="store_true", help="List the selected model order without calling Podman")
    args = parser.parse_args()

    try:
        models = load_models()
        if args.model:
            wanted = set(args.model)
            known = {model["id"] for model in models}
            unknown = wanted - known
            if unknown:
                parser.error("unknown model id(s): " + ", ".join(sorted(unknown)))
            models = [model for model in models if model["id"] in wanted]
        if not models:
            parser.error("no models selected")
        if not args.suite.is_file():
            parser.error(f"suite file does not exist: {args.suite}")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        parser.error(str(exc))

    if args.dry_run:
        for index, model in enumerate(models, start=1):
            print(f"{index}. {model['id']}: {model['label']} [{model['image']}] volume={model['volume']}")
        return 0
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    if not port_is_free(args.port):
        parser.error(f"127.0.0.1:{args.port} is already in use; stop the existing service or choose another --port")

    run_id = dt.datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]
    outdir = args.reports_root / run_id
    outdir.mkdir(parents=True, exist_ok=False)
    outcomes = []
    for model in models:
        outcomes.append(run_model(
            model, podman=args.podman, port=args.port, run_id=run_id, outdir=outdir,
            suite=args.suite.resolve(), startup_timeout=args.startup_timeout,
            poll_interval=args.poll_interval, request_timeout=args.timeout,
            max_tokens=args.max_tokens, python_image=args.python_image,
            api_key_env=args.api_key_env, allow_strata_download=args.allow_strata_download,
        ))
    write_batch_summary(outdir, outcomes)
    print(f"\nBatch report: {outdir / 'summary.md'}")
    print(f"Orchestration audit: {outdir / 'orchestration.json'}")
    return 0 if all(item["status"] == "completed" for item in outcomes) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted; any active model container is stopped during cleanup.", file=sys.stderr)
        raise SystemExit(130)
