# StrixHalo-Fedora44-70B

A repository for deploying and orchestrating local large language models (70B+) on **AMD Strix Halo (Ryzen AI Max+ / gfx1151)** hardware running **Fedora 44**.

This project provides end-to-end automation using **SaltStack** to provision ROCm 10 repo configurations, container runtime toolkits, and CDI (Container Device Interface) hooks, alongside optimized **Podman / Docker runtime containers** for high-throughput 70B+ model inference.

---

## 🏗️ Repository Architecture

```text
.
├── AGENTS.md                  # Development guidelines & agent instructions
├── NEXT.md                    # Project roadmap and pending task queue
├── salt/                      # SaltStack state tree for host provisioning
│   ├── top.sls                # Main Salt state mapping
│   └── rocm10/                # ROCm 10 repo configuration & AMD container toolkit
│       ├── init.sls
│       └── files/
│           ├── amd-container-toolkit.repo
│           ├── fedora-rawhide-rocm10.repo
│           └── refresh-amd-cdi.sh
└── containers/                # Containerized LLM inference runtimes
    ├── llama-cpp-ds-r1-70b/   # llama.cpp container for DeepSeek-R1-Distill-70B
    │   ├── Dockerfile
    │   └── README.md
    └── strata-qwen-flash-next-iq3-s/ # Patch-optimized Qwen/Strata container
        ├── Dockerfile
        ├── strata-gfx1151.patch # Strix Halo (gfx1151) compilation patch
        └── README.md
```

---

## 🚀 Quick Start

### 1. Provision Host with SaltStack

Configure the host operating system with ROCm 10 packages, container runtime tools, and AMD Container Device Interface (CDI) configurations:

```bash
# Run Salt state locally to apply ROCm 10 repos and CDI drivers
sudo salt-call --local state.apply

# Refresh AMD Container Device Interface (CDI) spec
sudo /srv/salt/rocm10/files/refresh-amd-cdi.sh
```

### 2. Build & Run Containerized Models

#### Option A: DeepSeek-R1-Distill-70B (`llama.cpp`)

Navigate to the DeepSeek container directory and build the ROCm-accelerated runtime:

```bash
cd containers/llama-cpp-ds-r1-70b

# Build image
podman build -t llama-cpp-ds-r1-70b .

# Run with AMD iGPU passthrough
podman run --rm -it \
  --device /dev/kfd \
  --device /dev/dri \
  --ipc=host \
  -v /path/to/models:/models:z \
  -p 8080:8080 \
  llama-cpp-ds-r1-70b
```

#### Option B: Quantized Qwen / Strata (gfx1151 Optimized)

This runtime incorporates `strata-gfx1151.patch` to patch underlying kernel calls and target the Strix Halo architecture directly:

```bash
cd containers/strata-qwen-flash-next-iq3-s

# Build patch-applied container
podman build -t strata-qwen-gfx1151 .
```

---

## ⚙️ Target Hardware & Environment

* **APU:** AMD Ryzen AI Max+ 395 / 390 (**Strix Halo**)
* **GPU Architecture:** RDNA 3.5 (`gfx1151`)
* **Unified Memory:** 128 GB / 192 GB LPDDR5X-8000
* **Host OS:** Fedora 44 (Rawhide / ROCm 10 stack)
* **Acceleration Stack:** ROCm 10.x + AMD Container Toolkit (CDI)

---

## 📌 Environment Overrides

When running manual inference commands outside of containers on Strix Halo, ensure the following environment variables are exported:

```bash
export HSA_OVERRIDE_GFX_VERSION=11.5.1
export HCC_AMDGPU_TARGET=gfx1151
export HIP_VISIBLE_DEVICES=0
export GGML_CUDA_ENABLE_UNIFIED_MEMORY=1
```

---

## 📄 License & Notes

* Refer to `NEXT.md` for upcoming features, performance benchmarks, and pending container updates.
* Refer to `AGENTS.md` for contributor guidelines and coding conventions used across this repository.
