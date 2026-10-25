#!/usr/bin/env bash
# Dev launcher. Behaviour:
#  - If .env.local exists, source it (full local dev with your real secrets).
#  - If it's missing, write a preview-mode fallback that proxies /api to the
#    live backend, so the frontend still boots and login/data work against
#    production. This survives environment resets where .env.local disappears.
#  - Then boot the full stack: uvicorn (backend), deno supervisor (edge
#    functions), deno actors-host (realtime), and vite (frontend).
#    Processes that can't run in a given environment (no uv/deno) fail
#    silently in the background; vite keeps serving the frontend.
set -e

if [ ! -f .env.local ]; then
  cat > .env.local <<'PREVIEW'
EB44_BACKEND_PROXY="https://teachertranslate.eb44.app"
VITE_BASE44_APP_ID="69fc81cf4f6a0ae5ab617e2b"
VITE_BASE44_BACKEND_URL="http://localhost:5173"
VITE_BASE44_APP_BASE_URL=""
APP_ID="69fc81cf4f6a0ae5ab617e2b"
MONGO_URL="mongodb://localhost:27017"
MONGO_DB="teachertranslate"
BASE_URL="http://localhost:5173"
FRONTEND_DIR="dist"
ESCAPEBASE44_DEV_FUNCTIONS_BASE_URL="http://localhost:8002"
BASE44_ORIGINAL_APP_ID="69fc81cf4f6a0ae5ab617e2b"
SERVICE_PRINCIPAL_ID="16da470c-867e-4fbc-b730-d4fdf0800883"
EMAIL_FROM="no-reply@teachertranslate.com.au"
BASE44_FALLBACK_URL="https://base44.app"
LLM_PROVIDER="openrouter"
STORAGE_PROVIDER="s3"
S3_BUCKET="eb44-assets"
S3_REGION="ap-southeast-2"
S3_ENDPOINT_URL="https://toeynygydmamcxnxakhb.storage.supabase.co/storage/v1/s3"
S3_PUBLIC_URL="https://toeynygydmamcxnxakhb.storage.supabase.co/storage/v1/object/public/eb44-assets"
PREVIEW
  echo "[dev] .env.local missing — wrote a preview-mode fallback that proxies /api to the live backend."
  echo "[dev] For full local dev, download your real .env.local (see README.md)."
fi

set -a
. ./.env.local
set +a

# Optional SSH tunnel to a remote Mongo (only when EB44_BOX_HOST is set and
# MONGO_URL points at the box's internal address).
if [ -n "${EB44_BOX_HOST:-}" ] && printf %s "$MONGO_URL" | grep -q '@mongo:27017'; then
  mkdir -p .escapebase44/dev/.cache
  printf '%b\n' "$EB44_SSH_PRIVATE_KEY" | tr -d '\r' > .escapebase44/dev/.cache/box_key
  chmod 600 .escapebase44/dev/.cache/box_key
  pkill -f '^sh .escapebase44/dev/.cache/mongo-tunnel.sh' 2>/dev/null || true
  pkill -f '^ssh .*-L 127.0.0.1:27017:127.0.0.1:27017' 2>/dev/null || true
  printf '%s\n' 'while :; do ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ExitOnForwardFailure=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=2 -i .escapebase44/dev/.cache/box_key -N -L 127.0.0.1:27017:127.0.0.1:27017 "$EB44_BOX_USER@$EB44_BOX_HOST"; sleep 3; done' > .escapebase44/dev/.cache/mongo-tunnel.sh
  sh .escapebase44/dev/.cache/mongo-tunnel.sh &
  trap 'pkill -f "^sh .escapebase44/dev/.cache/mongo-tunnel.sh" 2>/dev/null || true; pkill -f "^ssh .*-L 127.0.0.1:27017:127.0.0.1:27017" 2>/dev/null || true' EXIT
  export MONGO_URL="$(printf %s "$MONGO_URL" | sed 's/@mongo:27017/@127.0.0.1:27017/')&directConnection=true"
fi

# Ensure the frontend dir exists (vite serves the frontend; uvicorn's static
# mount reads from here in a full local run).
mkdir -p "${FRONTEND_DIR:-dist}"
[ -f "${FRONTEND_DIR:-dist}/index.html" ] || printf '%s' '<!doctype html><title>dev</title>' > "${FRONTEND_DIR:-dist}/index.html"

# Boot everything. Backend processes that aren't installed in this
# environment (uv/deno) exit immediately; `wait` only blocks on vite, which
# keeps the dev server alive for the frontend.
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --env-file .env.local 2>/dev/null &
deno run --allow-all .escapebase44/dev/supervisor.ts 2>/dev/null &
EB44_ACTORS_PORT=8004 EB44_ACTORS_DIR=base44/actors EB44_BACKEND_URL=http://localhost:8000 deno run --allow-all --unstable-worker-options --watch=base44/actors --config .escapebase44/actors-host/deno.json .escapebase44/actors-host/host.ts 2>/dev/null &
vite --config vite.config.dev.ts &
wait
