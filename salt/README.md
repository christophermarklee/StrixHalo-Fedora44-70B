# Masterless Salt: Fedora 44 ROCm 10 host tools

The `rocm10` state targets this GMKtec EVO-X2 on Fedora 44 x86_64. It installs the Fedora Rawhide ROCm 10 **host runtime and diagnostics** (`rocm-core`, `rocm-runtime`, `rocm-smi`, and `rocminfo`) plus AMD Container Runtime Toolkit 1.3.0, which supplies `amd-ctk`. It adds `mlops` to the existing `render` and `video` groups, generates `/etc/cdi/amd.json`, and validates that CDI specification. Podman remains the container runtime.

The two repository files are installed with `enabled=0`. The state enables them only for its pinned package transaction. The Rawhide repository exposes ROCm package names only, so DNF cannot select Rawhide Python, glibc, or other core system packages from it. The October 4, 2026 transaction installed five packages and upgraded `rocm-smi`; it did not change Python or glibc. The AMD toolkit RPM comes from AMD's RHEL 9 repository; AMD does not list Fedora 44 as a supported ROCm 10 platform, so check GPU access after applying the state.

The full Rawhide `rocm` meta package is intentionally outside this state. It requires Rawhide Python 3.15, and the ROCm 10 HIP compiler requires glibc 2.44. Fedora 44 currently has glibc 2.43. Installing those dependencies would mix core Fedora 46 packages into Fedora 44. The project container images supply their own ROCm build libraries.

## Apply locally

Install the Fedora 44 Salt minion package, then run the state from the repository root. `--local` keeps this masterless; `--file-root` points Salt at this project instead of `/srv/salt`.

```sh
sudo dnf install salt-minion
cd /home/mlops/Code/StrixHalo-Fedora44-70B
sudo salt-call --local --file-root="$PWD/salt" state.apply rocm10 test=True
sudo salt-call --local --file-root="$PWD/salt" state.apply rocm10
```

The state refuses to install packages while DNF has a pending offline transaction. On October 4, `dnf offline status` reported the queued transaction was invalid after the package database changed, so it was removed with `sudo dnf offline clean` before applying Salt. If a future offline transaction is valid, complete it before applying the state.

After Salt completes, start a new login session to pick up the `render` and `video` groups. Check the host tools and CDI GPU names:

```sh
id -nG
rocminfo | grep gfx1151
rocm-smi
amd-ctk cdi list
sudo amd-ctk cdi validate --path=/etc/cdi/amd.json
podman run --rm --device amd.com/gpu=all --group-add keep-groups \
  localhost/llama-cpp-ds-r1-70b:latest --list-devices
```

Regenerate CDI after a GPU or partition change by reapplying `rocm10`, or run `/usr/local/sbin/refresh-amd-cdi`. The state applied successfully on October 4, 2026. `rocminfo` reported `gfx1151`, `rocm-smi` reported the GPU, `amd-ctk cdi list` found one AMD GPU, and the existing llama.cpp image saw the Radeon 8060S through Podman CDI. The Rawhide RPMs are signed by Fedora 46's key, so this state points its Rawhide repository at `/etc/pki/rpm-gpg/RPM-GPG-KEY-fedora-46-primary` while keeping signature checks enabled. The 70B model has not yet been loaded through this setup.
