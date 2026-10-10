# syntax=docker/dockerfile:1
# Radeon AI PRO R9700 (gfx1201); the Fedora host supplies amdgpu/KFD.
FROM docker.io/rocm/dev-ubuntu-24.04:7.2.3-complete

ENV DEBIAN_FRONTEND=noninteractive \
    ROCM_PATH=/opt/rocm

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential ca-certificates cmake curl jq ninja-build \
    && rm -rf /var/lib/apt/lists/*

# llama.cpp v0.6.0, released 2026-10-05.
ARG LLAMA_CPP_REF=8345f333951c661d166b00e6f9362e553768f292
RUN mkdir -p /opt/llama.cpp \
    && curl -fL --retry 5 \
      "https://codeload.github.com/ggml-org/llama.cpp/tar.gz/${LLAMA_CPP_REF}" \
      | tar -xz --strip-components=1 -C /opt/llama.cpp

WORKDIR /opt/llama.cpp
ARG BUILD_JOBS=4
RUN cmake -S . -B build -G Ninja \
      -DGGML_HIP=ON \
      -DCMAKE_HIP_ARCHITECTURES=gfx1201 \
      -DGGML_CUDA_FA=ON \
      -DGGML_NATIVE=OFF \
      -DLLAMA_CURL=OFF \
      -DLLAMA_BUILD_TESTS=OFF \
      -DCMAKE_BUILD_TYPE=Release \
    && cmake --build build --target llama-cli llama-server --parallel "$BUILD_JOBS"

ENV LD_LIBRARY_PATH=/opt/rocm/lib:/opt/rocm/lib64
COPY entrypoint.sh /usr/local/bin/qwen-next-entrypoint
COPY download-model.sh /usr/local/bin/download-model
RUN chmod 0755 /usr/local/bin/qwen-next-entrypoint /usr/local/bin/download-model

VOLUME ["/models"]
EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/qwen-next-entrypoint"]
