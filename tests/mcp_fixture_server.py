#!/usr/bin/env python3
"""Minimal deterministic MCP stdio server used only by the evaluation harness."""

from __future__ import annotations

import json
import sys
from typing import Any


TOOLS = [
    {
        "name": "get_project",
        "description": "Look up a project by its project ID.",
        "inputSchema": {
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
            "required": ["project_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_person",
        "description": "Look up a person by their employee ID.",
        "inputSchema": {
            "type": "object",
            "properties": {"person_id": {"type": "string"}},
            "required": ["person_id"],
            "additionalProperties": False,
        },
    },
]


def dispatch(name: str, arguments: Any) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be an object")
    if name == "get_project" and arguments == {"project_id": "PX-731"}:
        return {"project_id": "PX-731", "name": "Orchid", "owner_id": "U-2048", "status": "blocked"}
    if name == "get_person" and arguments == {"person_id": "U-2048"}:
        return {"person_id": "U-2048", "name": "Amara Chen", "team": "Release Engineering"}
    raise ValueError(f"unknown tool or invalid arguments: {name} {arguments!r}")


def respond(request: dict[str, Any]) -> dict[str, Any] | None:
    method = request.get("method")
    request_id = request.get("id")
    if method == "notifications/initialized":
        return None
    if request_id is None:
        return None
    try:
        params = request.get("params") or {}
        if method == "initialize":
            result = {
                "protocolVersion": params.get("protocolVersion", "2025-06-18"),
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "strixhalo-eval-fixtures", "version": "1.0.0"},
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            output = dispatch(str(params.get("name", "")), params.get("arguments") or {})
            result = {"content": [{"type": "text", "text": json.dumps(output, ensure_ascii=False)}]}
        else:
            return {"jsonrpc": "2.0", "id": request_id,
                    "error": {"code": -32601, "message": f"method not found: {method}"}}
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except (TypeError, ValueError) as exc:
        if method == "tools/call":
            return {
                "jsonrpc": "2.0", "id": request_id,
                "result": {"isError": True, "content": [{"type": "text", "text": str(exc)}]},
            }
        return {"jsonrpc": "2.0", "id": request_id,
                "error": {"code": -32602, "message": str(exc)}}


def main() -> int:
    for line in sys.stdin:
        try:
            request = json.loads(line)
            if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
                continue
            response = respond(request)
            if response is not None:
                sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
                sys.stdout.flush()
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None,
                                         "error": {"code": -32700, "message": "parse error"}}) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

