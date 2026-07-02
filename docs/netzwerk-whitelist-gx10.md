# Netzwerk-Whitelist für TaskPilot auf ASUS GX10

**Stand:** Juni 2026  
**Zielgruppe:** Kunden-Deployment mit netzwerktechnischer Abriegelung (Default-Deny, explizite Freigaben)  
**Referenz-Stack:** TaskPilot Phase 1 (Pflichtenheft v0.12), ASUS Ascent GX10, Ubuntu/DGX OS (aarch64), Docker, Ollama lokal, Cloudflare Tunnel optional

---

## Zweck und Annahmen

Dieses Dokument listet **ausgehende** Internet-Ziele (Hostnames / URL-Muster), die auf einer abgeriegelten GX10 für den Betrieb, Build und Wartung von TaskPilot freigegeben werden müssen.

| Symbol | Bedeutung |
|--------|-----------|
| **Pflicht** | Für Standard-Deployment (M365 + lokales LLM + Docker) erforderlich |
| **Optional** | Nur wenn das Feature aktiv genutzt wird |
| **Build** | Nur bei Image-Build, `pip install`, `npm ci`, Erstinstallation — nicht im Dauerbetrieb |
| **Lokal** | Kein Internet — läuft auf localhost / internes Netz |

**Wichtig:**

- Fast alle Einträge nutzen **HTTPS (TCP 443)**. Zusätzlich **DNS (UDP/TCP 53)** und **NTP (UDP 123)** auf vertrauenswürdige interne Resolver/Zeitserver.
- Der GX10 initiiert Verbindungen **ausgehend** (Pull-Modell). Eingehender Zugriff auf TaskPilot erfolgt typischerweise über **Cloudflare Tunnel** (`cloudflared`) — ebenfalls als ausgehender Tunnel, kein offener Port nach aussen.
- Platzhalter `{tenant}`, `{domain}`, `{kunde}` durch kundenspezifische Werte ersetzen.
- Bei **Default-Deny** empfiehlt sich ein **Offline-Mirror** (Docker-Registry, PyPI, npm, Ollama-Modelle) für wiederholbare Builds ohne breite Internet-Freigabe.

---

## 1. Betriebssystem, NVIDIA & CUDA (GX10 Host)

Für Treiber, DGX OS / Ubuntu-Updates und GPU-Stack auf dem GB10 (ARM64, CUDA 13.x).

| Host / Muster | Zweck | Priorität |
|---------------|-------|-----------|
| `archive.ubuntu.com` | Ubuntu-Paket-Updates (Host) | Pflicht |
| `security.ubuntu.com` | Sicherheitsupdates (Host) | Pflicht |
| `ports.ubuntu.com` | ARM64-Pakete (Host) | Pflicht |
| `developer.download.nvidia.com` | NVIDIA-Treiber, CUDA-Toolkit, Runfiles | Pflicht |
| `developer.nvidia.com` | Metadaten, Redirects | Pflicht |
| `ngc.nvidia.com` | NVIDIA GPU Cloud (Metadaten, Auth) | Optional |
| `nvcr.io` | NGC-Container (z. B. PyTorch/vLLM-Images) | Optional |
| `*.nvidia.com` | Breite Freigabe nur wenn Einzelhosts unbekannt — sonst obige Hosts bevorzugen | Bedingt |

**Hinweis:** Ollama nutzt auf dem GX10 primär den **lokalen** Dienst (`http://127.0.0.1:11434`). NVIDIA-URLs sind für OS/Treiber-Wartung und optionale NGC-Container relevant, nicht für jeden LLM-Aufruf.

---

## 2. Container-Images & Docker-Registry

TaskPilot zieht folgende Images (siehe `docker/docker-compose*.yml`, `docker/Dockerfile.*`):

| Host / Muster | Images / Zweck | Priorität |
|---------------|----------------|-----------|
| `registry-1.docker.io` | `python:3.12-slim`, `node:20-slim`, `nginx:alpine`, `pgvector/pgvector:pg16`, `clamav/clamav-debian:unstable`, `docker:cli` (Sandbox-Executor-Basis) | Pflicht (Pull) |
| `auth.docker.io` | Docker-Hub-Authentifizierung | Pflicht (Pull) |
| `production.cloudflare.docker.com` | Docker-Hub CDN-Layer | Pflicht (Pull) |
| `ghcr.io` | `ghcr.io/berriai/litellm:main-latest` (LiteLLM-Proxy) | Pflicht |
| `deb.debian.org` | APT innerhalb Debian-basierter Images (Build) | Build |
| `security.debian.org` | Sicherheitsupdates im Image-Build | Build |

**Build-only (Backend-Image):** HuggingFace- und spaCy-Modelle werden beim Image-Build geladen (siehe Abschnitt 8).

---

## 3. Paket-Registries (Build & Wartung)

| Host / Muster | Zweck | Priorität |
|---------------|-------|-----------|
| `pypi.org` | Python-Dependencies (`requirements.txt`, `hermes-agent`, …) | Build |
| `files.pythonhosted.org` | PyPI-Wheel-Downloads | Build |
| `registry.npmjs.org` | Frontend (`npm ci` in `src/frontend`) | Build |
| `github.com` | Quellcode, Releases (spaCy-Modelle), Git-Clone | Pflicht (Dev/Ops) |
| `api.github.com` | GitHub API (`gh` CLI, Automation) | Optional |
| `raw.githubusercontent.com` | Raw-Dateien, Redirects | Build |
| `codeload.github.com` | GitHub-Archive-Downloads | Build |
| `objects.githubusercontent.com` | Git LFS / Release-Artefakte | Build |

---

## 4. Lokale LLM-Infrastruktur (Ollama)

| Host / Muster | Zweck | Priorität |
|---------------|-------|-----------|
| `registry.ollama.ai` | `ollama pull` — Modell-Downloads (z. B. Qwen 3.x, Embedding-Modelle) | Pflicht (Initial + Updates) |
| `ollama.com` | Installer, Metadaten, ggf. Update-Checks | Build / Wartung |

**Lokal (kein Internet):**

| URL | Zweck |
|-----|-------|
| `http://127.0.0.1:11434` | Ollama API (Tags, Chat, Embeddings) — vom Backend, LiteLLM und Hermes genutzt |
| `http://host.docker.internal:11434` | Ollama vom Docker-Container aus (via `extra_hosts`) |

**Empfehlung abgeriegeltes Netz:** Modelle einmalig pullen, danach `registry.ollama.ai` wieder sperren; Modell-Tags **fixieren** (kein `:latest` in Produktion).

---

## 5. Microsoft 365 / Graph API

TaskPilot greift über `src/email-graph/graph_client.py` und MCP `mcp-graph` auf Microsoft Graph zu (E-Mail, Kalender, Teams-Chat, OneDrive, Planner).

| Host / Muster | Endpunkte / Zweck | Priorität |
|---------------|-------------------|-----------|
| `login.microsoftonline.com` | OAuth2 Client-Credentials: `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token` | **Pflicht** |
| `graph.microsoft.com` | REST API v1.0: Mail, Kalender, Chats, OneDrive, Planner, Online-Meetings/Transkripte | **Pflicht** |

**Typische Graph-Pfade (alle unter `https://graph.microsoft.com/v1.0`):**

- `/users/{mailbox}/messages`, `/mailFolders`, `/send`
- `/users/{mailbox}/calendarView`, `/events`
- `/users/{mailbox}/chats`, `/chats/{id}/messages`
- `/users/{mailbox}/drive/...` (OneDrive)
- `/users/{mailbox}/planner/...`, `/planner/tasks/...`

**Nicht serverseitig nötig (nur Browser-Deep-Links im Frontend):**

- `outlook.office.com`, `outlook.office365.com`, `onedrive.live.com`

**Azure-Portal** (`portal.azure.com`) nur für Admin-Einrichtung der App-Registration — nicht für Laufzeit.

---

## 6. Cloud-LLM-Provider (über LiteLLM-Proxy)

Konfiguration: `docker/litellm-config.yaml`. Cloud-Aufrufe nur wenn API-Keys gesetzt und Modell explizit gewählt (Datenschutz: sensitive Tasks → Ollama lokal).

| Host / Muster | Provider | Verwendung in TaskPilot | Priorität |
|---------------|----------|-------------------------|-----------|
| `api.openai.com` | OpenAI | Chat, LinkedIn-Extraktion (`gpt-4.1-nano`), Modell-Liste | Optional |
| `api.anthropic.com` | Anthropic | Chat, Analyse, Modell-Liste | Optional |
| `generativelanguage.googleapis.com` | Google Gemini | Chat, Deep Research (`/v1beta/interactions`), Modell-Liste | Optional |
| `api.perplexity.ai` | Perplexity | Recherche-Modelle (`perplexity/*` via LiteLLM) | Optional |

**Lokal (kein Internet):**

| URL | Zweck |
|-----|-------|
| `http://127.0.0.1:4000` | LiteLLM-Proxy (Routing zu Ollama + Cloud) |
| `http://taskpilot-litellm:4000` | LiteLLM aus Prod-Backend-Container |

---

## 7. Business-Integrationen (SaaS-APIs)

Nur freigeben, wenn die Integration beim Kunden aktiv ist.

### Pipedrive CRM

| Host / Muster | Zweck | Priorität |
|---------------|-------|-----------|
| `https://{domain}.pipedrive.com/api/v1` | Leads, Notes (Legacy) | Optional |
| `https://{domain}.pipedrive.com/api/v2` | Deals, Persons, Activities, Pipelines | Optional |

`{domain}` = Firmen-Subdomain (Env: `TP_PIPEDRIVE_DOMAIN`, Default bei InnoSmith: `innosmith`).

### Bexio Buchhaltung

| Host / Muster | Zweck | Priorität |
|---------------|-------|-----------|
| `api.bexio.com` | REST API v2/v3 (`/2.0`, `/3.0`) | Optional |

### Toggl Track

| Host / Muster | Zweck | Priorität |
|---------------|-------|-----------|
| `api.track.toggl.com` | API v9 + Reports API v3 | Optional |

### Tavily (Websuche, Legacy)

| Host / Muster | Zweck | Priorität |
|---------------|-------|-----------|
| `api.tavily.com` | `/search` — klassische Websuche (`web_search`-Router, MCP-TaskPilot) | Optional |

### Unsplash (Hintergrundbilder)

| Host / Muster | Zweck | Priorität |
|---------------|-------|-----------|
| `api.unsplash.com` | Foto-Suche (Backend) | Optional |
| `images.unsplash.com` | Bild-CDN (Frontend lädt Thumbnails/HQ) | Optional |

### MeisterTask / MindMeister (Migrations-Skripte)

| Host / Muster | Zweck | Priorität |
|---------------|-------|-----------|
| `www.meistertask.com` | Einmalige Migration (`scripts/migrate_meistertask.py`) | Optional (Migration) |
| `www.mindmeister.com` | Export-Skript (`scripts/export_mindmeister.py`) | Optional (Migration) |

---

## 8. NLP-Modelle & Virenscanner (Build + Laufzeit)

### Docker-Build (Backend-Image)

| Host / Muster | Artefakt | Priorität |
|---------------|----------|-----------|
| `github.com` (explosion/spacy-models Releases) | spaCy `de_core_news_lg`, `en_core_web_sm` | Build |
| `huggingface.co` | GLiNER `urchade/gliner_multi_pii-v1` | Build |
| `cdn-lfs.huggingface.co` | HuggingFace LFS-Dateien | Build |
| `hf.co` | HuggingFace-Redirects | Build |

**Empfehlung:** Modelle im Build pullen und Image versionieren; danach HF/GitHub für Laufzeit sperren.

### ClamAV (Upload-Virenscan)

| Host / Muster | Zweck | Priorität |
|---------------|-------|-----------|
| `database.clamav.net` | Virendefinitionen (Freshclam, alle ~2 h) | Pflicht (wenn ClamAV aktiv) |
| `*.clamav.net` | Spiegel (falls konfiguriert) | Pflicht (wenn ClamAV aktiv) |

Container: `clamav/clamav-debian:unstable` — intern auf Port 3310, kein Internet-Zugriff von aussen nötig.

---

## 9. Hermes Agent — Websuche & Recherche

Hermes aktiviert das Built-in-Toolset **`web`** (`web_search`, `web_extract`) für agentische Recherche.

| Verhalten | Netzwerk-Implikation |
|-----------|---------------------|
| `web_search` / `web_extract` | **Beliebige HTTPS-Ziele** — nicht auf eine feste URL-Liste reduzierbar |
| Legacy Tavily-Endpunkt | Nur `api.tavily.com` (siehe Abschnitt 7) |

**Empfehlung für strikte Whitelist:**

1. Toolset `web` in Hermes deaktivieren / aus Allowlist entfernen, **oder**
2. Separates HTTP-Proxy mit URL-Policy + Logging, **oder**
3. Recherche ausschliesslich über Tavily (ohne `web_extract` auf beliebige Seiten)

---

## 10. Cloudflare Tunnel & Zero Trust (Remote-Zugriff)

Wenn TaskPilot wie bei InnoSmith über Cloudflare erreichbar ist (`docs/cloudflare-tunnel.md`):

| Host / Muster | Zweck | Priorität |
|---------------|-------|-----------|
| `*.cfargotunnel.com` | Tunnel-Endpunkt (CNAME-Ziel) | Optional (Remote-Zugriff) |
| `region1.v2.argotunnel.com` (weitere Regionen möglich) | `cloudflared` QUIC-Verbindung | Optional |
| `api.cloudflare.com` | Tunnel-Registrierung, Management | Optional |
| `update.argotunnel.com` | `cloudflared`-Updates | Wartung |
| `pkg.cloudflare.com` | Paket-Distribution (Installer) | Build |
| `{kunde}.cloudflareaccess.com` | Zero Trust Login (Client-Browser, nicht GX10) | — |

**Lokal auf GX10:**

| URL | Zweck |
|-----|-------|
| `http://localhost:5173` | Dev-Frontend (Vite) |
| `http://localhost:3100` / `:3200` | Int/Prod-Frontend (Nginx) |
| `http://localhost:8000` / `:8100` / `:8200` | Backend-API |

---

## 11. Optionale / kundenspezifische Dienste

| Dienst | Host / URL | Hinweis |
|--------|------------|---------|
| **SIGNA** (Strategic Intelligence) | `{ISI_HOST}:{ISI_PORT}` (PostgreSQL) | Meist **internes Netz**, kein Internet — Env: `TP_ISI_*` |
| **InvoiceInsight** | `http://127.0.0.1:8055/mcp` (Default) | Lokal auf GX10; kein Internet |
| **Private Git-Repos** | z. B. `github.com/{org}/contentConverter` | Build — InnoSmith-intern |
| **Gravatar** | `gravatar.com` | Nur Browser (Avatare) — **nicht** GX10-Server |
| **YouTube-Embeds** | `www.youtube.com`, `img.youtube.com` | Nur Browser (SIGNA-Signale) — **nicht** GX10-Server |
| **CRM/Bexio/Toggl-UI** | `{domain}.pipedrive.com`, `office.bexio.com`, `track.toggl.com` | Nur Browser-Links |

---

## 12. Komplett lokal — kein Internet erforderlich

Diese Komponenten kommunizieren nur innerhalb des Hosts / Docker-Netzes:

| Komponente | URL / Port |
|------------|------------|
| PostgreSQL + pgvector | `127.0.0.1:5435` (Dev/Int), `127.0.0.1:5437` (Prod) |
| LiteLLM-Proxy | `127.0.0.1:4000` |
| Ollama | `127.0.0.1:11434` |
| ClamAV | `127.0.0.1:3310` |
| InvoiceInsight MCP | `127.0.0.1:8055` |
| Hermes-Config / Skills | `~/.hermes/` (Dateisystem) |
| MCP-Server | Subprocess stdio (kein TCP nach aussen) |
| Sandbox-Executor | `127.0.0.1:8090` (Dev) / internes Docker-Netz (Int/Prod) — token-geschützt, kein Internet |
| Sandbox-Container | Lokales Docker-Image (`docker/sandbox/Dockerfile`), `--network none` |

---

## 13. Empfohlene Minimal-Whitelist (Kompakt)

Für ein **typisches CH-KMU-Setup** (M365 + Ollama lokal + Docker + ClamAV + GitHub-Deploy, **ohne** Cloud-LLMs und **ohne** CRM/Bexio/Toggl):

```
# OS & GPU
archive.ubuntu.com
security.ubuntu.com
ports.ubuntu.com
developer.download.nvidia.com
developer.nvidia.com

# Container & Code
registry-1.docker.io
auth.docker.io
production.cloudflare.docker.com
ghcr.io
github.com
raw.githubusercontent.com
codeload.github.com
objects.githubusercontent.com

# LLM-Modelle
registry.ollama.ai

# Microsoft 365
login.microsoftonline.com
graph.microsoft.com

# Sicherheit
database.clamav.net

# Build (kann nach Setup entfernt werden)
pypi.org
files.pythonhosted.org
registry.npmjs.org
deb.debian.org
security.debian.org
huggingface.co
cdn-lfs.huggingface.co
```

---

## 14. Checkliste für Kunden-Onboarding

1. **Feature-Matrix** erstellen: Welche Integrationen (Graph, Pipedrive, Bexio, Toggl, Tavily, Cloud-LLMs, Unsplash, Cloudflare) sind aktiv?
2. **Build-Fenster** definieren: PyPI, npm, Docker Hub, HuggingFace nur während Installation/Upgrade.
3. **Ollama-Modelle** vor Produktiv-Go-Live pullen und Tags fixieren.
4. **Hermes `web`-Toolset** policy-mässig entscheiden (breite Egress-Freigabe vs. deaktiviert).
5. **ClamAV** Freshclam testen (`database.clamav.net` erreichbar?).
6. **Graph App-Registration**: Application Permissions + Admin Consent (kein zusätzlicher Host ausser `login.microsoftonline.com` / `graph.microsoft.com`).
7. **Cloudflare** (falls genutzt): Tunnel-UUID, Service-Token-Ablauf dokumentieren.
8. **Monitoring**: DNS-Auflösung und HTTPS-443-Firewall-Logs während Erstinstallation mitführen — Hersteller/CDNs ändern gelegentlich Redirect-Ziele.

---

## 15. Referenzen im Repository

| Thema | Datei |
|-------|-------|
| Architektur & MCP-Server | `.cursor/rules/taskpilot-architektur.mdc` |
| Docker-Images & Dependencies | `.cursor/rules/deployment-docker.mdc` |
| Cloudflare Tunnel | `docs/cloudflare-tunnel.md` |
| LiteLLM-Routing | `docker/litellm-config.yaml` |
| Graph-Client | `src/email-graph/graph_client.py` |
| GX10 / LLM-Stack | `docs/research/LLM Inferenz-Stack für TaskPilot auf dem ASUS Ascent GX10 (April 2026).md` |

---

*Erstellt für InnoSmith GmbH — TaskPilot Referenz-Deployment. Kundenspezifische Domains und optionale Integrationen müssen pro Projekt ergänzt werden.*
