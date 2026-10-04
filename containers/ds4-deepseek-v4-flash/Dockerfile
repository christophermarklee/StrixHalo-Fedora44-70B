# AMD Strix Halo DS4 ROCm 10.0 toolbox, pinned by amd64 image digest.
FROM docker.io/kyuz0/strix-halo-ds4-toolbox:rocm-10.0@sha256:77b4d029894c576f654e3050dc9bcb84590e0b95db3679a5ffdca607a8ed6c96

VOLUME ["/models", "/var/cache/ds4-kv"]
EXPOSE 8000
ENTRYPOINT ["ds4-server"]
CMD ["--help"]
