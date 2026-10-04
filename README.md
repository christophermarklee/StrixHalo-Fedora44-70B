# StrixHalo-Fedora44-70B

Local 70B model inference on a GMKtec EVO-X2 with an AMD Ryzen AI Max+ 395, Radeon 8060S (`gfx1151`), 128 GB unified memory, and a 96 GiB GPU memory reservation. The host runs Fedora 44; the container images use pinned AMD ROCm development images and run with Podman.

## Project layout

- [`salt/README.md`](salt/README.md): masterless Salt state for the Fedora host's ROCm 10 runtime tools, AMD Container Runtime Toolkit, and Podman CDI device access.
- [`containers/llama-cpp-ds-r1-70b/README.md`](containers/llama-cpp-ds-r1-70b/README.md): llama.cpp HIP image and DeepSeek-R1-Distill-Llama-70B Q4_K_M instructions.
- [`containers/llama-cpp-qwen2.5-72b-q4-k-m/README.md`](containers/llama-cpp-qwen2.5-72b-q4-k-m/README.md): Qwen2.5-72B-Instruct Q4_K_M with llama.cpp HIP.
- [`containers/llama-cpp-ds-r1-distill-qwen-32b-q8/README.md`](containers/llama-cpp-ds-r1-distill-qwen-32b-q8/README.md): DeepSeek-R1-Distill-Qwen-32B Q8_0 with llama.cpp HIP.
- [`containers/llama-cpp-qwen3.8-27b-bf16-mtp/README.md`](containers/llama-cpp-qwen3.8-27b-bf16-mtp/README.md): Unsloth Qwen3.8-27B BF16 with MTP speculative decoding.
- [`containers/strata-qwen-flash-next-iq3-s/README.md`](containers/strata-qwen-flash-next-iq3-s/README.md): Strata's experimental `gfx1151` build and Qwen IQ3_S instructions.
- [`web/README.md`](web/README.md): local FastAPI dashboard for the inference containers.
- [`NEXT.md`](NEXT.md): source notes and remaining model work.
- [`AGENTS.md`](AGENTS.md): project conventions for ROCm containers and this host.

## Host setup

After completing any pending Fedora offline update, install the Salt minion and apply the state from this repository. Review the package compatibility limits in [`salt/README.md`](salt/README.md) first.

```sh
cd /home/mlops/Code/StrixHalo-Fedora44-70B
sudo dnf install salt-minion
sudo salt-call --local --file-root="$PWD/salt" state.apply rocm10 test=True
sudo salt-call --local --file-root="$PWD/salt" state.apply rocm10
amd-ctk cdi list
```

The Salt state completed successfully on this host on October 4, 2026. It installs a limited set of ROCm 10 host packages from a disabled Fedora Rawhide repository during a pinned transaction. The full Rawhide ROCm stack currently has incompatible Fedora 44 dependencies. The container images supply their own ROCm user-space build libraries.

## Containers

Build and run each image from the repository root using the commands in its README. Podman uses AMD Container Runtime Toolkit CDI (`--device amd.com/gpu=all`); the per-container READMEs include the tested direct-device fallback where useful. Keep model downloads in each project's named Podman volume so image rebuilds do not repeat them.

The Strata IQ3_S model has loaded and answered a short test on this machine using direct device access. The llama.cpp image has built and detected the Radeon 8060S through Podman CDI, but its 70B model has not yet been loaded.

## Model evaluation

Use [`tests/README.md`](tests/README.md) to run the shared smoke suite against a hosted model endpoint and compare the audit reports. The suite includes a container-sandboxed Python coding task; imported AIME/GPQA question sets can use the documented JSONL format.

## Contributions

The repository owner, collaborators, and existing contributors may open issues and pull requests. The workflow in `.github/workflows/restrict-contributions.yml` closes new issues and pull requests from other accounts. `.github/CODEOWNERS` requests review from [@christophermarklee](https://github.com/christophermarklee) on all changes. To require that review before merging, create a ruleset for the default branch under **Settings → Rules → Rulesets**, require a pull request and an approving review, and enable **Require review from Code Owners**.

GitHub's interaction limit can block non-contributors from opening issues and pull requests before they are created. Choose **Limit to prior contributors** under **Settings → Moderation options → Interaction limits**. That setting is temporary and expires after at most six months, so it must be renewed. The workflow provides a continuing repository-side check after that setting expires, but GitHub does not provide a permanent repository setting that prevents public users from attempting to open a pull request.
