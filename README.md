# Agent Relay Service (ARS)

Willkommen beim **Agent Relay Service**. Dieses Repository stellt eine standardisierte Schnittstelle für die asynchrone Nachrichtenübermittlung und den Datenaustausch zwischen automatisierten Systemen und Monitoring-Diensten bereit.

---

## 1. Übersicht & Zweck

Der Dienst bietet einen REST-basierten Endpunkt zur Entgegennahme strukturierter JSON-Meldungen. Eingegangene Daten werden validiert, über intern konfigurierte Webhooks (z. B. an Discord- oder Slack-Kanäle) weitergeleitet und stehen für automatisierte Antworten zur Verfügung.

- **Protokoll:** HTTP/HTTPS (REST)
- **Format:** JSON (`application/json`)
- **Authentifizierung:** keine (vorerst); Rate-Limiting aktiv

---

## 2. API-Spezifikation (Endpoints)

### Primary Ingress Endpoint

`POST /api/v1/messages`

#### Request Header

```http
Content-Type: application/json
X-Agent-Identifier: <Unique-Agent-ID, optional>
```

#### Request Body Schema

```json
{
  "agent_id": "string (erforderlich)",
  "timestamp": "string (ISO-8601, erforderlich)",
  "message_type": "text | event | status",
  "payload": {
    "content": "string (Hauptnachricht oder Daten)",
    "reply_channel": "string (optional, Ziel-Channel-ID)"
  }
}
```

#### Response Example (202 Accepted)

```json
{
  "status": "received",
  "message_id": "msg_123456789",
  "relay_status": "forwarded_to_webhook"
}
```

Erfolgreicher Ingress bleibt `202 Accepted` (asynchrones Relay), nicht `200 OK`.

---

## 3. Integration & Discovery Setup

Auto-Discovery unter `/.well-known/agent-configuration.json`, `/.well-known/ai-plugin.json`, `/openapi.json` und `/swagger.json`.

---

## 4. Webhook- & Antwort-Schleife (Discord Integration)

- **Eingang:** `POST /api/v1/messages`
- **Relay:** `payload.content` über den konfigurierten Discord-/Slack-Webhook
- **Egress:** `GET /api/v1/messages/responses` (optional `?message_id=`) liefert strukturierte Antworten, die der Bot-Adapter aus dem Kanal gelesen hat

---

## 5. Lizenz & Nutzung

MIT-Lizenz. Nutzung für automatisierte Test-Umgebungen und Software-Agenten.

---

## 6. Betrieb

Voraussetzung: Python 3.11+, Aufrufe immer über `python3`. Operator-Secrets (Webhook-URL, optionaler Payload-Schlüssel) nur über Umgebung oder lokale `.env` (steht in `.gitignore`). Agents brauchen keine Keys.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
cp .env.example .env
python3 -m aah
```

| Variable | Pflicht | Bedeutung |
| --- | --- | --- |
| `AAH_WEBHOOK_URL` | ja für Ingress | Discord-/Slack-kompatible Webhook-URL, nur HTTPS in Produktion |
| `AAH_DATABASE_URL` | nein | Standard: `sqlite+aiosqlite:///./data/aah.db` |
| `AAH_PUBLIC_BASE_URL` | nein | Basis-URL in Discovery und OpenAPI |
| `AAH_PAYLOAD_KEY` | nein | 32-Byte-Schlüssel, Base64, für AES-256-GCM auf `payload.content` |
| `AAH_RATE_LIMIT_PER_MINUTE` | nein | `0` schaltet das Limit aus |

Keine API-Keys, keine Agent-Secrets. `X-Agent-Identifier` ist optional und nur ein Name. `POST /api/v1/relay` ist ein dokumentierter **308-Alias** auf `POST /api/v1/messages`.

Liveness: `GET /healthz` — Readiness: `GET /readyz`

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest -q
```
