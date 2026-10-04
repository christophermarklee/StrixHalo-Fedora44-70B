# syntax=docker/dockerfile:1
# Qwen2.5-72B-Instruct Q4_K_M on the GMKtec EVO-X2 (gfx1151).
# The Fedora host supplies the amdgpu kernel driver; Podman supplies GPU access
# through AMD Container Runtime Toolkit CDI at run time.
FROM docker.io/rocm/dev-ubuntu-24.04:7.14.1-full

ENV DEBIAN_FRONTEND=noninteractive \
    ROCM_PATH=/opt/rocm \
    GGML_CUDA_ENABLE_UNIFIED_MEMORY=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential ca-certificates cmake curl git ninja-build \
    && rm -rf /var/lib/apt/lists/*

ARG LLAMA_CPP_REF=b11379
RUN git clone --depth 1 --branch "$LLAMA_CPP_REF" \
      https://github.com/ggml-org/llama.cpp.git /opt/llama.cpp

WORKDIR /opt/llama.cpp
RUN cmake -S . -B build -G Ninja \
      -DGGML_HIP=ON \
      -DGPU_TARGETS=gfx1151 \
      -DGGML_CUDA_FA=ON \
      -DGGML_HIP_NO_VMM=ON \
      -DGGML_NATIVE=OFF \
      -DLLAMA_CURL=OFF \
      -DCMAKE_BUILD_TYPE=Release \
    && cmake --build build --target llama-cli llama-server --parallel 4

ENV LD_LIBRARY_PATH=/opt/rocm/lib:/opt/rocm/lib64
ENV MODEL_FILE=Qwen2.5-72B-Instruct-Q4_K_M.gguf \
    MODEL_URL=https://huggingface.co/bartowski/Qwen2.5-72B-Instruct-GGUF/resolve/main/Qwen2.5-72B-Instruct-Q4_K_M.gguf
COPY download-model.sh /usr/local/bin/download-model
RUN chmod 0755 /usr/local/bin/download-model
ENTRYPOINT ["/opt/llama.cpp/build/bin/llama-cli"]
CMD ["--help"]
