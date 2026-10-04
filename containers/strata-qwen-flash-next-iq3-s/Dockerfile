# syntax=docker/dockerfile:1
# Experimental Strata HIP build for the Ryzen AI Max+ 395 / Radeon 8060S (gfx1151).
# AMD's ROCm image supplies user-space libraries; Podman passes the host amdgpu
# devices at run time. Strata upstream does not yet support this integrated GPU.
FROM docker.io/rocm/dev-ubuntu-24.04:7.14.1-full

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    LANG=C.UTF-8 \
    ROCM_PATH=/opt/rocm \
    STRATA_EXECV=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential ca-certificates curl git libatomic1 libgomp1 \
    python3 python3-pip python3-venv unzip \
    && rm -rf /var/lib/apt/lists/*

ARG STRATA_COMMIT=99f3dbd0b21d1401b3769e0c0d963913607f380b
WORKDIR /opt/strata
RUN git clone https://github.com/Niko1221/Strata.git . \
    && git checkout --detach "$STRATA_COMMIT"
COPY strata-gfx1151.patch /tmp/strata-gfx1151.patch
RUN git apply --check /tmp/strata-gfx1151.patch \
    && git apply /tmp/strata-gfx1151.patch \
    && python3 -m venv .venv \
    && .venv/bin/pip install --no-cache-dir -r requirements.txt \
    && chmod +x docker-entrypoint.sh

# Build without a GPU. Strata records the compiled architecture in engine/BUILD.json
# so the first container start can reuse the engine and download only model data.
RUN .venv/bin/python -c "import setup; setup.build_engine_hip({'arch': 'gfx1151'}, setup.get_llama_cpp())"
RUN .venv/bin/cmake --build build-hip --target strata-device -j 16 \
    && cp build-hip/strata-device engine/strata-device

ENV LD_LIBRARY_PATH=/opt/rocm/lib

VOLUME ["/data"]
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=600s --retries=3 \
    CMD curl -fs "http://127.0.0.1:${PORT:-8080}/health" || exit 1
ENTRYPOINT ["./docker-entrypoint.sh"]
