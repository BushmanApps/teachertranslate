"""Connector triggers whose provider PUSHES — the one inbound door.

Google's three integrations are POLLED (`connectors.py`): Google only pushes to a
domain verified inside the cloud project that owns the OAuth client, and after
migration that project is the customer's, so no push can be arranged for them.

Every OTHER integration Base44 offers workflow triggers for — slack, slackbot,
outlook, one_drive, share_point, microsoft_teams, wix — is push-native: the
provider POSTs to a URL configured on the OAuth app itself. The app is its own
client after migration, so the fork can receive those events at its own address
and forward them exactly as Base44 does.

WHAT BASE44 FORWARDS — measured on two independent providers, from customers'
own run ledgers (the `__trigger__` step's input_data):

  slackbot  `data` = Slack's Events API outer envelope VERBATIM
            ({token, team_id, api_app_id, event{...}, type: "event_callback",
            event_id, event_time, authorizations, event_context}); `event_type`
            = `event.type`, and for a `message` the `channel_type` suffix
            (channel → message.channels, group → message.groups). 24 runs
            across two workflows, 2026-09-17.
  outlook   `data` = Microsoft Graph's change-notification envelope VERBATIM
            ({value: [{subscriptionId, subscriptionExpirationDateTime,
            changeType, resource, resourceData{...}, clientState, tenantId}]});
            `event_type` = the subscribed name. 6 runs, 2026-09-27.

So the rule is: the provider's raw body, untouched. Nothing here reshapes a
payload — a reshape is what would break the customer's jq expressions and their
functions, which read `.trigger.data.event.…` / `.data.value[0].…`.

SHAPE. A provider contributes verification, a handshake, event-name derivation
and (where the subscription is ours to own) its lifecycle. The fan-out is the
one `connectors.py` already has — subscribers are connector-triggered workflows
AND legacy connector automations alike.

SERVERLESS. The response must be fast (Slack drops a subscription that takes
over 3 s) and the container freezes when the response is sent, so the door
VERIFIES, dedups and PERSISTS the event, then answers; the tick drains the
inbox, and `kick()` drains it immediately where background work is a declared
capability (`Settings.EB44_BACKGROUND_TASKS`). An event is therefore never lost
and never handled twice.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

from app.core import db

logger = logging.getLogger("escapebase44.workflows.push")

INBOX = "_connector_push_inbox"
SEEN = "_connector_push_seen"
# Slack signs with a 5-minute replay window and says to reject older ones.
SIGNATURE_MAX_AGE_S = 300
# Graph's ceiling for mail/calendar/contacts is 4230 minutes; renew well early.
GRAPH_SUBSCRIPTION_MINUTES = 4230
GRAPH_RENEW_BEFORE = timedelta(hours=12)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class PushEvent:
    """One provider occurrence: which subscribed names it satisfies, the
    `event_type` the payload carries, and the provider's raw body as `data`."""
    names: set[str]
    type: str
    data: dict
    dedup_key: str | None = None


@dataclass
class HandshakeReply:
    """What to answer a provider's subscription-verification request with."""
    body: str
    media_type: str = "text/plain"


class PushProvider:
    """A plain behaviour class, deliberately NOT a dataclass: a dataclass
    __init__ assigns the parent's field defaults over a subclass's class
    attributes, so every provider would register under an empty name (the
    engine gate's contract-vs-served invariant caught exactly that)."""
    integration: str = ""
    events: frozenset[str] = frozenset()
    # The field on the app's `_connector_configs` doc holding the verification
    # secret. Base44 never asks for one (it verifies against its OWN app), so
    # this is a field the setup surface collects for a bring-your-own app.
    secret_field: str = ""

    def handshake(self, raw: bytes, parsed: object, params: dict) -> HandshakeReply | None:
        return None

    def verify(self, raw: bytes, headers: dict, secret: str) -> bool:
        raise NotImplementedError

    def events_of(self, parsed: object) -> list[PushEvent]:
        raise NotImplementedError

    async def ensure_subscription(self, channel: dict, http: httpx.AsyncClient,
                                  headers: dict, notification_url: str, secret: str) -> None:
        """Create/renew the provider-side subscription when it is OURS to own.
        Slack's lives in the owner's app config (they set the request URL), so
        this is a no-op there; Graph's is created and renewed by us."""
        return None


class SlackPushProvider(PushProvider):
    integration = "slackbot"
    # message.channels / message.groups are measured on a customer's own runs;
    # message.im / message.mpim follow the SAME measured derivation (Slack's
    # own `channel_type`), and app_mention is the event's literal type. The
    # envelope is a verbatim passthrough either way, so what a new event could
    # only change is which subscriber matches.
    events = frozenset({"app_mention", "message.im", "message.mpim", "message.channels", "message.groups"})
    secret_field = "signing_secret"

    _CHANNEL_TYPE_SUFFIX = {"channel": "channels", "group": "groups", "im": "im", "mpim": "mpim"}

    def handshake(self, raw: bytes, parsed: object, params: dict) -> HandshakeReply | None:
        if isinstance(parsed, dict) and parsed.get("type") == "url_verification":
            return HandshakeReply(str(parsed.get("challenge", "")))
        return None

    def verify(self, raw: bytes, headers: dict, secret: str) -> bool:
        ts = headers.get("x-slack-request-timestamp", "")
        sig = headers.get("x-slack-signature", "")
        if not ts or not sig or not secret:
            return False
        try:
            if abs(time.time() - int(ts)) > SIGNATURE_MAX_AGE_S:
                return False
        except ValueError:
            return False
        expected = "v0=" + hmac.new(secret.encode(), b"v0:" + ts.encode() + b":" + raw, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, sig)

    def events_of(self, parsed: object) -> list[PushEvent]:
        if not isinstance(parsed, dict) or parsed.get("type") != "event_callback":
            return []
        event = parsed.get("event") or {}
        etype = str(event.get("type", ""))
        if etype == "message":
            suffix = self._CHANNEL_TYPE_SUFFIX.get(str(event.get("channel_type", "")))
            if suffix is None:
                return []
            name = f"message.{suffix}"
        else:
            name = etype
        if name not in self.events:
            return []
        return [PushEvent(names={name}, type=name, data=parsed,
                          dedup_key=str(parsed.get("event_id") or "") or None)]


class GraphPushProvider(PushProvider):
    """Microsoft Graph — one wire, four of Base44's integrations. The event
    names are Base44's (`created`/`updated`/`deleted`), derived from Graph's
    own `changeType`; `created` is measured on a customer's 6 runs."""
    events = frozenset({"created", "updated", "deleted"})
    secret_field = "client_state"
    graph_resource = ""

    _CHANGE_TYPE = {"created": "created", "updated": "updated", "deleted": "deleted"}

    @property
    def change_type(self) -> str:
        """What we ask Graph to notify us about — the events THIS integration
        serves, never a constant. A resource refuses a changeType it does not
        support and the whole subscription is rejected: OneDrive serves only
        `updated` and answers a create carrying `created` with `InvalidRequest:
        Invalid 'changeType' attribute: 'created'` (measured live, 2026-09-28),
        so a constant here left one_drive unable to hold a subscription at all.
        """
        return ",".join(sorted(g for b, g in self._CHANGE_TYPE.items() if b in self.events))

    def handshake(self, raw: bytes, parsed: object, params: dict) -> HandshakeReply | None:
        # Graph validates a notificationUrl by GET/POSTing it with this param
        # and demands the token echoed back as text/plain.
        token = params.get("validationToken")
        return HandshakeReply(str(token)) if token else None

    def verify(self, raw: bytes, headers: dict, secret: str) -> bool:
        # Graph carries no signature; the contract is the clientState WE set on
        # the subscription, returned on every notification.
        if not secret:
            return False
        import orjson
        try:
            body = orjson.loads(raw)
        except Exception:
            return False
        values = body.get("value") if isinstance(body, dict) else None
        if not isinstance(values, list) or not values:
            return False
        return all(hmac.compare_digest(str(v.get("clientState", "")), secret) for v in values)

    def events_of(self, parsed: object) -> list[PushEvent]:
        if not isinstance(parsed, dict):
            return []
        out: list[PushEvent] = []
        for item in parsed.get("value") or []:
            name = self._CHANGE_TYPE.get(str(item.get("changeType", "")))
            if name is None or name not in self.events:
                continue
            # One notification body can carry several changes; Base44 forwards
            # the body it received, so each occurrence keeps the whole envelope
            # with just its own item (measured bodies carried exactly one).
            out.append(PushEvent(
                names={name}, type=name, data={**parsed, "value": [item]},
                dedup_key=f"{item.get('subscriptionId', '')}:{item.get('resource', '')}:{name}:{(item.get('resourceData') or {}).get('@odata.etag', '')}" or None,
            ))
        return out

    async def ensure_subscription(self, channel: dict, http: httpx.AsyncClient,
                                  headers: dict, notification_url: str, secret: str) -> None:
        sub_id = (channel.get("cursor") or {}).get("subscription_id")
        expires = (channel.get("cursor") or {}).get("expires_at")
        deadline = (_now() + GRAPH_SUBSCRIPTION_MINUTES_DELTA).isoformat() + "Z"
        if sub_id and expires and datetime.fromisoformat(expires) - _now() > GRAPH_RENEW_BEFORE:
            return
        if sub_id:
            r = await http.patch(f"https://graph.microsoft.com/v1.0/subscriptions/{sub_id}",
                                 headers=headers, json={"expirationDateTime": deadline})
            if r.status_code < 300:
                channel["cursor"] = {"subscription_id": sub_id, "expires_at": _iso(deadline)}
                return
            logger.debug("graph subscription renew failed (%s) — recreating", r.status_code)
        r = await http.post("https://graph.microsoft.com/v1.0/subscriptions", headers=headers, json={
            "changeType": self.change_type,
            "notificationUrl": notification_url,
            "resource": self.graph_resource,
            "expirationDateTime": deadline,
            "clientState": secret,
        })
        if r.status_code >= 300:
            raise RuntimeError(f"graph subscription create failed: {r.status_code} {r.text[:200]}")
        body = r.json()
        channel["cursor"] = {"subscription_id": body.get("id"), "expires_at": _iso(body.get("expirationDateTime") or deadline)}


GRAPH_SUBSCRIPTION_MINUTES_DELTA = timedelta(minutes=GRAPH_SUBSCRIPTION_MINUTES)


def _iso(value: str) -> str:
    return str(value).replace("Z", "").split("+")[0]


class OutlookPushProvider(GraphPushProvider):
    integration = "outlook"
    graph_resource = "me/messages"


class OneDrivePushProvider(GraphPushProvider):
    integration = "one_drive"
    events = frozenset({"updated"})
    graph_resource = "me/drive/root"


PROVIDERS: dict[str, PushProvider] = {}
for _p in (SlackPushProvider(), OutlookPushProvider(), OneDrivePushProvider()):
    PROVIDERS[_p.integration] = _p


def served_events(integration: str) -> frozenset[str]:
    provider = PROVIDERS.get(integration)
    return provider.events if provider else frozenset()


async def receive(integration: str, raw: bytes, headers: dict, params: dict) -> tuple[int, HandshakeReply | None]:
    """The door's whole decision: handshake, verify, dedup, persist. Returns
    (status, body-to-echo). Never runs a workflow inline — the tick drains."""
    import orjson
    from app.modules.connectors.helpers import find_app_config

    provider = PROVIDERS.get(integration)
    if provider is None:
        return 404, None
    try:
        parsed = orjson.loads(raw) if raw else None
    except Exception:
        parsed = None

    reply = provider.handshake(raw, parsed, params)
    if reply is not None:
        return 200, reply

    cfg = await find_app_config(integration) or {}
    secret = str((cfg.get("connection_config") or {}).get(provider.secret_field) or "")
    if not provider.verify(raw, headers, secret):
        # A provider whose secret the owner has not set yet, or a forged call —
        # both are refusals, and neither is a reason to run anything.
        return 401, None

    stored = 0
    for event in provider.events_of(parsed):
        if event.dedup_key:
            seen = await db.coll(SEEN).find_one_and_update(
                {"_id": f"{integration}:{event.dedup_key}"},
                {"$setOnInsert": {"at": _now()}}, upsert=True)
            if seen is not None:
                continue  # the provider redelivered; Base44 would fire twice, we do not
        await db.coll(INBOX).insert_one({
            "integration": integration, "event_type": event.type,
            "names": sorted(event.names), "data": event.data,
            "received_at": _now(), "claimed_at": None,
        })
        stored += 1
    return 200, None


async def drain_push_inbox(limit: int = 50) -> int:
    """Fan every stored event out to its subscribers, exactly as a poll would.
    Runs on the tick (and right after the door where the host allows it)."""
    from .connectors import _collect_subscribers, _connection, _fire

    fired = 0
    subs = await _collect_subscribers()
    for _ in range(limit):
        doc = await db.coll(INBOX).find_one_and_delete({"claimed_at": None})
        if doc is None:
            break
        integration = doc["integration"]
        group = [s for s in subs if s.integration == integration]
        if not group:
            continue
        conn = await _connection(integration) or {"provider_identifier": ""}
        names = set(doc.get("names") or [])
        for sub in group:
            if not any(e in names for e in sub.events):
                continue
            fired += await _fire(sub, integration, doc["event_type"], doc["data"], conn)
    return fired


async def ensure_push_subscriptions(notification_url_for) -> None:
    """Create/renew the subscriptions that are ours to own (Graph's). Slack's
    request URL lives in the owner's own app, so it has nothing here."""
    from .connectors import _collect_subscribers, _connection, _ensure_channel, _save_channel
    from app.modules.connectors.helpers import find_app_config

    subs = await _collect_subscribers()
    integrations = {s.integration for s in subs} & set(PROVIDERS)
    async with httpx.AsyncClient(timeout=30.0) as http:
        for integration in sorted(integrations):
            provider = PROVIDERS[integration]
            conn = await _connection(integration)
            if conn is None:
                continue
            cfg = await find_app_config(integration) or {}
            secret = str((cfg.get("connection_config") or {}).get(provider.secret_field) or "")
            if not secret:
                continue
            channel = await _ensure_channel(integration, "push", timedelta(days=365))
            try:
                await provider.ensure_subscription(
                    channel, http, {"Authorization": f"Bearer {conn['access_token']}"},
                    notification_url_for(integration), secret)
                await _save_channel(channel)
            except Exception as exc:
                # LOUD, and on the record. Without a subscription the provider
                # never calls: the app's trigger simply never fires, and there is
                # nothing else anywhere that says so. It is not hypothetical —
                # the connector's own scopes decide whether the provider will
                # even accept a subscription (measured 2026-09-28: a mailbox
                # subscription is refused `Forbidden` on a token carrying
                # Mail.Read and accepted on Mail.ReadWrite, and Base44 registers
                # Outlook connector shapes of both kinds), and the scopes are the
                # customer's app's own contract, not ours to change.
                channel["last_error"] = {"at": _now(), "message": str(exc)[:500]}
                await _save_channel(channel)
                logger.warning("%s subscription could not be created — its trigger will NOT fire: %s",
                               integration, exc, exc_info=True)
