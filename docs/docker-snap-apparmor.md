# Docker Snap + AppArmor: no-new-privileges Problem

**Datum:** 12. Mai 2026
**Betrifft:** ASUS GX10 (aarch64), Ubuntu 24.04.4 LTS, Kernel 6.17.0-1014-nvidia

## Symptom

Container mit `security_opt: no-new-privileges:true` in `docker-compose.yml` starten nicht:

```
exec /app/entrypoint.sh: operation not permitted
```

Betrifft jedes Binary (bash, sh, python) — nicht nur das Entrypoint-Script.

## Ursache

Auf der GX10 laeuft der **Snap-Docker-Daemon** (nicht docker-ce):

```
dockerd --data-root=/var/snap/docker/common/var-lib-docker
        --config-file=/var/snap/docker/3507/config/daemon.json
```

Snap konfiguiert Docker unter einem AppArmor-Confinement-Profil (`snap.docker.dockerd`).
Wenn ein Container `no-new-privileges` setzt, verweigert AppArmor die Profil-Transition
beim `exec`-Syscall.

**Nicht betroffen:** Container ohne `no-new-privileges` (deshalb trat das Problem bei
anderen Projekten nie auf).

### Installationsstatus (Mai 2026)

| Komponente | Version | Status |
|---|---|---|
| Snap Docker (Daemon) | 29.3.1, Rev 3507 | **Aktiv** — laeuft als `dockerd` |
| docker-ce (apt) | 29.2.1 | Nur CLI-Binary `/usr/bin/docker`, kein eigener Daemon |
| NVIDIA Runtime | via Snap (`/snap/docker/3507/usr/bin/nvidia-container-runtime`) | Benoetigt fuer GPU-Workloads |

Der Snap-Docker wurde wegen der integrierten NVIDIA Container Runtime installiert.

## Aktuelle Loesung

`no-new-privileges:true` aus `docker-compose.integration.yml` entfernt.
Security wird stattdessen durch diese Massnahmen sichergestellt:

- Non-root User (`taskpilot`, UID 999) im Container
- Ports nur auf `127.0.0.1` gebunden (kein externer Zugriff)
- Cloudflare Zero Trust als aeussere Schicht
- Backend-RBAC + JWT-Auth + Rate-Limiting

## Saubere Alternative (fuer spaeter)

Snap-Docker durch docker-ce + nvidia-container-toolkit ersetzen:

```bash
# 1. Snap-Docker stoppen und entfernen
sudo snap stop docker
sudo snap remove docker

# 2. docker-ce Daemon aktivieren (apt-Paket ist bereits installiert)
sudo systemctl enable docker
sudo systemctl start docker

# 3. NVIDIA Container Toolkit separat installieren
# Siehe: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html
sudo apt install nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# 4. Testen
docker run --rm --gpus all nvidia/cuda:12.9.0-base-ubuntu24.04 nvidia-smi
```

Danach kann `no-new-privileges:true` wieder aktiviert werden.

**Achtung:** Dieser Wechsel betrifft ALLE Docker-Projekte auf der Maschine.
Daten unter `/var/snap/docker/common/var-lib-docker` (Images, Volumes) werden
beim Snap-Remove geloescht. Vorher pruefen, ob wichtige Volumes gesichert sind.

## Referenzen

- [Alpine + no-new-privileges Issue](https://github.com/alpinelinux/docker-alpine/issues/126)
- [Snap-Docker AppArmor Conflict (mcpproxy-go PR #386)](https://github.com/smart-mcp-proxy/mcpproxy-go/pull/386)
