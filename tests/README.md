# Local model evaluation harness

The harness sends the same prompts to an OpenAI-compatible chat-completions endpoint and records each prompt, full response, score, latency, token usage, model ID, and run settings. The comparison script produces a compact Markdown scorecard.

## Run all model containers in sequence

From the repository root, build each desired image and download its model into the named Podman volume described in that container's README. Then run:

```sh
python3 tests/run_all.py
```

The orchestrator runs the configured projects one at a time: it starts a container, waits for `http://127.0.0.1:8080/health`, runs the same suite, and stops/removes that container before starting the next. It binds the API only to host loopback and always uses AMD Container Runtime Toolkit CDI (`--device amd.com/gpu=all`). Local llama.cpp GGUF volumes are mounted read-only. The Qwen3.8 HF volume is mounted read-write so llama.cpp can use its persistent download cache. The runner unsets `GGML_CUDA_ENABLE_UNIFIED_MEMORY` for llama.cpp because this release otherwise uses managed allocations that failed when loading the 32B model; it also applies the observed `label=disable` SELinux workaround to that model. The Strata volume is mounted at `/data`; a non-empty volume is required by default. To explicitly allow Strata to fetch missing model data into its named Podman volume, add `--allow-strata-download`.

The runner checks that each image and volume already exist and that each llama.cpp model file is present. For Qwen3.8, it also checks for both BF16 target shards and the MTP draft file before starting; missing files are skipped so an evaluation run never silently begins a multi-gigabyte Hugging Face download. Prepare that named volume using [`containers/llama-cpp-qwen3.8-27b-bf16-mtp/README.md`](../containers/llama-cpp-qwen3.8-27b-bf16-mtp/README.md). Missing prerequisites are recorded as skipped, then it continues to later models. Strata's first load can download about 84 GB, so an empty volume is skipped unless the download flag is supplied. Each batch gets a unique directory under `tests/reports/`, containing per-model JSON reports, `summary.md`, and `orchestration.json`. It returns a non-zero exit code if any model was skipped, failed to start, or did not pass every suite case.

Select a subset by repeating `--model` with an ID from `tests/models.json`; `--dry-run` prints the order without calling Podman:

```sh
python3 tests/run_all.py --dry-run
python3 tests/run_all.py --model deepseek-r1-distill-llama-70b-q4-k-m --model deepseek-r1-distill-qwen-32b-q8-0
python3 tests/run_all.py --port 8081 --startup-timeout 5400
```

To run against a server started manually instead, see the single-model instructions in the next section. Do not run another service on the selected host port during an orchestrated batch.

## Run one manually hosted model

Start one model's `llama-server` using its container README. Then run from the repository root:

```sh
python3 tests/run_eval.py \
  --label deepseek-r1-distill-llama-70b-q4-k-m \
  --base-url http://127.0.0.1:8080/v1
```

The harness reads the served model ID from `/v1/models`; pass `--model-id ID` if the server does not implement that endpoint. Reports are written to `tests/reports/` and ignored by Git.

## Compare coding and tool use

Use the agentic suite to compare the configured models on four Python coding tasks, two direct OpenAI function-call tasks, and two MCP-backed tasks:

```sh
python3 tests/run_all.py --suite tests/suites/agentic.jsonl --port 8081
```

Choose an unused loopback port if another model server is already running. The runner starts each available model container in sequence and writes per-model JSON plus a Markdown summary under a unique directory in `tests/reports/`. Models with missing images or model data are recorded as skipped.

The coding tasks cover an LRU cache, interval merging, top-k frequency ordering, and duration parsing. Generated Python is executed with tests that are not sent to the model, inside the same no-network, read-only, resource-limited Podman sandbox used by the smoke suite.

The direct tool cases give the model two read-only fixture functions and test a two-step lookup plus a case where it should not call a tool. The MCP cases run a local stdio MCP server through `initialize`, `tools/list`, and `tools/call`; the harness makes its tool schemas available to the model as OpenAI function tools, executes the model's calls through MCP, and returns the results for the final answer. This measures the model plus a small MCP-capable host loop. It does not test Strata's optional built-in `strata_mcp` server configuration or external MCP servers.

These are small project-authored checks, not standardized coding or agent benchmarks. Python performance does not establish ability in other programming languages, repository-scale changes, or safe operation of real tools. Fixture tools are deterministic and have no external side effects.

The built-in `suites/smoke.jsonl` has three project-authored reasoning checks and one Python coding task. Generated code is executed in a disposable Podman container with networking disabled, a read-only root filesystem, no capabilities, and CPU, memory, process, and time limits. The first coding case may pull `python:3.13-slim-bookworm` into Podman image storage. The model must respond with a Python code block for this case.

Combine manually generated reports after running all models:

```sh
python3 tests/summarize.py tests/reports/*.json --out tests/reports/summary.md
```

## Add benchmark questions

The runner accepts any JSONL suite with one object per line. Each object needs `id`, `category`, `prompt`, and `evaluator`. Add `source` to preserve the dataset/problem ID in reports.

- `evaluator: "exact"` also needs an `expected` answer. Prompt the model to put its final answer on a line beginning `FINAL:`; the harness compares that answer after trimming whitespace and punctuation.
- `evaluator: "python_tests"` needs `test_code`, which is appended to the model's first Python code block and run in the Podman sandbox.
- `evaluator: "tool_call"` and `"mcp_tool"` need `expected` and `expected_tool_calls`; they run a bounded OpenAI-style tool loop and score both tool selection/arguments and the final answer. The MCP evaluator sources its tools from the included stdio fixture server.

This lets you adapt selected AIME or GPQA Diamond questions without including benchmark text or answer keys in the repository. Preserve the dataset's terms and source IDs in your local suite. For LiveCodeBench, use its official test harness to score contest tasks. SWE-bench requires a coding-agent environment; its result measures the agent and tool setup along with the model. Keep those benchmark scores distinct from this small prompt suite.

For example, an imported AIME item can use this shape (replace the placeholder with a question and its answer from a dataset you are authorized to use):

```json
{"id":"aime25-I-01","source":"AIME-2025-I/problem-1","category":"math","evaluator":"exact","expected":"123","prompt":"[question text]. Solve it and finish with FINAL: <integer>."}
```

For an API that requires a key, put the key in an environment variable and pass only its variable name with `--api-key-env`; the key itself is never stored in the report. Do not use the Hugging Face download token as an inference API key unless the serving endpoint explicitly requires it.

## Report interpretation

The smoke-suite score is a quick local comparison, not an AIME, GPQA, LiveCodeBench, or SWE-bench score. Reports from October 4, 2026 before the prompt correction included expected answers in the three reasoning prompts; disregard those scores. Current exact-answer cases reject answer leakage in their `FINAL:` instruction. The default response budget is 4096 tokens, with 8192-token llama.cpp server context for reasoning models. It contains only four questions. Compare category accuracy and latency, and review the saved answers before drawing conclusions. Re-run with a larger held-out suite for a more useful model audit.
