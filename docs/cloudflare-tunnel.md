# Cloudflare Tunnel Setup

## Uebersicht

TaskPilot nutzt Cloudflare Tunnel (Zero Trust Access) fuer den sicheren Zugriff
vom MacBook auf die GX10. Alle 3 Umgebungen sind ueber eigene Subdomains erreichbar.

## Subdomains

| Umgebung | Subdomain | Ziel (lokal auf GX10) |
|----------|-----------|----------------------|
| Development | tp-dev.innosmith.ai | http://localhost:5173 |
| Integration | tp-int.innosmith.ai | http://localhost:3100 |
| Produktion | tp.innosmith.ai | http://localhost:3200 |

## Cloudflare DNS

Alle 3 Subdomains als CNAME auf den Tunnel zeigen lassen:

```
tp-dev.innosmith.ai  CNAME  <TUNNEL-UUID>.cfargotunnel.com
tp-int.innosmith.ai  CNAME  <TUNNEL-UUID>.cfargotunnel.com
tp.innosmith.ai      CNAME  <TUNNEL-UUID>.cfargotunnel.com
```

## Tunnel-Konfiguration auf der GX10

Datei: `~/.cloudflared/config.yml`

```yaml
tunnel: <TUNNEL-UUID>
credentials-file: /home/innosmith/.cloudflared/<TUNNEL-UUID>.json

ingress:
  - hostname: tp-dev.innosmith.ai
    service: http://localhost:5173
  - hostname: tp-int.innosmith.ai
    service: http://localhost:3100
  - hostname: tp.innosmith.ai
    service: http://localhost:3200
  - service: http_status:404
```

## Zero Trust Access Policy

Im Cloudflare Dashboard unter Access > Applications:

1. **Application erstellen** fuer `*.innosmith.ai` (oder je Subdomain einzeln)
2. **Policy**: Allow
   - Include: Emails ending in `@innosmith.ch`
   - Spaeter erweitern: `@be.ch` oder weitere Kunden-Domains
3. **Session Duration**: 24h (oder nach Bedarf)

## cloudflared als systemd-Service

```bash
# Installation (falls noch nicht vorhanden)
sudo cloudflared service install

# Status pruefen
sudo systemctl status cloudflared

# Neustart nach Config-Aenderung
sudo systemctl restart cloudflared
```

## Troubleshooting

```bash
# Tunnel-Status pruefen
cloudflared tunnel info <TUNNEL-UUID>

# Lokale Verbindung testen (auf GX10)
curl -s http://localhost:5173    # Dev Frontend
curl -s http://localhost:3100    # Int Frontend
curl -s http://localhost:3200    # Prod Frontend

# Tunnel-Logs
sudo journalctl -u cloudflared -f
```
