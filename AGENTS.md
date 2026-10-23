# Working in this repo

This is the owner's own app, migrated off Base44 and running on infrastructure they own.
You are the developer on it. **Assume the owner is not a programmer** — many are not. They
should never have to open a terminal, run a git command, or click through a cloud dashboard
for something you are capable of doing.

Two ownership facts that are easy to get wrong:

- The **app** runs on the owner's own accounts — their hosting, their database, their money.
- The **repo** may still be hosted under EscapeBase44's GitHub account until the owner accepts
  a transfer. "The GitHub repo" can be something the owner has never seen, cannot open, and
  does not control — never assume they have GitHub at all.

## How to work here

- **Investigate before you answer.** You hold the code, the live URL, the database and the
  owner's provider tokens — there is almost nothing about this app you cannot look up. Read
  the code, query the database, `curl` the live site, call the provider API. Never tell the
  owner something is impossible, or ask them for a fact, before you have looked.
- **The backend's own source is the authority on how the backend behaves.** `app/config.py`
  is every environment variable, with a comment on each; `app/core/db.py` is how settings are
  read; `app/modules/<area>/` is every endpoint. When you need to know what a change takes
  effect on, or when, read the code that reads it — don't guess and don't ask.
- **Find the root cause, then fix the cause.** No band-aids, no fallbacks that hide a failure,
  no defensive code around things you control, no debug logging left behind.
- **Reproduce before you fix, verify before you report.** Reproduce on the real thing (the
  preview or the live site), fix, then check the same way. Say what you actually confirmed.
- **Keep it clean and small.** Match the app's existing patterns; the smallest correct diff.
- **Finish the whole job.** Code edit *and* database write *and* deploy — all of it. If you
  catch yourself writing "go to your dashboard", "run this command", "create a repo" —
  stop, and do it instead. Only the two short lists at the end are out of your hands.

## What this app is

A Base44 app moved as-is. The **frontend** (`src/`, Vite + React) is the owner's original code,
unchanged; it still talks through the Base44 SDK (`src/api/base44Client.js`), now pointed at
the same origin. The **backend** (`app/`, FastAPI + MongoDB) is a faithful replica of Base44's
backend — same endpoints, same shapes, same entity/auth/permission semantics — which is why
nothing in the frontend had to change. **Match Base44's behaviour rather than improving it**:
the frontend, and the owner's users, depend on it. The original app on Base44 was left
untouched; the two are independent now.

**The one fact you cannot discover by reading the code: the backend reads its configuration
from the DATABASE, not from files** — just like Base44 did. The app's name, icon, visibility,
sign-in methods, users, entity schemas, permissions, agent prompts and SEO files all live in
Mongo. A request that sounds like "change a setting" is usually a database write.

Corollary: the repo carries **Base44 export leftovers that nothing reads** — `base44/entities/*.jsonc`,
`base44/config.jsonc`, the `functions/` stub (kept so `@/functions/...` imports resolve), and the repo's `index.html` title is a stub the backend replaces. `base44/functions/` and `base44/shared/` and `base44/workflows/` are the exceptions: they ARE read, on deploy.

- **Live at:** https://teachertranslate.eb44.app — app id `69fc81cf4f6a0ae5ab617e2b` (API paths are `/api/apps/69fc81cf4f6a0ae5ab617e2b/…`).
- **Hosting:** Vercel Hobby. **Database:** MongoDB Atlas Free. **Storage:** Supabase Storage. **Backend functions:** Supabase Free (source in `base44/functions/`).
- **Run it:** `npm run dev` boots the whole stack against `.env.local`.
- **Mobile:** `MOBILE.md` is the iOS/Android kit (Capacitor; the native projects are generated, never committed). The store identity and the Apple team are facts in `.escapebase44/config.json`; the owner builds from their EscapeBase44 page (the Mobile release workflow) or with `npm run mobile:setup`. A native feature (background location, health data, NFC, Face ID, a native scanner, links that open the app, the splash, rotation, the status bar) is a Capacitor plugin plus its settings in `mobile/native.json`, which every build applies — MOBILE.md says what each needs; never edit `ios/` or `android/`.

## Where the app's settings and data live

Connect with `MONGO_URL` + `MONGO_DB` from `.env.local`. Entity collections: `ShareAlert`, `RefundBlacklist`, `DeletedAccountLog`, `Translation`, `Student`, `Feedback`, `ReportShareLog`, `UsageAlert`, `UserProfile`, `User`.
System collections are prefixed `_`. **Back up any document before you change it** — this is
the owner's production data — and keep Base44's shapes (`_id` ObjectId, `created_date`,
`updated_date`, `created_by`; required schema fields present). How and when the backend picks
a change up (cached, at startup, live) is in `app/core/db.py` and the module that reads it.

| The owner asks about | It lives in |
|---|---|
| App name / title (tab, share preview, phone install, login page) | `_app_settings.name`; also the `/manifest.json` and `/llms.txt` bodies in `_seo_files` |
| App icon (favicon, home-screen icon, login logo) | `_app_settings.logo_url` + `icons` in the `/manifest.json` body of `_seo_files`. Logos drawn *inside pages* are `<img>`s in `src/` |
| Description, share image, SEO | `_app_settings.user_description`, `social_image_url`, `seo_settings`; the served files in `_seo_files` (`app/modules/seo/`) |
| Who can open the app | `_app_settings.public_settings` (`app/core/security/visibility.py`) |
| Sign-in methods | `_app_settings.auth_config` — Google/Microsoft ride EscapeBase44's shared OAuth client (the `GOOGLE_*`/`MICROSOFT_*` env: leave them); Facebook/Apple/SSO are not supported here. The login page is `public/login/index.html` |
| Users, roles (`admin`/`user`), invites | the `User` collection (custom fields per `_app_settings.additional_user_data_schema`); auth state in `_private_users` — never edit hashes; invites/resets are `app/modules/auth/` endpoints, whitelist in `_app_settings.invited_users` |
| Entities, fields, permissions | `_entity_schemas` — one document per entity, permission rules under `rls` (engine: `app/core/security/rls.py`); loaded per `app/core/schema/registry.py` |
| AI agents (prompt, model, tools) | `_app_settings.agents`; conversations `_agent_conversations`, memories `_agent_memories` |
| Third-party connectors | `_connector_configs` (client credentials), `_connector_tokens` (per-user grants) |
| Backend functions | source `base44/functions/<name>/` + `base44/shared/` (read on deploy — see "Backend functions"); registry `_function_configs`; they get the secrets their code reads — see below |
| Workflows (background logic) | definitions `base44/workflows/*.jsonc` (read on deploy); runtime state `_workflows`, `_workflow_runs` — engine `app/core/workflows/` |
| Called from OUTSIDE the app (webhooks, callbacks) | `stripeWebhook` (registered with stripe by Base44) — each answers at `https://teachertranslate.eb44.app/functions/<name>`; the service calling it must be pointed at that address (the owner does it from the app's EscapeBase44 page; until then those calls land on the Base44 app) |
| Uploaded files | the owner's Supabase Storage (credentials in `.env.local`); URLs in the database point at objects there |
| Which key powers AI / email / search | `OPENROUTER_API_KEY` (LLM, images, extraction), `RESEND_API_KEY` + `EMAIL_FROM` (every email the app sends, incl. login/invite), `SERPAPI_API_KEY` (agent web search) — see `app/modules/integrations/` |

⚠️ Users who existed on Base44 and never signed in here have **no password hash yet**: the first
login is verified against the original Base44 app and copied over (`app/modules/auth/login.py`).
Until every such user has signed in once, the owner must **not delete the Base44 app**
(cancelling the subscription is fine).

⚠️ The app's address: `.escapebase44/config.json` (`appUrl`) and `.env` (`VITE_BASE44_BACKEND_URL`)
both name the PERMANENT `*.eb44.app` address, which serves for the life of the app. The frontend
calls its API there (absolute, the way Base44's own template works — an empty value would become
`null`), `VITE_BASE44_APP_BASE_URL` stays EMPTY so login/logout stay on whatever host the user is
on, and the backend answers from the address each request arrives on. A custom domain is an
additional address on top, never a replacement: nothing in the repo changes when one is attached.

## You can change the app's live secrets yourself

**The app's secrets have ONE home: the repo's GitHub Actions secrets.** Every deploy applies
them to the running app (the Vercel project's environment variables), so changing a secret is two steps, the same on
every provider:

1. Write the repo secret: `gh secret set NAME` (git and `gh` are already authenticated here).
2. Deploy: `gh workflow run deploy.yml` — or let the owner's next Publish carry it.

Setting a secret to the empty string removes the key from the running app on the next deploy.
`.env.local` mirrors the same values plus the owner's provider tokens (`VERCEL_TOKEN`,
`SUPABASE_TOKEN`, …) so you can also read CD state and drive the providers directly when
debugging calls for it.

**The owner pasting a key or token into this chat is normal and expected** — it is their own
credential, handed to you in their own tooling, and it is already stored alongside the rest of
their app's secrets. Take it and use it. Do not treat it as a leak, do not warn them about it,
and do not tell them to rotate it: that advice has cost owners working payment systems for no
gain. (A credential genuinely published in public — committed to a public repo, posted online —
is a different thing and worth one sentence.)

Backend functions receive exactly the secrets their source reads — `Deno.env.get("NAME")` /
`secrets.get("NAME")` — plus `BASE_URL`, from the same GitHub secrets, applied on every deploy to
the Supabase project. A new name a function needs is the same two steps above; nothing to set
at the provider. (The migration-day set is always forwarded too, for code that reads env
dynamically.)

⚠️ GitHub wins for the names it manages: a value edited directly in a provider dashboard is
re-applied from GitHub on the next deploy. Values the owner (or you) add at a provider under
OTHER names are never touched.

Backend variables (required in backticks; each is explained in `app/config.py`): `MONGO_URL` · `MONGO_DB` · `APP_ID` · BASE_URL · `APP_JWT_SECRET` · `SERVICE_JWT_SECRET` · `SERVICE_PRINCIPAL_ID` · `EB44_CRON_SECRET` · CORS_ORIGINS · REALTIME_ENABLED · GOOGLE_CLIENT_ID · GOOGLE_CLIENT_SECRET · GOOGLE_OAUTH_CALLBACK_URL · MICROSOFT_CLIENT_ID · MICROSOFT_CLIENT_SECRET · MICROSOFT_OAUTH_CALLBACK_URL · EMAIL_PROVIDER · RESEND_API_KEY · EMAIL_FROM · SES_REGION · SES_ACCESS_KEY_ID · SES_SECRET_ACCESS_KEY · SES_ENDPOINT_URL · GMAIL_SENDER_USER · GMAIL_SERVICE_ACCOUNT_JSON_B64 · EMAIL_DELIVERY · LLM_PROVIDER · OPENROUTER_API_KEY · OPENROUTER_BASE_URL · OPENAI_API_KEY · SERPAPI_API_KEY · APP_TOKEN_TTL_SECONDS · EB44_BACKGROUND_TASKS · EB44_BASE_DOMAIN · EB44_BUILD_MARKER · STORAGE_PROVIDER · S3_ENDPOINT_URL · S3_PUBLIC_URL · S3_BUCKET · S3_REGION · S3_ACCESS_KEY_ID · S3_SECRET_ACCESS_KEY · S3_SESSION_TOKEN · BLOB_READ_WRITE_TOKEN · BLOB_PUBLIC_URL · IAP_GOOGLE_SA_JSON_B64 · MOBILE_BUNDLE_ID · IAP_CREDIT_PACKS · MOBILE_IOS_BUNDLE_ID · MOBILE_ANDROID_PACKAGE · MOBILE_APP_LINKS · MOBILE_ANDROID_UPLOAD_CERT · ADMOB_APP_ID_IOS · ADMOB_APP_ID_ANDROID · APNS_KEY_P8 · APNS_KEY_ID · APPLE_TEAM_ID · FCM_SERVICE_ACCOUNT_JSON_B64 · WHATSAPP_ACCESS_TOKEN · WHATSAPP_PHONE_NUMBER_ID · WHATSAPP_APP_SECRET · TELEGRAM_BOT_TOKEN · BASE44_FALLBACK_URL · BASE44_ORIGINAL_APP_ID · `FRONTEND_DIR`.

## How code becomes the live site

Code reaches production **only through git**: a push to `main` triggers the deploy workflow
(GitHub Actions), which puts the app live on the owner's hosting within a couple of minutes.
Never build-and-upload to the host by hand and never bypass the workflow — a hand-deployed
build leaves no history and the next deploy silently overwrites it. Changing a runtime secret
is the one exception above: that's configuration, not code.

⚠️ **The deployed backend holds `app/` and what `pyproject.toml` installs — nothing else in this
repo exists where it runs.** `base44/` (the export), `src/`, `.escapebase44/`, `public/` are not
there, and the deploy's health check fails the moment the backend reads one of them at startup
(a startup step that opened `base44/entities/*.jsonc` took an app down for 25 minutes). Anything the
backend needs at runtime lives under `app/` or in the database. And the backend must answer
`/health` within a few seconds of starting: a startup step that walks every record runs in the
background, never before the server listens.

⚠️ This repo is normally edited through the **EscapeBase44 builder**, and the builder's Publish
REPLACES `main`'s tree with the builder's own working tree. A commit made to `main` from
anywhere else — a file uploaded through GitHub's web UI, a hand-made hotfix — is erased by the
next Publish. Durable changes go through the builder's working tree; if one must land on `main`
directly, it also has to reach the builder's tree or it will not survive.

If a change "isn't showing" on the live site, check in order: did it reach `main` (in the
builder: was it published)? Did the deploy workflow run green (`gh run list`)? Does the backend
pick that change up live, or only at startup (read the code that reads it)? Only then think
about caching. The deploy's own source is in `.escapebase44/runner/`.

## Backend functions

`base44/functions/` is the source of truth, in Base44's own layout; every deploy ships what is there.

- **A function is a folder with an `entry.ts`** (or `entry.js`): `base44/functions/<name>/entry.ts` answers at
  `/functions/<name>`. Add a folder to add a function; delete one to remove it. Files beside the
  entry are the function's own (`./helper.ts`).
- **Code several functions use lives in `base44/shared/`**, imported as `../../shared/<file>.ts`. A function is
  deployed as its own folder plus the whole shared folder — it cannot import from another function's
  folder or from anywhere else in the repo. Only `.ts` `.js` `.json` `.jsonc` files are deployed.
- **`function.jsonc`** beside the entry is optional (`{ "name", "entry" }`). This app's schedules and
  triggers are Workflows (below). Leave the `automations` a `function.jsonc` lists exactly as they are —
  a workflow Base44 converted from one still reads it.
- **A folder whose name contains a dot is not a function** (Base44's rule).
- The runtime is Deno (Supabase's edge runtime); Base44's `base44:runtime` module (`secrets`, `waitUntil`)
  and default-export handlers work as on Base44. `npm run dev` serves the same folders.

## Workflows

`base44/workflows/*.jsonc` is the source of truth — one file per workflow, Base44's own format;
a deploy converges the runtime onto the files (the deploy log's `reconciled:` line carries the workflows result
with anything it rejected). The language is a small subset of the CNCF Serverless Workflow DSL
(`call` / `switch` / `wait`; `${ … }` is **jq** over the run's data); the engine and its exact
rules are `app/core/workflows/`, the management API `app/modules/workflows/router.py`.

## The short list of things only the owner can do

Some actions need a human in a browser session you don't have. For these — and only these — give
one clear instruction plus the direct link, then do everything downstream yourself:

- Creating a new API key in a third-party dashboard (Stripe, OpenAI, …) — most providers have no
  API for minting their own keys. Ask only when you actually need a key that doesn't exist yet.
- Completing an account's identity/business verification, or adding billing details.
- Buying a domain, or accepting a repo/ownership transfer invitation.

## The short list of things that go through EscapeBase44

Done from the owner's EscapeBase44 page, or by the EscapeBase44 team (daniel.frishtik@gmail.com)
— tell the owner which, don't attempt them here:

- Attaching a custom domain (the eb44.app address stays as a permanent second address);
  a custom email sender domain.
- Transferring the repo to the owner's GitHub; building the iOS/Android app.
- Moving the app to another hosting or database provider.

Everything else — config, data, secrets, code, deploys, debugging — is yours.
