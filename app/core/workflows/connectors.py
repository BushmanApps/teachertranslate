"""Connector triggers — rebuilt as polling, because Base44's delivery cannot
be inherited.

WHAT BASE44 DOES (measured): a connector trigger is a provider-side
subscription Base44 owns — Gmail `watch()` against ITS Pub/Sub topic
(`projects/base44-integrations/subscriptions/gmailwebhookpush`, H §14.11b),
a Drive `changes.watch` / `files.watch` / Calendar `events.watch` push
channel (a customer's own runs + the parity lab, 2026-09-02: every fire
carries Google's five push-notification headers under `data._provider_meta`
and NOTHING else — Google pushes no body) — and it forwards the provider's
raw notification into every workflow subscribed to it: ONE channel per
resource, fanned out (three Drive workflows of one app received the same
resource-id and message-number in the same second). A `changes` / Calendar
channel is re-registered weekly (expiration = registration + 7 days on every
captured notification); a Drive FILE channel daily (+1 day — Google's
`files.watch` cap, measured on the lab's six file workflows). The message
number is Google's per-channel counter: a fresh channel starts in the
thousands and reaches the hundreds of millions after weeks — measured on both
a fresh lab channel and a customer's weeks-old ones it tracks the
MILLISECONDS elapsed since the channel's registration (~996/s on the lab's
file channel across six notifications), so ours is derived from exactly that.

None of that transfers with a migrated app: the subscriptions live in
Base44's GCP project, bound to Base44's OAuth client. So delivery is REBUILT
here as polling from the engine tick with the connector token the app
already holds, and the rest is replicated: one `_connector_channels` doc per
(integration, resource) carrying the cursor and the channel identity
(resource-id, registration, expiration, message-number — renewed weekly like
Base44's), one poll per channel per tick, one fire per subscriber whose
events match and whose condition admits. A payload is shape-faithful to the
captured one; the fields that named Base44's mechanism (the Pub/Sub
subscription, Google's channel ids) are SYNTHESIZED because no subscription
exists — they name OUR mechanism. The cost is latency: up to one tick (60s)
against Base44's measured ~15s push.

SUBSCRIBERS are both kinds Base44 has: workflow records (`_workflows`,
trigger_type connector — the workflows-mode app) and legacy connector
AUTOMATIONS (`_function_configs.automations[type=connector]` — the
automations-mode app; extracted + seeded since May, never fired until
2026-09-02). Both ride the same channel and the same adapter; only the
delivery envelope differs (core/automations.dispatch_connector builds the
documented automation body).

ADAPTERS: one per integration, each owning the events it serves, the channel
key for a subscriber, the cursor semantics and the payload shape. The
inventory is `contract.json`'s `events_by_integration` — the analysis
allowlist — and the engine gate asserts the two agree. An integration or
event outside the contract is precision-blocked at analysis, never a silent
no-op here. Only MEASURED integrations are in the table; the docs' catalog
(45 integration/event pairs) is the map of what still has to be measured
with a live connection per provider (research/divergence-chasing/
2026-09-02-connector-universe/HANDOFF.md).
"""

import base64
import logging
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from uuid import uuid4

import httpx
import orjson

from app.core import db
from app.core import addresses

from .contract import CONTRACT
from .engine import WORKFLOWS, create_run, kick
from .expressions import trigger_admits

logger = logging.getLogger("escapebase44.workflows")

CHANNELS = "_connector_channels"

# Overridable so the engine gate can point the pollers at a local stand-in.
GMAIL_API_BASE = "https://gmail.googleapis.com"
GOOGLE_API_BASE = "https://www.googleapis.com"
SUBSCRIPTION_NAME = "projects/escapebase44-selfhosted/subscriptions/gmail-poll"

# Base44 re-registers its provider channels weekly: every captured Drive
# `changes` / Calendar notification carried `x-goog-channel-expiration` =
# registration + 7 days (2026-09-02, 200 runs across two integrations). A
# Drive FILE channel expires after ONE day (the lab's six file workflows:
# every notification's expiration = registration + 1 day — Google's
# `files.watch` cap). Each adapter declares its own.
CHANNEL_TTL = timedelta(days=7)
FILE_CHANNEL_TTL = timedelta(days=1)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── subscribers ──

@dataclass
class Subscriber:
    kind: str                      # "workflow" | "automation"
    integration: str
    events: list[str]
    resource_id: str | None
    condition: object              # workflow: jq expression | automation: trigger_conditions
    doc: dict                      # the workflow record | the automation entry
    deployed_url: str | None = None  # automation: its function's URL
    function_name: str | None = None  # automation: its function's name (the `base44-function-name` header)


async def _collect_subscribers() -> list[Subscriber]:
    subs: list[Subscriber] = []
    workflows = await db.coll(WORKFLOWS).find({
        "status": "active",
        "trigger.config.trigger_type": "connector",
    }).to_list(length=1000)
    for w in workflows:
        cfg = w["trigger"]["config"]
        subs.append(Subscriber(
            kind="workflow",
            integration=str(cfg.get("integration_type") or ""),
            events=[str(e) for e in (cfg.get("events") or [])],
            resource_id=cfg.get("resource_id") or None,
            condition=(w.get("trigger") or {}).get("condition"),
            doc=w,
        ))
    async for fc in db.coll("_function_configs").find():
        deployed_url = fc.get("deployed_url")
        if not deployed_url:
            continue
        for auto in fc.get("automations", []):
            if auto.get("type") != "connector" or auto.get("is_active") is False:
                continue
            subs.append(Subscriber(
                kind="automation",
                integration=str(auto.get("integration_type") or ""),
                events=[str(e) for e in (auto.get("events") or [])],
                resource_id=auto.get("resource_id") or None,
                condition=auto.get("trigger_conditions"),
                doc=auto,
                deployed_url=deployed_url,
                function_name=str(fc.get("name") or ""),
            ))
    return subs


# ── channels ──

def _mint_resource_id() -> str:
    """Google's `x-goog-resource-id` is 27 url-safe base64 chars (20 bytes),
    e.g. `Mvxm040z5B635a1eFhD5OLaClBk` — same shape, ours."""
    return base64.urlsafe_b64encode(secrets.token_bytes(20)).decode().rstrip("=")


async def _ensure_channel(integration: str, key: str, ttl: timedelta = CHANNEL_TTL) -> dict:
    """Load (or register) the channel for (integration, key); renew its
    identity when its `ttl` is up — Base44 re-registers (weekly for
    `changes` / Calendar, daily for a Drive file), and every notification
    after a renewal carries the new channel's ids and a counter that starts
    over."""
    coll = db.coll(CHANNELS)
    now = _now()
    channel = await coll.find_one({"integration_type": integration, "key": key})
    if channel is None:
        channel = {
            "integration_type": integration,
            "key": key,
            "resource_id": _mint_resource_id(),
            "registered_at": now,
            "expires_at": now + ttl,
            # the last emitted message number — a monotonic guard over the
            # elapsed-ms derivation in _google_meta
            "message_number": 0,
            "cursor": {},
            "created_at": now,
            "updated_at": now,
        }
        result = await coll.insert_one(channel)
        channel["_id"] = result.inserted_id
    elif channel["expires_at"] <= now:
        await coll.update_one({"_id": channel["_id"]}, {"$set": {
            "resource_id": _mint_resource_id(),
            "registered_at": now,
            "expires_at": now + ttl,
            "message_number": 0,
            "updated_at": now,
        }})
        channel = await coll.find_one({"_id": channel["_id"]})
    return channel


async def _save_channel(channel: dict) -> None:
    # `last_error` is the one field a caller may add: a push subscription that
    # cannot be created is a trigger that will never fire, and the channel is
    # the only place that says so (core/workflows/push.py).
    await db.coll(CHANNELS).update_one({"_id": channel["_id"]}, {"$set": {
        "cursor": channel["cursor"],
        "message_number": channel["message_number"],
        "updated_at": _now(),
        **({"last_error": channel["last_error"]} if channel.get("last_error") else {}),
    }})


def _google_meta(channel: dict, *, state: str, resource_uri: str) -> dict:
    """The five headers Google's push notification carries — the ENTIRE
    payload Base44 forwards for its Drive / Calendar triggers (measured on
    200 customer runs + 19 lab runs). The message number is the channel's
    age in milliseconds (measured: a fresh channel's notifications read
    236743 at +237.7 s, 407139 at +413 s; a weeks-old channel's read in the
    hundreds of millions), kept strictly increasing per channel."""
    elapsed_ms = int((_now() - channel["registered_at"]).total_seconds() * 1000)
    channel["message_number"] = max(channel["message_number"] + 1, elapsed_ms)
    return {
        "x-goog-resource-id": channel["resource_id"],
        "x-goog-resource-state": state,
        "x-goog-resource-uri": resource_uri,
        "x-goog-message-number": str(channel["message_number"]),
        "x-goog-channel-expiration": format_datetime(
            channel["expires_at"].replace(tzinfo=timezone.utc), usegmt=True),
    }


# ── adapters ──

@dataclass
class Event:
    names: set[str]   # the subscribed event names this occurrence satisfies
    data: dict
    type: str         # the payload's `event_type` — derived from the provider's
                      # state, not from the subscription (a Drive catch-all
                      # `file` subscriber receives `file.update`; measured)


class Adapter:
    integration: str = ""
    events: frozenset[str] = frozenset()
    channel_ttl: timedelta = CHANNEL_TTL

    def channel_keys(self, sub: Subscriber) -> set[str]:
        raise NotImplementedError

    async def poll(self, channel: dict, key: str, http: httpx.AsyncClient,
                   headers: dict) -> list[Event]:
        """Advance the channel's cursor; return the events since the last
        poll (empty on baseline). Mutates `channel["cursor"]`; the caller
        persists it."""
        raise NotImplementedError


class GmailAdapter(Adapter):
    """`mailbox` (the only Gmail event — the validator names it; Base44's own
    description: "Watch for mailbox changes (new messages, label changes,
    etc.)"). Base44's watch() is on the INBOX label unless `resource_id`
    names labels (a comma-separated list, docs). Cursor = a Gmail history id;
    the payload is the measured Pub/Sub passthrough plus Base44's enrichment
    (H §14.11b). Measured on the lab 2026-09-02 (7 runs): `mailbox` fires on
    EVERY history change on the watched label — a label-only change fires
    with `has_new_messages: false, new_message_ids: []` — so the poll reads
    history WITHOUT a type filter and fires on any record; the ids are the
    `messagesAdded` ones. (Base44's at-least-once duplicate deliveries and
    its cursor-less first delivery — `true` with an empty id list — are
    artifacts of its shared Pub/Sub cursor, not information; a migrated app
    always has its own cursor here.)"""
    integration = "gmail"
    events = frozenset({"mailbox"})

    def channel_keys(self, sub: Subscriber) -> set[str]:
        return {f"mailbox:{sub.resource_id or 'INBOX'}"}

    async def poll(self, channel, key, http, headers):
        cursor = channel["cursor"]
        labels = key.split(":", 1)[1].split(",")
        if cursor.get("history_id") is None:
            # First poll establishes the baseline; nothing fires for mail that
            # predates the connection (Base44's watch starts at registration too).
            profile = await http.get(f"{GMAIL_API_BASE}/gmail/v1/users/me/profile", headers=headers)
            profile.raise_for_status()
            body = profile.json()
            cursor["history_id"] = str(body["historyId"])
            cursor["email_address"] = body.get("emailAddress")
            return []
        start = cursor["history_id"]
        message_ids: list[str] = []
        records = 0
        newest = start
        for label in labels:
            resp = await http.get(
                f"{GMAIL_API_BASE}/gmail/v1/users/me/history", headers=headers,
                params={"startHistoryId": start, "labelId": label},
            )
            if resp.status_code == 404:
                # Gmail expires history ids (~a week of inactivity). Re-baseline
                # from the profile; the gap is unrecoverable and logged.
                logger.warning("gmail history cursor %s expired (%s) — re-baselining", start, key)
                cursor["history_id"] = None
                return []
            resp.raise_for_status()
            body = resp.json()
            newest = max(newest, str(body.get("historyId", start)), key=int)
            for record in body.get("history", []):
                records += 1
                for added in record.get("messagesAdded", []):
                    mid = added.get("message", {}).get("id")
                    if mid and mid not in message_ids:
                        message_ids.append(mid)
        cursor["history_id"] = newest
        if not records:
            return []
        return [Event({"mailbox"}, _gmail_payload(
            message_ids, previous_history_id=start, history_id=newest,
            email_address=cursor.get("email_address")), "mailbox")]


class GoogleDriveChangesAdapter(Adapter):
    """`changes` — "any change in the drive". Base44 registers `changes.watch`;
    Google then pushes `x-goog-resource-state: change` with the watch's page
    token in the resource URI (every one of a customer's 150 captured runs).
    Cursor = a changes page token; one fire per poll that sees ≥1 change
    (Google pushes 1–2 notifications per change — the lab's create and
    content upload each produced two `changes` runs seconds apart — and the
    duplicates carry nothing; one fire per poll is the honest analogue).

    The file-scoped events (`file`, `file.update`, `file.trash`,
    `file.untrash`, `file.delete` — `files.watch`, resource_id = the file)
    live on GoogleDriveFileAdapter: a different channel, a different
    expiration, a state-derived event name."""
    integration = "googledrive"
    events = frozenset({"changes"})

    def channel_keys(self, sub: Subscriber) -> set[str]:
        return {"changes"} if "changes" in sub.events else set()

    async def poll(self, channel, key, http, headers):
        cursor = channel["cursor"]
        if cursor.get("page_token") is None:
            resp = await http.get(f"{GOOGLE_API_BASE}/drive/v3/changes/startPageToken", headers=headers)
            resp.raise_for_status()
            token = str(resp.json()["startPageToken"])
            cursor["page_token"] = token
            # the token the channel was registered with — Google echoes it in
            # every notification's resource URI for the channel's whole life
            cursor["watch_page_token"] = token
            return []
        page = cursor["page_token"]
        seen = 0
        while True:
            resp = await http.get(f"{GOOGLE_API_BASE}/drive/v3/changes", headers=headers, params={
                "pageToken": page, "pageSize": 1000,
                "fields": "nextPageToken,newStartPageToken,changes(fileId,changeType,removed)",
            })
            if resp.status_code == 400:
                # an invalid/expired page token (Google: "Invalid Value") — re-baseline
                logger.warning("drive changes cursor %s rejected — re-baselining", page)
                cursor["page_token"] = None
                return []
            resp.raise_for_status()
            body = resp.json()
            seen += len(body.get("changes") or [])
            if body.get("nextPageToken"):
                page = body["nextPageToken"]
                continue
            cursor["page_token"] = str(body.get("newStartPageToken") or page)
            break
        if not seen:
            return []
        meta = _google_meta(channel, state="change", resource_uri=(
            f"{GOOGLE_API_BASE}/drive/v3/changes?alt=json&pageToken={cursor['watch_page_token']}"))
        return [Event({"changes"}, {"_provider_meta": meta}, "changes")]


# The Drive file events, keyed by the `x-goog-resource-state` Google reports
# for the file (measured on the lab 2026-09-02, six subscriptions on one file
# through metadata update / content upload / trash / untrash / permanent
# delete). Base44 derives the payload's `event_type` from that STATE, not
# from the subscription: a catch-all `file` subscriber received
# `file.update` / `file.trash` / `file.untrash` for those states and plain
# `file` for `remove`; and NO subscription fired `file.delete` on the
# permanent delete — Google reports it as `remove`, which Base44 never maps
# to `file.delete`. Replicated exactly: `file.delete` is subscribable and
# never fires on a removal; the catch-all is what sees the deletion.
DRIVE_FILE_STATES: dict[str, tuple[str, frozenset[str]]] = {
    #  google state: (payload event_type, the subscriptions it satisfies)
    "update": ("file.update", frozenset({"file", "file.update"})),
    "trash": ("file.trash", frozenset({"file", "file.trash"})),
    "untrash": ("file.untrash", frozenset({"file", "file.untrash"})),
    "remove": ("file", frozenset({"file"})),
}
DRIVE_FILE_FIELDS = "id,modifiedTime,version,md5Checksum,trashed"


class GoogleDriveFileAdapter(Adapter):
    """The file-scoped Drive events — `files.watch(resource_id)` on Base44,
    a one-day channel (measured: every notification's expiration =
    registration + 1 day) whose resource URI is the file's own
    (`…/drive/v3/files/{id}?alt=json`). Cursor = a snapshot of the file's
    metadata; each poll diffs `files.get` against it: a version / content /
    metadata change is `update`, the `trashed` flag flipping is `trash` /
    `untrash`, a 404 is `remove` — after which the file is gone and the
    channel goes quiet for good."""
    integration = "googledrive"
    events = frozenset({"file", "file.update", "file.trash", "file.untrash", "file.delete"})
    channel_ttl = FILE_CHANNEL_TTL

    def channel_keys(self, sub: Subscriber) -> set[str]:
        if sub.resource_id and any(e in self.events for e in sub.events):
            return {f"file:{sub.resource_id}"}
        return set()

    async def poll(self, channel, key, http, headers):
        cursor = channel["cursor"]
        file_id = key.split(":", 1)[1]
        if cursor.get("removed"):
            return []
        resp = await http.get(f"{GOOGLE_API_BASE}/drive/v3/files/{file_id}", headers=headers,
                              params={"fields": DRIVE_FILE_FIELDS, "supportsAllDrives": "true"})
        uri = f"{GOOGLE_API_BASE}/drive/v3/files/{file_id}?alt=json"
        if resp.status_code == 404:
            if cursor.get("snapshot") is None:
                # never seen: nothing to report a removal against
                return []
            cursor["removed"] = True
            event_type, names = DRIVE_FILE_STATES["remove"]
            return [Event(set(names), {"_provider_meta": _google_meta(channel, state="remove", resource_uri=uri)}, event_type)]
        resp.raise_for_status()
        body = resp.json()
        snapshot = {
            "modified_time": body.get("modifiedTime"),
            "version": str(body.get("version") or ""),
            "md5": body.get("md5Checksum"),
            "trashed": bool(body.get("trashed")),
        }
        previous = cursor.get("snapshot")
        cursor["snapshot"] = snapshot
        if previous is None:
            return []  # baseline — Base44's watch starts at registration too
        if snapshot["trashed"] != previous["trashed"]:
            state = "trash" if snapshot["trashed"] else "untrash"
        elif (snapshot["version"], snapshot["modified_time"], snapshot["md5"]) != (
                previous["version"], previous["modified_time"], previous["md5"]):
            state = "update"
        else:
            return []
        event_type, names = DRIVE_FILE_STATES[state]
        return [Event(set(names), {"_provider_meta": _google_meta(channel, state=state, resource_uri=uri)}, event_type)]


class GoogleCalendarEventsAdapter(Adapter):
    """`events` — "any calendar event change" on the calendar `resource_id`
    names (`primary` on the captured app). Base44 registers `events.watch`;
    Google pushes `x-goog-resource-state: exists` with the calendar's events
    URI (50 of 50 captured runs). Cursor = an events sync token; 410 = the
    token expired → resync silently (Google's contract)."""
    integration = "googlecalendar"
    events = frozenset({"events"})

    def channel_keys(self, sub: Subscriber) -> set[str]:
        return {f"calendar:{sub.resource_id or 'primary'}"}

    async def poll(self, channel, key, http, headers):
        cursor = channel["cursor"]
        cal = key.split(":", 1)[1]
        url = f"{GOOGLE_API_BASE}/calendar/v3/calendars/{cal}/events"
        if cursor.get("sync_token") is None:
            page = None
            while True:
                params = {"maxResults": 2500, "showDeleted": "true", "fields": "nextPageToken,nextSyncToken"}
                if page:
                    params["pageToken"] = page
                resp = await http.get(url, headers=headers, params=params)
                resp.raise_for_status()
                body = resp.json()
                if body.get("nextPageToken"):
                    page = body["nextPageToken"]
                    continue
                cursor["sync_token"] = str(body["nextSyncToken"])
                return []
        page = None
        changed = 0
        while True:
            params = {"syncToken": cursor["sync_token"], "showDeleted": "true",
                      "fields": "nextPageToken,nextSyncToken,items(id)"}
            if page:
                params["pageToken"] = page
            resp = await http.get(url, headers=headers, params=params)
            if resp.status_code == 410:
                logger.warning("calendar sync token expired (%s) — resyncing", key)
                cursor["sync_token"] = None
                return []
            resp.raise_for_status()
            body = resp.json()
            changed += len(body.get("items") or [])
            if body.get("nextPageToken"):
                page = body["nextPageToken"]
                continue
            cursor["sync_token"] = str(body.get("nextSyncToken") or cursor["sync_token"])
            break
        if not changed:
            return []
        meta = _google_meta(channel, state="exists", resource_uri=f"{url}?alt=json")
        return [Event({"events"}, {"_provider_meta": meta}, "events")]


# One integration can carry several adapters (Drive: the `changes` channel
# and the per-file channels are different Google subscriptions with different
# lifetimes); an integration's served events = the union.
ADAPTERS: dict[str, tuple[Adapter, ...]] = {}
for _adapter in (GmailAdapter(), GoogleDriveChangesAdapter(), GoogleDriveFileAdapter(),
                 GoogleCalendarEventsAdapter()):
    ADAPTERS[_adapter.integration] = ADAPTERS.get(_adapter.integration, ()) + (_adapter,)


def served_events(integration: str) -> frozenset[str]:
    """Everything the fork serves for an integration, by EITHER mechanism: a
    polling adapter here (Google — it only pushes to a domain verified in the
    OAuth client's own cloud project, which is the customer's after migration)
    or the inbound push door (`push.py` — every other provider POSTs to the
    app's own address)."""
    from .push import served_events as push_events
    polled = frozenset().union(*(a.events for a in ADAPTERS.get(integration, ())), frozenset())
    return polled | push_events(integration)


def _serving_integrations() -> set[str]:
    from .push import PROVIDERS
    return set(ADAPTERS) | set(PROVIDERS)


def contract_matches_adapters() -> list[str]:
    """The contract's `events_by_integration` (the analysis allowlist) and what
    the fork can actually serve must be the same inventory — so analysis can
    never pass an app an event nothing handles, and the fork can never carry a
    handler analysis refuses. The engine gate asserts it."""
    contract = CONTRACT["trigger_types"]["connector"]["events_by_integration"]
    serving = _serving_integrations()
    problems = []
    for integration, events in contract.items():
        if integration not in serving:
            problems.append(f"contract lists {integration} but nothing serves it")
        elif set(events) != set(served_events(integration)):
            problems.append(f"{integration}: contract {sorted(events)} != served {sorted(served_events(integration))}")
    for integration in serving:
        if integration not in contract:
            problems.append(f"{integration} is served but is not in the contract")
    return problems


# ── the tick entry point ──

async def poll_connector_triggers() -> int:
    """Poll every channel that has an active subscriber (workflow or legacy
    automation); fire per subscriber per matching event. Returns fires."""
    subs = await _collect_subscribers()
    if not subs:
        return 0
    channels: dict[tuple[str, str], tuple[Adapter, list[Subscriber]]] = {}
    for sub in subs:
        # analysis blocks unmeasured integrations/events pre-pay; a record
        # still here for one is inert
        for adapter in ADAPTERS.get(sub.integration, ()):
            for key in adapter.channel_keys(sub):
                channels.setdefault((sub.integration, key), (adapter, []))[1].append(sub)

    fired = 0
    tokens: dict[str, dict | None] = {}
    async with httpx.AsyncClient(timeout=30.0) as http:
        for (integration, key), (adapter, group) in channels.items():
            if integration not in tokens:
                tokens[integration] = await _connection(integration)
            conn = tokens[integration]
            if conn is None:
                continue  # the app's connector is not connected yet
            try:
                channel = await _ensure_channel(integration, key, adapter.channel_ttl)
                events = await adapter.poll(
                    channel, key, http, {"Authorization": f"Bearer {conn['access_token']}"})
                await _save_channel(channel)
            except Exception:
                logger.debug("%s poll failed for %s (non-fatal, next tick retries)", integration, key, exc_info=True)
                continue
            for event in events:
                for sub in group:
                    if not any(e in event.names for e in sub.events):
                        continue
                    fired += await _fire(sub, integration, event.type, event.data, conn)
    return fired


async def _connection(integration: str) -> dict | None:
    """The app-scoped connection's live access token + identity, or None when
    the app has not connected this integration."""
    from app.modules.connectors.helpers import find_app_config, token_filter_app
    from app.modules.connectors.refresh import vend_access_token

    cfg = await find_app_config(integration)
    token_doc = await db.coll("_connector_tokens").find_one(token_filter_app(integration))
    if not cfg or not token_doc:
        return None
    access_token = await vend_access_token(token_doc, cfg, await addresses.canonical_base_url())
    return {
        "access_token": access_token,
        "provider_identifier": token_doc.get("integration_account_identifier") or token_doc.get("user_email") or "",
    }


async def _fire(sub: Subscriber, integration: str, event_type: str, data: dict, conn: dict) -> int:
    if sub.kind == "workflow":
        payload = {
            "trigger_type": "connector",
            "integration_type": integration,
            "event_type": event_type,
            "data": data,
        }
        if not trigger_admits(sub.condition, payload):
            return 0
        try:
            run_id = await create_run(sub.doc, trigger_type="connector", trigger_payload=payload)
            kick(run_id)
            return 1
        except Exception:
            logger.debug("connector run creation failed (non-fatal)", exc_info=True)
            return 0
    from app.core.automations import dispatch_connector
    return 1 if await dispatch_connector(
        sub.doc, sub.deployed_url, function_name=sub.function_name or "",
        integration_type=integration, event_type=event_type,
        data=data, provider_identifier=conn["provider_identifier"],
    ) else 0


def _gmail_payload(message_ids: list[str], *, previous_history_id: str, history_id: str,
                   email_address: str | None) -> dict:
    """The measured Gmail trigger payload (H §14.11b; lab 2026-09-02) —
    `data` carries message IDS and a history cursor, never the message; the
    workflow's function reads mail itself with the connector token, exactly
    as on Base44. A label-only change is the same shape with
    `has_new_messages: false` and no ids."""
    now_ms = time.time()
    publish_time = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now_ms)) + f".{int((now_ms % 1) * 100):02d}Z"
    message_id = str(uuid4().int % 10**17)
    data_b64 = base64.b64encode(orjson.dumps(
        {"emailAddress": email_address, "historyId": int(history_id)}
    )).decode()
    return {
        "has_new_messages": len(message_ids) > 0,
        "new_message_ids": message_ids,
        "previous_history_id": previous_history_id,
        "message": {
            "data": data_b64,
            "messageId": message_id, "message_id": message_id,
            "publishTime": publish_time, "publish_time": publish_time,
        },
        "subscription": SUBSCRIPTION_NAME,
    }
