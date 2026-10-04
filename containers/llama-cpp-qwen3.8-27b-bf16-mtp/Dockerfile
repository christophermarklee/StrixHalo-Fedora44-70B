# syntax=docker/dockerfile:1
# Unsloth Qwen3.8-27B BF16 with MTP on the GMKtec EVO-X2 (gfx1151).
# Fedora supplies the amdgpu kernel driver; Podman passes the GPU through CDI.
FROM docker.io/rocm/dev-ubuntu-24.04:7.14.1-full

ENV DEBIAN_FRONTEND=noninteractive \
    ROCM_PATH=/opt/rocm \
    LLAMA_CACHE=/models

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential ca-certificates cmake curl git libcurl4-openssl-dev libssl-dev ninja-build \
    && rm -rf /var/lib/apt/lists/*

# b11390 includes current Qwen3.5/Qwen3.8 and MTP support.
ARG LLAMA_CPP_REF=b11390
RUN git clone --depth 1 --branch "$LLAMA_CPP_REF" \
      https://github.com/ggml-org/llama.cpp.git /opt/llama.cpp

WORKDIR /opt/llama.cpp
RUN cmake -S . -B build -G Ninja \
      -DGGML_HIP=ON \
      -DGPU_TARGETS=gfx1151 \
      -DGGML_CUDA_FA=ON \
      -DGGML_HIP_NO_VMM=ON \
      -DGGML_NATIVE=OFF \
      -DLLAMA_CURL=ON \
      -DLLAMA_OPENSSL=ON \
      -DCMAKE_BUILD_TYPE=Release \
    && cmake --build build --target llama-cli llama-server --parallel 4

ENV LD_LIBRARY_PATH=/opt/rocm/lib:/opt/rocm/lib64
COPY download-mtp.sh /usr/local/bin/download-mtp
COPY entrypoint.sh /usr/local/bin/qwen38-entrypoint
RUN chmod 0755 /usr/local/bin/download-mtp /usr/local/bin/qwen38-entrypoint

VOLUME ["/models"]
EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/qwen38-entrypoint"]
CMD ["--help"]
