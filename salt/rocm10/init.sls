{% if grains.get('os') == 'Fedora' and grains.get('osmajorrelease', 0)|int == 44 and grains.get('cpuarch') == 'x86_64' %}

rocm10-no-pending-offline-update:
  cmd.run:
    - name: /usr/bin/bash -c 'if compgen -G "/var/lib/dnf/offline/packages/*.rpm" >/dev/null; then echo "A pending DNF offline transaction must finish before ROCm packages are installed." >&2; exit 1; fi'
    - stateful: True

rocm10-prerequisites:
  pkg.installed:
    - pkgs:
      - fedora-gpg-keys
      - podman
    - require:
      - cmd: rocm10-no-pending-offline-update

rocm10-rawhide-repo:
  file.managed:
    - name: /etc/yum.repos.d/fedora-rawhide-rocm10.repo
    - source: salt://rocm10/files/fedora-rawhide-rocm10.repo
    - user: root
    - group: root
    - mode: '0644'

rocm10-toolkit-repo:
  file.managed:
    - name: /etc/yum.repos.d/amd-container-toolkit.repo
    - source: salt://rocm10/files/amd-container-toolkit.repo
    - user: root
    - group: root
    - mode: '0644'

# DNF simulation on Fedora 44 resolves this set without Rawhide Python/glibc.
# The full `rocm` meta package and Rawhide HIP compiler do not resolve safely.
rocm10-host-packages:
  pkg.installed:
    - pkgs:
      - rocm-core: 10.0.0-1.fc46
      - rocm-runtime: 10.0.0-1.fc46
      - rocm-smi: 10.0.0-2.fc46
      - rocminfo: 10.0.0-1.fc46
      - amd-container-toolkit: 1.3.0-1.el9
    - enablerepo: fedora-rawhide-rocm10,amd-container-toolkit
    - refresh: True
    - setopt: install_weak_deps=False
    - require:
      - pkg: rocm10-prerequisites
      - file: rocm10-rawhide-repo
      - file: rocm10-toolkit-repo

rocm10-render-group:
  group.present:
    - name: render
    - addusers:
      - mlops

rocm10-video-group:
  group.present:
    - name: video
    - addusers:
      - mlops

rocm10-cdi-directory:
  file.directory:
    - name: /etc/cdi
    - user: root
    - group: root
    - mode: '0755'

rocm10-cdi-helper:
  file.managed:
    - name: /usr/local/sbin/refresh-amd-cdi
    - source: salt://rocm10/files/refresh-amd-cdi.sh
    - user: root
    - group: root
    - mode: '0755'

rocm10-cdi-spec:
  cmd.run:
    - name: /usr/local/sbin/refresh-amd-cdi
    - stateful: True
    - require:
      - pkg: rocm10-host-packages
      - file: rocm10-cdi-directory
      - file: rocm10-cdi-helper

{% else %}

rocm10-unsupported-target:
  test.fail_without_changes:
    - name: The rocm10 state targets Fedora 44 x86_64 only.

{% endif %}
