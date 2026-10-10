# syntax=docker/dockerfile:1
# OpenAI GPT-OSS-20B MXFP4 with llama.cpp HIP for the GMKtec EVO-X2 (gfx1151).
# Fedora supplies the amdgpu kernel driver; Podman passes the GPU through CDI.
FROM docker.io/rocm/dev-ubuntu-24.04:7.14.1-full

ENV DEBIAN_FRONTEND=noninteractive \
    ROCM_PATH=/opt/rocm \
    MODEL_FILE=gpt-oss-20b-MXFP4.gguf \
    MODEL_URL=https://huggingface.co/ggml-org/gpt-oss-20b-GGUF/resolve/main/gpt-oss-20b-MXFP4.gguf

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential ca-certificates cmake curl git libcurl4-openssl-dev libssl-dev ninja-build \
    && rm -rf /var/lib/apt/lists/*

# Pin llama.cpp to a release containing GPT-OSS GGUF support.
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
COPY download-model.sh /usr/local/bin/download-model
RUN chmod 0755 /usr/local/bin/download-model

VOLUME ["/models"]
EXPOSE 8080
ENTRYPOINT ["/opt/llama.cpp/build/bin/llama-cli"]
CMD ["--help"]
