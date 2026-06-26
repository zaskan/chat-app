# Demo Chat

API-first demo chat application with a static web UI styled like a typical ITSM/incident desk dashboard (dark sidebar, light content, primary blue actions). User, channel, and message configuration is done through the REST API. **Instance branding** (title, logo, sidebar colors) can be stored in the database and read by any client before login, or adjusted per browser in the Admin UI (local storage). The UI calls the HTTP and WebSocket APIs only.

Repository layout follows the same conventions as [itsm-app](https://github.com/zaskan/itsm-app/tree/main): `app/routes/api_v1.py` aggregates REST routers, `app/routes/ui.py` exposes static asset paths, optional logic lives under `app/services/`, JWT/password helpers in `app/auth_deps.py`, static UI files under `app/static/`, and Kubernetes manifests under `k8s/`.

## Features

- **REST API** at `/api/v1` with **OpenAPI docs** at `/docs`.
- **JWT authentication** (`Authorization: Bearer …`). Login: `POST /api/v1/auth/login`.
- **Roles**
  - **Admin**: create/delete users (with passwords), create/update/delete channels, assign users to channels, delete messages.
  - **Normal user**: participate in assigned channels; **change only their own password** (`PATCH /api/v1/users/me`).
- **Channels & membership**: users only see channels they belong to (admins see all).
- **Messages**: paginated history `GET /api/v1/channels/{channel_id}/messages?limit=&before_id=` with `has_more` and `next_before_id` for bot pagination.
- **WebSocket** (`/api/v1/ws?token=<jwt>`): JSON commands `subscribe`, `send_message`, `unsubscribe`; server events `message_created`, `subscribed`, `error`.
- **Inbound webhooks**: `POST /api/v1/webhooks/channels/{channel_id}/messages` with JSON `{"body":"..."}` and optional `"parent_id":"<root-message-uuid>"` for thread replies.
  - **Payload format** (per channel, `webhook_payload_format`): `body` (default) requires `{"body":"..."}`; `itsm` also accepts [itsm-app](https://github.com/zaskan/itsm-app) outbound events `incident.created` and `request.submitted` and maps them to channel messages (plain `body` still accepted when present).
  - **Authenticated**: same JWT as the API, or **HTTP Basic** (username/password).
  - **Anonymous** (demo only): per-channel `allow_anonymous_webhook` plus `anonymous_webhook_user_id` (member whose name appears on posts). **Anyone who can reach the URL can post** — use only on isolated networks.
- **AI / bot clients**: authenticate like any user; use REST for history and channel list; WebSocket for live traffic.
- **Instance settings (branding)**: persisted in the `app_settings` table, exposed as JSON. **Public** `GET /api/v1/settings` returns merged defaults + stored values (no auth, for the login shell). **Admin** `GET` / `PATCH` / `DELETE` on `/api/v1/admin/settings` let you read, merge-update, or clear branding overrides. The Admin UI can also keep purely local appearance overrides; wire the UI to the API when you want shared defaults for all users.
- **Health**: `GET /healthz` returns `{"status":"ok"}` (readiness/liveness).

## Quick start (local)

Requirements: Python 3.12+ recommended.

```bash
cd chat-app
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export JWT_SECRET="dev-secret-change-me"
# Optional: Postgres instead of SQLite (see Environment variables)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000/` for the UI, or `http://localhost:8000/docs` for Swagger.

**Note:** Opening `/api/v1/...` in the **browser address bar** sends **no `Authorization` header**, so the API correctly responds with `{"detail":"Not authenticated"}`. Use the UI (it stores the JWT), **Swagger “Authorize”**, or e.g. `curl -H "Authorization: Bearer <token>" https://<host>/api/v1/channels`.

On first startup with an empty database, a seed **admin** user is created (override via env):

| Variable              | Default    |
|-----------------------|------------|
| `SEED_ADMIN_USERNAME` | `admin`    |
| `SEED_ADMIN_PASSWORD` | `changeme` |

Change this password immediately for any shared or production deployment.

## Environment variables

| Variable               | Description |
|------------------------|-------------|
| `DATABASE_URL`         | SQLAlchemy URL. Default: `sqlite:///./chat.db`. Postgres example: `postgresql+psycopg://user:pass@host:5432/dbname` |
| `JWT_SECRET`           | Secret for signing JWTs (**required** in production) |
| `JWT_EXPIRE_MINUTES`   | Token lifetime (default: 1440) |
| `CORS_ORIGINS`         | Comma-separated origins or `*` (default) |
| `SEED_ADMIN_USERNAME`  | First-run admin username |
| `SEED_ADMIN_PASSWORD`  | First-run admin password |

## Container (Docker / Podman)

Build:

```bash
docker build -t demo-chat:latest .
# or: podman build -t demo-chat:latest .
```

Run with persistent SQLite:

```bash
docker run --rm -p 8000:8000 \
  -e JWT_SECRET="replace-me" \
  -v demo-chat-data:/data \
  demo-chat:latest
```

Same flags work with `podman run`.

For PostgreSQL, set `DATABASE_URL` to a `postgresql+psycopg://…` URL and drop the SQLite volume.

## Kubernetes / OpenShift

Manifests live under [`k8s/`](k8s/) (split files, similar to itsm-app): `namespace.yaml`, `secret.yaml`, `pvc.yaml`, `deployment.yaml`, `service.yaml`, `route.yaml` (OpenShift), and `ingress.example.yaml` (generic Kubernetes).

Resources use namespace **`demo-chat`** in the YAML; either switch to that project or pass **`-n demo-chat`** on every command.

### OpenShift: create the binary build once (required before `start-build`)

`oc start-build demo-chat` fails with **`buildconfigs … "demo-chat" not found`** until you create the **BuildConfig**. From your repo root (where the `Dockerfile` is), run **once per namespace**:

```bash
oc apply -f k8s/namespace.yaml
oc project demo-chat

oc new-build --name=demo-chat --binary --strategy=docker -l app=demo-chat -n demo-chat
```

Then build and push the image into the internal registry (repeat whenever you change the app):

```bash
oc start-build demo-chat --from-dir=. --follow -n demo-chat
```

Enable **local ImageStream lookup** so `image: demo-chat:latest` in the Deployment is **not** pulled from Docker Hub:

```bash
oc patch imagestream/demo-chat -n demo-chat -p '{"spec":{"lookupPolicy":{"local":true}}}'
```

### Apply Kubernetes manifests

```bash
oc apply -n demo-chat -f k8s/secret.yaml
oc apply -n demo-chat -f k8s/pvc.yaml
oc apply -n demo-chat -f k8s/deployment.yaml
oc apply -n demo-chat -f k8s/service.yaml
oc apply -n demo-chat -f k8s/route.yaml   # OpenShift; or use ingress.example.yaml on vanilla K8s
```

**`deployments.apps "demo-chat" not found`:** the Deployment was never created, or you are in the wrong namespace. Check: `oc get deployment -n demo-chat` and `oc project -q`. Create it with `oc apply -n demo-chat -f k8s/deployment.yaml`, then run `oc set image` / `oc rollout` with the same **`-n demo-chat`**.

**`InvalidImageName`:** almost always a **bad or empty image string**. Examples: `REPO` was empty so the image became literally `:latest`; or a copy/paste broke the reference. Check before `oc set image`:

```bash
REPO=$(oc get is demo-chat -n demo-chat -o jsonpath='{.status.dockerImageRepository}')
echo "REPO=${REPO}"
```

If `REPO` is empty, the ImageStream does not exist yet — run **`oc new-build`** (once), then **`oc start-build demo-chat --from-dir=. --follow`** as in the section above.

**Using short name `demo-chat:latest`:** patch **local ImageStream lookup** (shown above) before pods can resolve the image. If you prefer the full internal registry path instead of lookup, set `image:` to  
`image-registry.openshift-image-registry.svc:5000/<namespace>/demo-chat:latest`  
where `<namespace>` is **`oc project -q`**.

- Replace `jwt-secret` in `k8s/secret.yaml` before going to production.
- Optionally use PostgreSQL by changing `DATABASE_URL` in the Deployment and dropping the SQLite PVC.

Probes use `GET /healthz` on port 8000.

The sample `Deployment` sets security contexts compatible with **Pod Security** / OpenShift **restricted** SCCs: `runAsNonRoot`, `seccompProfile: RuntimeDefault`, `capabilities.drop: ["ALL"]`, `allowPrivilegeEscalation: false`, and `hostUsers: false`. It does **not** pin `fsGroup` or `runAsUser`, because OpenShift assigns UIDs/GIDs from your **namespace’s allocated ranges** (a fixed `fsGroup: 1001` often fails admission). The image marks `/data` as root-group writable (`chmod g=u`) so SQLite on a PVC still works with the assigned arbitrary UID.

## API overview

| Area | Methods |
|------|---------|
| Auth | `POST /api/v1/auth/login` |
| Instance settings (public) | `GET /api/v1/settings` — merged branding (no auth) |
| Instance settings (admin) | `GET /api/v1/admin/settings` (with `updated_at`), `PATCH /api/v1/admin/settings` (merge patch), `DELETE /api/v1/admin/settings/branding` (remove branding overrides), `POST /api/v1/admin/reset` (wipe channels/users/settings; restore seed admin) |
| Current user | `GET /api/v1/users/me`, `PATCH /api/v1/users/me` (password) |
| Users (admin) | `GET/POST /api/v1/users`, `DELETE /api/v1/users/{id}` |
| Channels | `GET/POST /api/v1/channels`, `PATCH/DELETE /api/v1/channels/{channel_id_or_name}` |
| Presence | `GET /api/v1/channels/{channel_id_or_name}/presence` — users currently connected via WebSocket (must be a channel member) |
| Members (admin) | `GET /api/v1/channels/{channel_id_or_name}/members`, `POST …/members`, `DELETE …/members/{user_id}` |
| Messages | `GET/POST /api/v1/channels/{channel_id_or_name}/messages` (`root_only`, `before_id`, `limit`; POST optional `parent_id` for thread replies), `GET …/messages/{message_id}/replies`, `DELETE …/messages` (admin, clear all history in channel), `DELETE …/messages/{message_id}` (admin) |
| Webhook | `POST /api/v1/webhooks/channels/{channel_id_or_name}/messages` (optional `parent_id` for thread replies) |

**Channel in the path:** `{channel_id_or_name}` is either the channel’s **UUID** or its exact **name** (e.g. `operations`). If the name contains reserved URL characters, percent-encode the path segment (e.g. `curl` and browsers do this for spaces; for `#` use `%23`).

| WebSocket | `GET /api/v1/ws?token=` |

### Instance settings payload

`GET /api/v1/settings` and the `branding` object in admin responses share the same shape. Branding fields (all optional in `PATCH` except you send only what you want to change):

| Field | Meaning |
|-------|---------|
| `app_title` | Application title (e.g. shown in the sidebar and browser tab). |
| `logo_mode` | `default` (built-in icon), `none`, or `custom`. |
| `logo_url` | For `custom`: `https` URL, site-relative path, or `data:image/...` (size-capped on the server). |
| `sidebar_background` | Sidebar background color, `#RRGGBB`. |
| `sidebar_text` | Primary sidebar text color (`#RRGGBB`), or `null` for automatic contrast from the background. |

`PATCH /api/v1/admin/settings` accepts a JSON body like `{"branding":{"app_title":"Support Chat","sidebar_background":"#0f172a"}}`. Set a key to JSON `null` to drop a stored override and fall back to the built-in default for that field. The service is structured so more top-level groups (e.g. feature flags) can be added next to `branding` later.

WebSocket client messages (JSON). Use **`channel_id`** (UUID string) or **`channel_name`** (exact name); one is required where a channel is referenced.

```json
{ "type": "subscribe", "channel_id": "<uuid-or-use-channel_name>" }
{ "type": "subscribe", "channel_name": "general" }
{ "type": "send_message", "channel_name": "general", "body": "hello" }
{ "type": "unsubscribe", "channel_id": "<uuid>" }
```

### curl examples (REST API)

Replace `BASE` with your origin (e.g. `http://localhost:8000` or `https://demo-chat-demo-chat.apps.example.com`). Replace `USER` / `PASS` with real credentials.

```bash
# Obtain a JWT
TOKEN=$(curl -sS -X POST "${BASE}/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"${USER}\",\"password\":\"${PASS}\"}" | jq -r '.access_token')

# Authenticated request (example: list channels you can access)
curl -sS "${BASE}/api/v1/channels" \
  -H "Authorization: Bearer ${TOKEN}"

# Paginated messages — use channel UUID or literal channel name in the path
curl -sS "${BASE}/api/v1/channels/${CHANNEL_ID}/messages?limit=50" \
  -H "Authorization: Bearer ${TOKEN}"

curl -sS "${BASE}/api/v1/channels/operations/messages?limit=50" \
  -H "Authorization: Bearer ${TOKEN}"

# Admin: clear all messages in a channel (keeps channel and members)
curl -sS -X DELETE "${BASE}/api/v1/channels/${CHANNEL_ID}/messages" \
  -H "Authorization: Bearer ${TOKEN}"

# Public instance settings (no token)
curl -sS "${BASE}/api/v1/settings"

# Admin: read settings + updated_at
curl -sS "${BASE}/api/v1/admin/settings" \
  -H "Authorization: Bearer ${TOKEN}"

# Admin: update branding (merge patch)
curl -sS -X PATCH "${BASE}/api/v1/admin/settings" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"branding":{"app_title":"Ops Chat","sidebar_background":"#1e293b"}}'

# Admin: clear stored branding overrides (defaults apply again)
curl -sS -X DELETE "${BASE}/api/v1/admin/settings/branding" \
  -H "Authorization: Bearer ${TOKEN}"

# Admin: reset instance (delete all channels, other users, settings; restore seed admin password)
curl -sS -X POST "${BASE}/api/v1/admin/reset" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"confirm":true}'
```

### curl examples (inbound webhook)

The webhook posts a message to a channel. Authenticate with the **same Bearer JWT** as the API, or **HTTP Basic** (`-u user:pass`). If the channel has **anonymous webhook** enabled in the admin UI, you may omit auth (demo-only).

```bash
# Bearer JWT (reuse TOKEN from login above) — UUID or channel name in path
curl -sS -X POST "${BASE}/api/v1/webhooks/channels/${CHANNEL_ID}/messages" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"body":"Hello from curl"}'

# Thread reply (parent_id = UUID of the top-level message being threaded)
curl -sS -X POST "${BASE}/api/v1/webhooks/channels/${CHANNEL_ID}/messages" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"body\":\"Bot reply in thread\",\"parent_id\":\"${ROOT_MESSAGE_ID}\"}"

curl -sS -X POST "${BASE}/api/v1/webhooks/channels/operations/messages" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"body":"Hello using channel name"}'

# HTTP Basic (same body schema)
curl -sS -X POST "${BASE}/api/v1/webhooks/channels/${CHANNEL_ID}/messages" \
  -u "${USER}:${PASS}" \
  -H "Content-Type: application/json" \
  -d '{"body":"Hello via Basic auth"}'

# Anonymous webhook (only if allow_anonymous_webhook is enabled on that channel)
curl -sS -X POST "${BASE}/api/v1/webhooks/channels/${CHANNEL_ID}/messages" \
  -H "Content-Type: application/json" \
  -d '{"body":"Anonymous post"}'

# ITSM outbound event (channel webhook_payload_format must be "itsm")
curl -sS -X POST "${BASE}/api/v1/webhooks/channels/operations/messages" \
  -H "Content-Type: application/json" \
  -d '{"event":"incident.created","incident":{"public_id":"INC-1","title":"Probe","severity":"low"}}'
```

Set `webhook_payload_format` to `itsm` when creating or patching a channel (admin API or channel settings UI). Unsupported ITSM event types return HTTP 204 with no message created.

## Limits

Demo-oriented: single process, no Redis, no horizontal fan-out of WebSockets across replicas. For production hardening, add migrations (Alembic), rate limits, structured logging, and a shared pub/sub if you scale past one pod.
