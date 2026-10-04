#!/usr/bin/env bash
set -euo pipefail

spec=/etc/cdi/amd.json
temporary_spec=$(mktemp /etc/cdi/amd.json.XXXXXX)
trap 'rm -f "$temporary_spec"' EXIT

amd-ctk cdi generate --output="$temporary_spec" >&2
amd-ctk cdi validate --path="$temporary_spec" >&2

if [[ -f "$spec" ]] && cmp -s "$temporary_spec" "$spec"; then
    printf "changed=no comment='AMD CDI specification is current'\n"
else
    install -m 0644 "$temporary_spec" "$spec"
    amd-ctk cdi validate --path="$spec" >&2
    printf "changed=yes comment='AMD CDI specification updated'\n"
fi
