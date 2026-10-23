"""The renders of a link-delivered message: the notice page (GET), the
message (POST) and an attachment of it (POST). Plain HTML, the app's own
name, no app chrome — this is a page the app's recipient reaches from an
email, not an app screen."""

from __future__ import annotations

import html as html_lib
from urllib.parse import quote

from fastapi.responses import HTMLResponse, Response

from app.core import db
from app.core.mail import link
from app.core.responses import utcnow_naive


async def show_notice(app_id: str, token: str) -> HTMLResponse:
    app_name = await _app_name()
    doc = await _live_message(token)
    if doc is None:
        return _expired(app_name)
    body = f"""
      <p class="lead">You have a new message.</p>
      <form method="post"><button type="submit">Open message</button></form>
      <p class="fine">Sent {_when(doc)}.</p>"""
    return HTMLResponse(_page(app_name, body))


async def open_message(app_id: str, token: str) -> HTMLResponse:
    app_name = await _app_name()
    doc = await _live_message(token)
    if doc is None:
        return _expired(app_name)
    if doc.get("opened_at") is None:
        await db.coll(link.MESSAGES).update_one({"_id": token, "opened_at": None}, {"$set": {"opened_at": utcnow_naive()}})
    subject = html_lib.escape(doc.get("subject") or "(no subject)")
    # The sender is named only when it is not the app itself (the heading).
    sender = doc.get("from_name")
    meta = _when(doc) if not sender or sender == app_name else f"From {html_lib.escape(sender)} · {_when(doc)}"
    if doc.get("html"):
        # The app's own HTML, rendered the way a mail client renders it: in a
        # frame with no scripts and no origin (`sandbox` with nothing
        # allowed). An app user who can call SendEmail with any htmlBody must
        # not get a script onto this origin.
        content = f'<iframe class="message" sandbox srcdoc="{html_lib.escape(doc["html"], quote=True)}" title="Message"></iframe>'
    else:
        content = f'<pre class="message">{html_lib.escape(doc.get("text") or "")}</pre>'
    # Each attachment is a button (a POST, like the message itself): a link a
    # scanner could follow would hand it the file.
    attachments = "".join(
        f'\n      <form method="post" action="/api/apps/{app_id}/mail/{token}/attachments/{i}" class="attachment">'
        f'<button type="submit" class="file">{html_lib.escape(a["filename"])}'
        f' <span class="size">({_size(len(a["content"]))})</span></button></form>'
        for i, a in enumerate(doc.get("attachments") or [])
    )
    body = f"""
      <p class="from">{meta}</p>
      <h2>{subject}</h2>
      {content}{attachments}"""
    return HTMLResponse(_page(app_name, body, wide=True))


async def download_attachment(app_id: str, token: str, index: int) -> Response:
    doc = await _live_message(token)
    attachments = (doc or {}).get("attachments") or []
    if doc is None or not 0 <= index < len(attachments):
        return _expired(await _app_name())
    a = attachments[index]
    name = a["filename"]
    ascii_name = name.encode("ascii", "replace").decode("ascii").replace('"', "")
    return Response(
        content=bytes(a["content"]),
        media_type=a["content_type"],
        headers={"Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"},
    )


async def _app_name() -> str:
    return (await db.app_settings()).get("name") or "the app"


async def _live_message(token: str) -> dict | None:
    return await db.coll(link.MESSAGES).find_one({"_id": token})


def _expired(app_name: str) -> HTMLResponse:
    body = """
      <p class="lead">This link isn't valid.</p>
      <p class="fine">Check that the whole link was copied, or ask the sender to send the message again.</p>"""
    return HTMLResponse(_page(app_name, body), status_code=404)


def _when(doc: dict) -> str:
    created = doc.get("created_date")
    return created.strftime("%b %-d, %Y") if created else ""


def _size(n: int) -> str:
    return f"{n} B" if n < 1024 else f"{n / 1024:.0f} KB" if n < 1024 * 1024 else f"{n / (1024 * 1024):.1f} MB"


def _page(app_name: str, body: str, *, wide: bool = False) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{html_lib.escape(app_name)}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: #F6F7F9; font-family: Arial, sans-serif; color: #000; line-height: 1.5; }}
  main {{ max-width: {"760px" if wide else "480px"}; margin: 40px auto; padding: 0 16px; }}
  .card {{ background: #fff; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,.1); padding: 32px 28px; }}
  h1 {{ font-size: 18px; margin: 0 0 24px; }}
  h2 {{ font-size: 20px; margin: 8px 0 20px; }}
  .lead {{ font-size: 16px; margin: 0 0 24px; }}
  .from {{ color: #6B7280; font-size: 14px; margin: 0; }}
  .fine {{ color: #A5A5A5; font-size: 13px; margin: 20px 0 0; }}
  button {{ background: #000; color: #fff; border: 1px solid #000; border-radius: 300px; padding: 12px 32px; font-size: 16px; font-family: inherit; cursor: pointer; }}
  button:hover {{ background: #080D2F; border-color: #080D2F; }}
  .message {{ width: 100%; border: 1px solid #E5E7EB; border-radius: 4px; background: #fff; }}
  iframe.message {{ height: min(60vh, 520px); min-height: 240px; }}
  pre.message {{ padding: 20px; white-space: pre-wrap; word-wrap: break-word; font: inherit; margin: 0; }}
  form.attachment {{ display: inline-block; margin: 16px 8px 0 0; }}
  button.file {{ background: #fff; color: #000; border-color: #E5E7EB; border-radius: 6px; padding: 8px 14px; font-size: 14px; }}
  button.file:hover {{ background: #F6F7F9; border-color: #D1D5DB; }}
  .size {{ color: #6B7280; }}
</style>
</head>
<body>
<main>
  <div class="card">
    <h1>{html_lib.escape(app_name)}</h1>{body}
  </div>
</main>
</body>
</html>
"""
