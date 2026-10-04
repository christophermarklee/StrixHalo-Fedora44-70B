#!/usr/bin/env bash
set -euo pipefail

curl -fsSL https://github.com/saltstack/salt-install-guide/releases/latest/download/salt.repo | sudo tee /etc/yum.repos.d/salt.repo
sudo dnf install -y salt-minion
