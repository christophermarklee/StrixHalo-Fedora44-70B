# Container projects

This repository holds local inference containers under `containers/`. New and existing container projects target this host:

- **Machine:** GMKtec EVO-X2 mini PC with AMD Ryzen AI Max+ 395 and Radeon 8060S.
- **GPU target:** AMD `gfx1151` (Strix Halo / RDNA 3.5).
- **Memory:** 128 GB unified system memory, with 96 GiB assigned to GPU memory and about 30 GiB visible to Fedora for normal host processes.
- **Host OS/runtime:** Fedora 44 and Podman.

Host provisioning lives under `salt/` and runs with a masterless Salt minion. Its ROCm 10 state installs only the Rawhide host runtime and diagnostic packages that resolve on Fedora 44, plus AMD Container Runtime Toolkit for Podman CDI. Keep its Rawhide repository disabled outside the pinned Salt package transaction; see `salt/README.md` for the package and compatibility limits.

## ROCm container baseline

Base ROCm container setup on [AMD's Run ROCm Docker containers guide](https://rocm.docs.amd.com/projects/install-on-linux/en/develop/how-to/docker.html#docker-with-toolkit). Containers share the host kernel: GPU access depends on the host's working `amdgpu`/KFD driver and device nodes. Keep ROCm user-space libraries and build dependencies in the image; do not install a second kernel driver in the container.

Use AMD Container Runtime Toolkit with Podman through CDI. The toolkit's separate `amd-container-runtime` OCI runtime is Docker-only; CDI is the runtime-agnostic path for Podman. On the host, generate and validate the toolkit CDI spec when needed:

```sh
sudo amd-ctk cdi generate --output=/etc/cdi/amd.json
sudo amd-ctk cdi validate --path=/etc/cdi/amd.json
amd-ctk cdi list
```

Use the CDI device name shown by `amd-ctk cdi list` in Podman commands; select `all` when the container needs every GPU:

```sh
podman run --rm --device amd.com/gpu=all --group-add keep-groups <image> <command>
```

The toolkit injects the selected GPU's device access and related configuration. `--group-add keep-groups` preserves supplementary `video` and `render` group membership for rootless Podman when needed. `seccomp=unconfined` is an optional AMD-documented setting for workloads needing memory mapping; include it where the application needs it and record why. If CDI is unavailable or a project needs explicit selection by render node, the documented fallback is `--device /dev/kfd --device /dev/dri/renderD128` (confirm the node with `ls /dev/dri/render*`).

On this Fedora 44 host, Strata's first model load failed with ROCm's `Memory in use` error until the container was launched with `--security-opt label=disable`. Keep that setting in the Strata run instructions. Apply it to another container only when needed to resolve an observed SELinux/device-access issue, since it relaxes SELinux isolation for that container. Use `--group-add keep-groups` for rootless Podman when device-node group permissions require it.

## Image and application requirements

- Prefer an AMD ROCm development image as the base (for example, `rocm/dev-ubuntu-24.04`) with a pinned ROCm release. Select a release that includes usable `gfx1151` compiler/runtime support. Avoid floating `latest` tags for reproducible projects.
- Compile GPU code for `gfx1151` explicitly. A source project's list of supported architectures may exclude this integrated GPU; inspect its checks and kernels rather than merely overriding a target flag. Keep any compatibility patch in that container's folder, pin the upstream source revision, and label unvalidated support as experimental.
- Do not assume that host `free` reports all 128 GB as ordinary RAM. The 96 GiB GPU reservation leaves about 30 GiB for Fedora. Avoid imposing a low container memory cap on inference containers unless the model/runtime has been configured for it. Account for the project's model weights, KV cache, expert/cache strategy, and host RAM needs in its README.
- Persist large model downloads and generated model artifacts in a named Podman volume. Download weights from inside a container into that volume, not into the repository or an image layer. A container rebuild should not require downloading the model again.
- Bind web UIs and APIs to `127.0.0.1` by default. If a project supports access from other machines, document API-key protection and require a key for non-loopback access.

## Per-project documentation

Every directory in `containers/` should include a `Dockerfile` and a `README.md` with:

1. The upstream project and pinned source/release version.
2. The selected ROCm base image/version and how its `gfx1151` support is established.
3. Podman build and run commands using AMD Container Runtime Toolkit CDI (`--device amd.com/gpu=...`), required Fedora/SELinux options, and safe loopback port publishing. Include the direct device-passthrough fallback only when useful.
4. Named Podman volumes for model persistence, an in-container download command, and the expected first-run download size.
5. A device-visibility command and one application-level health or inference smoke check.
6. Known limits and which hardware/model configurations have actually been tested.

Use Podman with AMD Container Runtime Toolkit CDI in user-facing run instructions. A Dockerfile remains the portable image build recipe. Translate AMD's Docker examples to Podman CDI options; do not use `--runtime=amd` with Podman. Keep each container project self-contained so its build context and model data paths are clear.
