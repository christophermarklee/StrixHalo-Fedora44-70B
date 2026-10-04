"""Deterministic tools and a tiny MCP stdio client for the model evaluation suite."""

from __future__ import annotations

import json
import selectors
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
MCP_SERVER = ROOT / "mcp_fixture_server.py"

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_project",
            "description": "Look up a project by its project ID.",
            "parameters": {
                "type": "object",
                "properties": {"project_id": {"type": "string"}},
                "required": ["project_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_person",
            "description": "Look up a person by their employee ID.",
            "parameters": {
                "type": "object",
                "properties": {"person_id": {"type": "string"}},
                "required": ["person_id"],
                "additionalProperties": False,
            },
        },
    },
]


def direct_call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Run the same deterministic fixture functions without an MCP transport."""
    if name == "get_project" and arguments == {"project_id": "PX-731"}:
        return {"project_id": "PX-731", "name": "Orchid", "owner_id": "U-2048", "status": "blocked"}
    if name == "get_person" and arguments == {"person_id": "U-2048"}:
        return {"person_id": "U-2048", "name": "Amara Chen", "team": "Release Engineering"}
    raise ValueError(f"unknown tool or invalid arguments: {name} {arguments!r}")


def mcp_tool_schema(tool: dict[str, Any]) -> dict[str, Any]:
    """Convert an MCP tools/list item to an OpenAI Chat Completions function tool."""
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool.get("inputSchema") or {"type": "object", "properties": {}},
        },
    }


class McpStdioClient:
    """Small MCP stdio client using newline-delimited JSON-RPC messages."""

    protocol_version = "2025-06-18"

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout
        self.process = subprocess.Popen(
            [sys.executable, "-I", str(MCP_SERVER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self.next_id = 0
        self.selector = selectors.DefaultSelector()
        assert self.process.stdout is not None
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        self._request(
            "initialize",
            {
                "protocolVersion": self.protocol_version,
                "capabilities": {},
                "clientInfo": {"name": "strixhalo-eval", "version": "1.0"},
            },
        )
        self._notify("notifications/initialized")
        self.tools = self._request("tools/list", {}).get("tools", [])

    def _write(self, message: dict[str, Any]) -> None:
        if self.process.poll() is not None:
            raise RuntimeError(f"MCP fixture server exited with status {self.process.returncode}")
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
        self.process.stdin.flush()

    def _read_response(self, request_id: int) -> dict[str, Any]:
        assert self.process.stdout is not None
        while True:
            if not self.selector.select(self.timeout):
                raise TimeoutError(f"MCP server timed out waiting for response to request {request_id}")
            line = self.process.stdout.readline()
            if not line:
                raise RuntimeError("MCP fixture server closed stdout")
            message = json.loads(line)
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise RuntimeError(f"MCP error: {message['error']}")
            result = message.get("result")
            if not isinstance(result, dict):
                raise ValueError("MCP response result was not an object")
            return result

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.next_id += 1
        request_id = self.next_id
        self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        return self._read_response(request_id)

    def _notify(self, method: str) -> None:
        self._write({"jsonrpc": "2.0", "method": method})

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = self._request("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            raise ValueError(f"MCP tool returned an error: {result}")
        if isinstance(result.get("structuredContent"), dict):
            return result["structuredContent"]
        for item in result.get("content") or []:
            if item.get("type") == "text":
                try:
                    value = json.loads(item.get("text", ""))
                    if isinstance(value, dict):
                        return value
                except json.JSONDecodeError:
                    pass
        raise ValueError(f"MCP tool returned no structured object: {result}")

    def close(self) -> None:
        self.selector.close()
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)

