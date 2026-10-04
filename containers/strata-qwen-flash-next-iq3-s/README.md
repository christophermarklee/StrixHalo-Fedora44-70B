# Strata on the GMKtec EVO-X2

This image builds Strata's AMD HIP engine for the Radeon 8060S (`gfx1151`).
Strata [currently excludes integrated Radeon GPUs](https://github.com/Niko1221/Strata/blob/main/docs/AMD_HIP.md), so this is an experimental compatibility build. The Dockerfile pins the upstream source commit and uses AMD's ROCm 7.14.1 image. Model data persists in a Podman volume.

Build:

```sh
podman build --format docker -t strata-gfx1151 -f containers/strata-qwen-flash-next-iq3-s/Dockerfile containers/strata-qwen-flash-next-iq3-s
```

## GPU access with Podman

Use AMD Container Runtime Toolkit's CDI integration for GPU access. On the host, generate and validate its CDI spec, then check the available device names. Use `amd.com/gpu=all` to make all GPUs available to the container:

```sh
sudo amd-ctk cdi generate --output=/etc/cdi/amd.json
sudo amd-ctk cdi validate --path=/etc/cdi/amd.json
amd-ctk cdi list
```

Check GPU visibility without downloading a model:

```sh
podman run --rm --device amd.com/gpu=all \
  --security-opt seccomp=unconfined --security-opt label=disable \
  --group-add keep-groups \
  --entrypoint /opt/strata/engine/strata-device \
  strata-gfx1151 --list-devices
```

Run IQ3_S (the first start downloads roughly 84 GB of model data):

```sh
podman volume create strata-iq3-s-data
podman run -d --name strata-iq3-s \
  --device amd.com/gpu=all \
  --security-opt seccomp=unconfined \
  --security-opt label=disable \
  --group-add keep-groups \
  -p 127.0.0.1:8080:8080 \
  -v strata-iq3-s-data:/data \
  -e FAMILY=qwen -e MODEL=IQ3_S -e CONTEXT=32768 -e LOW_RAM=auto \
  strata-gfx1151
```

Follow the first download and model load with `podman logs -f strata-iq3-s`. Open <http://127.0.0.1:8080> after the model loads. The published port listens only on the host's loopback address. Stop and restart with `podman stop strata-iq3-s` and `podman start strata-iq3-s`. To choose another Strata model, change `MODEL` and use a separate data volume, or set `REINSTALL=1` when changing settings for a model already in the volume. The 96 GiB GPU reservation leaves about 30 GiB of host RAM, so keep low RAM mode enabled.

Check the local server:

```sh
curl -fsS http://127.0.0.1:8080/health
curl -fsS -H 'Content-Type: application/json' \
  -d '{"model":"qwen3.8-flash-next-iq3_s","messages":[{"role":"user","content":"What is 2 + 2? Reply with only the number."}],"max_tokens":64,"stream":false}' \
  http://127.0.0.1:8080/v1/chat/completions
```

The CDI device name can differ by host; use the name reported by `amd-ctk cdi list`. Rootless Podman may need `--group-add keep-groups` to retain access through the host's `render` and `video` groups. The AMD Container Runtime Toolkit's `amd-container-runtime` OCI runtime is for Docker; Podman uses CDI.

If Toolkit CDI is not configured, these direct device mappings are the tested fallback on this host:

```sh
podman run --rm --device /dev/kfd --device /dev/dri/renderD128 \
  --security-opt seccomp=unconfined --security-opt label=disable \
  --group-add keep-groups \
  --entrypoint /opt/strata/engine/strata-device \
  strata-gfx1151 --list-devices

podman run -d --name strata-iq3-s \
  --device /dev/kfd --device /dev/dri/renderD128 \
  --security-opt seccomp=unconfined \
  --security-opt label=disable \
  --group-add keep-groups \
  -p 127.0.0.1:8080:8080 \
  -v strata-iq3-s-data:/data \
  -e FAMILY=qwen -e MODEL=IQ3_S -e CONTEXT=32768 -e LOW_RAM=auto \
  strata-gfx1151
```

On this Fedora host, the first model load failed with ROCm's `Memory in use` error; retrying with `--security-opt label=disable` worked. The IQ3_S image then loaded 24,576 experts into 46.84 GiB of GPU memory and answered the short request above with `4`. That one request measured about 49 output tokens/s; full-context behavior and long-running stability remain unverified. Toolkit CDI is now installed, and the `strata-device --list-devices` Podman CDI command detected the Radeon 8060S (`gfx1151`). A full Strata model load through CDI remains untested.

## Notes for October 4

- The image is built as `localhost/strata-gfx1151:latest`. The downloaded IQ3_S shards, prepared expert file, MTP layer, and install config are in the persistent `strata-iq3-s-data` volume. Starting the existing container does not repeat the downloads.
- Start it with `podman start strata-iq3-s`, then follow loading with `podman logs -f strata-iq3-s`. Check `curl -fsS http://127.0.0.1:8080/health`; the web app is at <http://127.0.0.1:8080>.
- The first short request returned `4` with 49.4 output tokens/s and 75.2 prompt tokens/s. These are a smoke test, not a sustained benchmark. Try a normal conversation and a longer prompt, then watch `podman logs --tail 50 strata-iq3-s` for HIP errors.
- Keep `--security-opt label=disable` if recreating the container on this Fedora host. The API is published only on host loopback and has no API key; add a key before exposing it to other devices.
- Stop it with `podman stop strata-iq3-s`. Keep the named volume so the model remains available.
