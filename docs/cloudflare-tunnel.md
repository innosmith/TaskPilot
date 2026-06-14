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

## Service-Tokens fuer die Chrome-Extension

Die LinkedIn-Sync-Extension (`src/chrome-extension/`) ruft die API non-interaktiv auf
und kann sich daher nicht per E-Mail/MFA anmelden. Stattdessen authentisiert sie sich
bei Cloudflare Access ueber einen **Service-Token** (Header `CF-Access-Client-Id` +
`CF-Access-Client-Secret`).

### Einrichtung

1. Cloudflare Zero Trust > Access > **Service Auth** > **Create Service Token**
2. Client-ID + Client-Secret kopieren (Secret wird nur **einmal** angezeigt)
3. In der Extension unter Optionen eintragen
4. In der Access-Application fuer `tp.innosmith.ai` eine **zusaetzliche Policy** anlegen:
   - Action: **Service Auth** (nicht Allow)
   - Include: **Service Token** > den erstellten Token auswaehlen

### WICHTIG: Ablaufdatum

> Service-Tokens haben eine begrenzte Laufzeit (Default **1 Jahr**, konfigurierbar).
> Laeuft der Token ab, bricht die Extension **lautlos** ab — Cloudflare blockt mit einem
> Redirect (`service_token_status: false`) und die Extension zeigt einen Cloudflare-Access-Fehler.
> Das ist die haeufigste Ursache fuer "Verbindung fehlgeschlagen", obwohl sich nichts
> geaendert hat.

**Ablaufdatum hier dokumentieren und rechtzeitig (ca. 2 Wochen vorher) erneuern:**

| Token-Name | Erstellt | Laeuft ab | Verwendung |
|------------|----------|-----------|------------|
| `taskpilot-linkedin-extension` | _<Datum eintragen>_ | _<Datum eintragen>_ | Chrome-Extension |

### Diagnose bei "Verbindung fehlgeschlagen"

```bash
# Mit den Extension-Creds testen (Werte einsetzen, NICHT committen):
curl -sS -o /dev/null \
  -w "%{http_code} %{redirect_url}\n" \
  -H "CF-Access-Client-Id: <CLIENT-ID>" \
  -H "CF-Access-Client-Secret: <CLIENT-SECRET>" \
  https://tp.innosmith.ai/api/pipedrive/test-connection
```

- `200` → Token gueltig (Problem liegt woanders).
- `302 https://innosmith.cloudflareaccess.com/...` → Token abgelaufen/ungueltig oder Policy fehlt → erneuern.

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
