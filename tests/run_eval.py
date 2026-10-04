#!/usr/bin/env python3
"""Run a JSONL prompt suite against one OpenAI-compatible chat endpoint."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DEFAULT_SUITE = ROOT / "suites" / "smoke.jsonl"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def safe_url(value: str) -> str:
    parts = urllib.parse.urlsplit(value)
    host = parts.hostname or ""
    if parts.port:
        host += f":{parts.port}"
    return urllib.parse.urlunsplit((parts.scheme, host, parts.path, "", ""))


def read_suite(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            try:
                case = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: {exc}") from exc
            required = {"id", "category", "prompt", "evaluator"}
            missing = required - case.keys()
            if missing:
                raise ValueError(f"{path}:{line_number}: missing {', '.join(sorted(missing))}")
            if case["evaluator"] not in {"exact", "python_tests"}:
                raise ValueError(f"{path}:{line_number}: unsupported evaluator {case['evaluator']!r}")
            if case["evaluator"] == "exact" and "expected" not in case:
                raise ValueError(f"{path}:{line_number}: exact evaluator requires expected")
            if case["evaluator"] == "exact" and "expected" in case:
                leaked_answer = re.search(r"(?im)\bFINAL\s*:\s*" + re.escape(str(case["expected"])) + r"(?:\b|$)", str(case["prompt"]))
                if leaked_answer:
                    raise ValueError(f"{path}:{line_number}: prompt contains its expected final answer")
            if case["evaluator"] == "python_tests" and "test_code" not in case:
                raise ValueError(f"{path}:{line_number}: python_tests evaluator requires test_code")
            cases.append(case)
    if not cases:
        raise ValueError(f"No cases found in {path}")
    return cases


def request_json(url: str, headers: dict[str, str], payload: dict[str, Any] | None, timeout: int) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request_headers = dict(headers)
    if data is not None:
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=request_headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def api_headers(api_key: str | None) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def discover_model(base_url: str, headers: dict[str, str], timeout: int) -> str:
    try:
        data = request_json(base_url.rstrip("/") + "/models", headers, None, timeout)
        entries = data.get("data", [])
        if entries and entries[0].get("id"):
            return str(entries[0]["id"])
    except (OSError, ValueError, KeyError):
        pass
    return "local-model"


def ask_model(
    base_url: str,
    headers: dict[str, str],
    model_id: str,
    prompt: str,
    temperature: float,
    max_tokens: int,
    timeout: int,
) -> tuple[str, dict[str, Any], float, dict[str, Any]]:
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    start = time.monotonic()
    data = request_json(base_url.rstrip("/") + "/chat/completions", headers, payload, timeout)
    elapsed = time.monotonic() - start
    choices = data.get("choices") or []
    if not choices:
        raise ValueError("Chat completion response contained no choices")
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, list):
        content = "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    if not isinstance(content, str):
        raise ValueError("Chat completion content was not text")
    usage = data.get("usage", {})
    metadata = {"finish_reason": choices[0].get("finish_reason")}
    for field in ("reasoning_content", "reasoning"):
        if isinstance(message.get(field), str):
            metadata[field] = message[field]
    return content, usage, elapsed, metadata


def normalize_answer(value: str) -> str:
    value = value.strip().casefold()
    value = re.sub(r"^```[^\n]*\n|```$", "", value, flags=re.MULTILINE).strip()
    value = re.sub(r"\s+", " ", value)
    return value.strip(" .,:;!?`'\"$")


def final_answer(response: str) -> str:
    matches = re.findall(r"(?im)^\s*FINAL\s*:\s*(.+?)\s*$", response)
    if matches:
        return matches[-1]
    lines = [line.strip() for line in response.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def python_code(response: str) -> str:
    blocks = re.findall(r"```(?:python|py)?\s*\n?(.*?)```", response, flags=re.IGNORECASE | re.DOTALL)
    return blocks[0].strip() if blocks else response.strip()


def run_python_tests(code: str, test_code: str, image: str, timeout: int) -> dict[str, Any]:
    podman = shutil.which("podman")
    if not podman:
        return {"passed": False, "error": "podman executable not found"}
    payload = code.rstrip() + "\n\n" + test_code.strip() + "\n"
    container_name = f"strixhalo-eval-{uuid.uuid4().hex[:12]}"
    command = [
        podman, "run", "--rm", "--name", container_name, "--pull=missing", "--network=none", "--read-only",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m", "--pids-limit=64",
        "--memory=512m", "--cpus=1", "--cap-drop=ALL",
        "--security-opt=no-new-privileges", "--user=65534:65534", "-i",
        image, "python", "-I", "-",
    ]
    try:
        result = subprocess.run(command, input=payload, text=True, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        try:
            subprocess.run([podman, "kill", container_name], capture_output=True, timeout=5, check=False)
        except (OSError, subprocess.TimeoutExpired):
            pass
        return {"passed": False, "error": f"sandbox timed out after {timeout}s", "stdout": exc.stdout or "", "stderr": exc.stderr or ""}
    except OSError as exc:
        return {"passed": False, "error": str(exc)}
    return {
        "passed": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout[-12000:],
        "stderr": result.stderr[-12000:],
    }


def evaluate_case(case: dict[str, Any], response: str, args: argparse.Namespace) -> tuple[bool, dict[str, Any]]:
    if case["evaluator"] == "exact":
        answer = final_answer(response)
        expected = str(case["expected"])
        passed = normalize_answer(answer) == normalize_answer(expected)
        return passed, {"answer_extracted": answer, "expected": expected}
    if not response.strip():
        return False, {"error": "Model returned no final code to test"}
    result = run_python_tests(python_code(response), case["test_code"], args.python_image, args.sandbox_timeout)
    return bool(result.get("passed")), {"sandbox": result}


def category_summary(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        grouped.setdefault(result["category"], []).append(result)
    summary: dict[str, dict[str, Any]] = {}
    for category, rows in sorted(grouped.items()):
        done = [row for row in rows if row.get("response") is not None]
        summary[category] = {
            "passed": sum(bool(row.get("passed")) for row in rows),
            "total": len(rows),
            "accuracy": sum(bool(row.get("passed")) for row in rows) / len(rows) if rows else 0.0,
            "mean_latency_s": statistics.mean([row["latency_s"] for row in done]) if done else None,
        }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True, help="Human-readable model name for the report")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080/v1", help="OpenAI-compatible API base URL")
    parser.add_argument("--model-id", help="Served model ID; auto-detected from /models when omitted")
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE, help="JSONL suite file")
    parser.add_argument("--outdir", type=Path, default=ROOT / "reports")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--timeout", type=int, default=600, help="Model request timeout in seconds")
    parser.add_argument("--sandbox-timeout", type=int, default=30, help="Per-code-task Podman timeout")
    parser.add_argument("--python-image", default="python:3.13-slim-bookworm", help="Python image used to sandbox generated code")
    parser.add_argument("--api-key-env", help="Environment variable containing API key; never written to reports")
    args = parser.parse_args()

    try:
        cases = read_suite(args.suite)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    api_key = os.environ.get(args.api_key_env) if args.api_key_env else None
    headers = api_headers(api_key)
    model_id = args.model_id or discover_model(args.base_url, headers, min(args.timeout, 20))
    started = utc_now()
    rows: list[dict[str, Any]] = []

    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] {case['id']} ({case['category']})", flush=True)
        row: dict[str, Any] = {
            "id": case["id"], "source": case.get("source", "project-smoke"),
            "category": case["category"], "evaluator": case["evaluator"],
            "prompt": case["prompt"], "response": None, "passed": False,
        }
        if "expected" in case:
            row["reference"] = case["expected"]
        try:
            response, usage, elapsed, metadata = ask_model(
                args.base_url, headers, model_id, case["prompt"], args.temperature,
                args.max_tokens, args.timeout,
            )
            passed, evaluation = evaluate_case(case, response, args)
            row.update({"response": response, "passed": passed, "latency_s": round(elapsed, 3), "usage": usage, "evaluation": evaluation, **metadata})
        except (OSError, urllib.error.URLError, urllib.error.HTTPError, ValueError, KeyError) as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
        rows.append(row)
        print("  " + ("PASS" if row["passed"] else "ERROR" if "error" in row else "FAIL"), flush=True)

    summary = {
        "passed": sum(bool(row["passed"]) for row in rows),
        "total": len(rows),
        "accuracy": sum(bool(row["passed"]) for row in rows) / len(rows),
        "mean_latency_s": round(statistics.mean([row["latency_s"] for row in rows if "latency_s" in row]), 3)
        if any("latency_s" in row for row in rows) else None,
        "categories": category_summary(rows),
    }
    finished = utc_now()
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", args.label).strip("-").lower() or "model"
    args.outdir.mkdir(parents=True, exist_ok=True)
    report_path = args.outdir / f"{dt.datetime.now().strftime('%Y%m%dT%H%M%S-%f')}-{slug}.json"
    report = {
        "schema_version": 1,
        "label": args.label,
        "model_id": model_id,
        "api_base_url": safe_url(args.base_url),
        "suite": str(args.suite),
        "started_at": started,
        "finished_at": finished,
        "settings": {"temperature": args.temperature, "max_tokens": args.max_tokens, "request_timeout_s": args.timeout},
        "summary": summary,
        "results": rows,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nScore: {summary['passed']}/{summary['total']} ({summary['accuracy']:.1%})")
    print(f"Report: {report_path}")
    return 0 if summary["passed"] == summary["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
