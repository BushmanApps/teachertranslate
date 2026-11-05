from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    MONGO_URL: str
    MONGO_DB: str

    APP_ID: str
    # LEGACY canonical-address input. Deployments generated before the
    # single-home architecture (2026-08-31) supply the app's primary URL here;
    # newer ones supply nothing — the canonical lives in the app's own
    # settings document and per-request surfaces derive from the arrival
    # host (app/core/addresses.py). When both exist, the settings field wins.
    BASE_URL: str | None = None

    APP_JWT_SECRET: str
    SERVICE_JWT_SECRET: str
    SERVICE_PRINCIPAL_ID: str  # stable UUID, used as sub/client_id in service tokens

    # Shared secret for the scheduled-automation trigger endpoint
    # (/api/internal/fire-automation/{id}). The cron infra (pg_cron job SQL on
    # Supabase, Deno.cron handler on Deno Deploy) sends this in the
    # X-Eb44-Cron-Secret header. The cron is just a trigger — the backend
    # builds the actual Base44-shaped automation request. This keeps payload
    # construction in one place (matching Base44's architecture: their
    # EventBridge worker is purely a trigger; payload comes from their
    # backend).
    EB44_CRON_SECRET: str

    CORS_ORIGINS: str = "*"
    REALTIME_ENABLED: bool = False

    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    # Set when this deployment rides EB44's shared Google client (the
    # migrator seeds it alongside the shared GOOGLE_CLIENT_ID/SECRET): the
    # OAuth redirect_uri to use INSTEAD of {BASE_URL}/api/apps/auth/callback.
    # The shared client's only registered redirect URIs live on auth.eb44.app,
    # whose forwarder relays the callback here by reading state.domain —
    # Base44's own central-callback mechanism. Ignored in custom mode
    # (google_oauth_mode == "custom" means the builder's own client, whose
    # redirect URI is this deployment directly).
    GOOGLE_OAUTH_CALLBACK_URL: str | None = None

    # Microsoft social login (auth_config.enable_microsoft_login). Always
    # EB44's shared Entra client — Base44 has no bring-your-own mode for
    # Microsoft (their CLI: custom credentials are Google-only), so neither
    # do we. Callback URL points at the auth.eb44.app forwarder, same
    # mechanism as GOOGLE_OAUTH_CALLBACK_URL above; unset falls back to
    # {BASE_URL}/api/apps/auth/microsoft/callback (a directly-registered
    # redirect URI, e.g. local dev against a test client).
    MICROSOFT_CLIENT_ID: str | None = None
    MICROSOFT_CLIENT_SECRET: str | None = None
    MICROSOFT_OAUTH_CALLBACK_URL: str | None = None

    FACEBOOK_CLIENT_ID: str | None = None
    FACEBOOK_CLIENT_SECRET: str | None = None
    APPLE_WEB_CLIENT_ID: str | None = None
    APPLE_WEB_TEAM_ID: str | None = None
    APPLE_WEB_KEY_ID: str | None = None
    APPLE_WEB_PRIVATE_KEY_P8: str | None = None

    # Which email service sends every email the app produces (auth OTP /
    # reset / invite, the SendEmail integration, workflow send_email).
    #   resend — our shared account during the migration window (the default)
    #   ses    — Amazon SES on the app owner's own AWS account (the HIPAA
    #            lineup: Resend signs no BAA, SES is HIPAA-eligible). The
    #            sending identity is the app's own domain, verified by the
    #            migration; the keys are the owner's IAM user.
    EMAIL_PROVIDER: str = "resend"
    RESEND_API_KEY: str | None = None
    EMAIL_FROM: str = ""
    SES_REGION: str | None = None
    SES_ACCESS_KEY_ID: str | None = None
    SES_SECRET_ACCESS_KEY: str | None = None
    # Amazon's own endpoint of the region when unset; the gates point it at a stand-in.
    SES_ENDPOINT_URL: str | None = None
    # EMAIL_PROVIDER=gmail (the Google HIPAA lineup): the owner's Workspace
    # account the key acts as, and the service-account key file (base64),
    # authorized under domain-wide delegation — providers/email/gmail.py.
    GMAIL_SENDER_USER: str | None = None
    GMAIL_SERVICE_ACCOUNT_JSON_B64: str | None = None

    # How the emails the APP's own code produces (the SendEmail integration,
    # the workflows send_email activity) reach their recipient:
    #   inline — the message is the email (the default; Base44's behaviour)
    #   link   — the message is stored on this server and the email is a
    #            one-line notice with a button that opens it here, over
    #            HTTPS (core/mail/link.py + modules/mail; chosen once at
    #            startup like the transport itself — main.py). The HIPAA lineup: no
    #            patient data ever sits in a mailbox, so the sender needs no
    #            BAA. Sign-in codes, password resets and invitations carry no
    #            app data and stay inline whatever this says.
    EMAIL_DELIVERY: str = "inline"

    # Which service answers every LLM call (InvokeLLM, ExtractData,
    # GenerateImage, GenerateVideo, GenerateSpeech, TranscribeAudio, agents,
    # the AI gateway, workflow LLM steps):
    #   openrouter — Base44's model aliases resolve to the same models Base44
    #                serves, via OpenRouter (the default; core/llm.py)
    #   openai     — every alias resolves to ONE GPT model on the owner's own
    #                OpenAI key, under OpenAI's BAA (the HIPAA lineup). No web
    #                grounding, no agent web search, no video generation —
    #                none of the three has a BAA path (generate_video.py).
    LLM_PROVIDER: str = "openrouter"
    OPENROUTER_API_KEY: str | None = None
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENAI_API_KEY: str | None = None
    SERPAPI_API_KEY: str | None = None

    # App-user session length. 90 days = Base44 parity (the SDK keeps the
    # token in localStorage); the HIPAA lineup sets 24 h ("automatic logoff").
    APP_TOKEN_TTL_SECONDS: int = 90 * 24 * 60 * 60

    # Can this process finish work AFTER an HTTP response has been returned?
    # True only where a long-lived server owns the process (the VPS providers
    # run uvicorn; `AppProvider.runsUvicorn` is the same fact on the migrator
    # side). On serverless the container is frozen the moment the response is
    # sent, so a fire-and-forget task is suspended mid-flight — measured on a
    # live Vercel deployment 2026-08-22: kicked workflow runs froze inside their
    # backend-function call, the next tick found an expired lease in `invoking`
    # and FAILED them, and five of those auto-deactivate the workflow. When
    # false the workflows engine advances runs only inside the minutely tick,
    # which is synchronous and therefore safe on every host.
    EB44_BACKGROUND_TASKS: bool = False
    # The platform zone every migrated app gets its permanent `{slug}.` address
    # under. The VPS TLS gate authorizes any host in it (tls_check.py).
    EB44_BASE_DOMAIN: str = "eb44.app"

    # Deployment identity marker for the workflows `app_publish` trigger —
    # post-migration, "published" means a deployment going live. Vercel
    # deploys carry VERCEL_DEPLOYMENT_ID natively; VPS deploys get this
    # written into the backend .env by the runner (the git sha). Absent (local
    # dev) = no publish events. See modules/workflows/lifespan.py.
    EB44_BUILD_MARKER: str | None = None

    # No default — must be set explicitly when the deployment has S3/R2
    # provisioned. With a default of "s3", the lifespan init would
    # instantiate S3StorageProvider(bucket=None, region=None, ...) which
    # succeeds silently then crashes inside boto's put_object with a
    # NoneType bucket error. With STORAGE_PROVIDER=None the lifespan
    # leaves storage_provider as None and the upload handlers correctly
    # emit "Storage provider not configured" (500).
    STORAGE_PROVIDER: str | None = None
    S3_ENDPOINT_URL: str | None = None
    S3_PUBLIC_URL: str | None = None
    S3_BUCKET: str | None = None
    S3_REGION: str | None = None
    S3_ACCESS_KEY_ID: str | None = None
    S3_SECRET_ACCESS_KEY: str | None = None
    # Session-token S3 auth (Supabase Storage: ref + anon key + service_role
    # JWT). Unset for real keypair providers (R2, S3).
    S3_SESSION_TOKEN: str | None = None
    # Vercel Blob (STORAGE_PROVIDER == "vercel-blob") — its own REST API,
    # driven by a single read-write token.
    BLOB_READ_WRITE_TOKEN: str | None = None
    BLOB_PUBLIC_URL: str | None = None

    # In-app purchases (the eb44/iap module — see MOBILE.md). iOS needs no
    # credentials (StoreKit transactions verify offline against Apple's
    # pinned root). Android needs a Play service account, base64-encoded
    # because the raw JSON is multi-line and .env files can't carry that.
    # MOBILE_BUNDLE_ID only when the user changed the kit's default
    # (com.eb44.app<APP_ID>) before submitting to the stores.
    IAP_GOOGLE_SA_JSON_B64: str | None = None
    MOBILE_BUNDLE_ID: str | None = None
    # The app's credit packs (consumable purchases): which products add how
    # many credits to which number field of the buyer's User record, as
    # `product=field+amount, …` — a fact in .escapebase44/config.json
    # (app/modules/iap/packs.py reads it).
    IAP_CREDIT_PACKS: str | None = None
    # The ids the stores know the app by, one per platform — the mobile
    # kit's facts (core/mobile_identity.py reads them; MOBILE_BUNDLE_ID is
    # the older single name, kept as the fallback).
    MOBILE_IOS_BUNDLE_ID: str | None = None
    MOBILE_ANDROID_PACKAGE: str | None = None
    # Links to the app's own address open in the installed app — the app's
    # mobile/native.json `links`, told to the backend by the runner. The
    # Android app's upload certificate (base64 DER) is a fact the App Store
    # card writes with the upload key; Google Play's own signing certificate
    # is read from Play. core/mobile_identity.py derives the two files the
    # phones read from these.
    MOBILE_APP_LINKS: bool = False
    MOBILE_ANDROID_UPLOAD_CERT: str | None = None
    # AdMob app ids, one per platform (facts from the App Store card): the
    # publisher inside them is what /app-ads.txt names.
    ADMOB_APP_ID_IOS: str | None = None
    ADMOB_APP_ID_ANDROID: str | None = None

    # Push notifications (app/modules/push): the owner's APNs auth key +
    # Apple team, and the owner's Firebase service account. Each platform is
    # inert while its credential is unset — the app never asks anyone for
    # permission then. Collected post-migration on the App Store card.
    APNS_KEY_P8: str | None = None
    APNS_KEY_ID: str | None = None
    APPLE_TEAM_ID: str | None = None
    FCM_SERVICE_ACCOUNT_JSON_B64: str | None = None

    # Agent messaging channels (app/modules/agents/channels/). Base44 relays
    # WhatsApp/Telegram through its own servers on pool-assigned numbers; a
    # migrated app relays through its OWN number/bot, so the credentials are
    # the app owner's. Each channel is inert while its credentials are unset —
    # the connect endpoints then behave exactly as Base44's do for an
    # unconnected agent. Collected post-deploy (the migration never talks to
    # either platform), same as the AI keys and the IAP service account.
    WHATSAPP_ACCESS_TOKEN: str | None = None
    WHATSAPP_PHONE_NUMBER_ID: str | None = None
    # Only for verifying inbound X-Hub-Signature-256 — never sent anywhere.
    WHATSAPP_APP_SECRET: str | None = None
    TELEGRAM_BOT_TOKEN: str | None = None

    # Where a migrated user's FIRST login is forwarded to import their
    # password (auth/login.py — every migrated user starts with no hash).
    # Empty = never forward: every existing user resets their password once
    # instead (the HIPAA lineup — a login hop through Base44 has no BAA).
    # Default EMPTY: the migration writes the URL as a config fact on
    # deployments that keep the first-login password import (an empty value
    # cannot travel through the runtime-env composer — empty means "remove
    # this key" there — so the OFF state has to be the default).
    BASE44_FALLBACK_URL: str = ""
    BASE44_ORIGINAL_APP_ID: str | None = None

    FRONTEND_DIR: str
