"""The attachments of a SendEmail, as Base44 takes them (measured
2026-09-29, the parity audit's attachment batteries).

One attachment at a time, in the request's order, and for each: its bytes
(a base64 `content`, or a `file_url` naming a file this app stores) → not
empty → at most 5 MB → the mail's attachments so far at most 10 MB → the
bytes are what the extension says. The first attachment that fails any of
these ends the request, so a later attachment's fault is never reported
before an earlier one's.

What "the bytes are what the extension says" means per type:
- png, jpg/jpeg, gif, pdf, webp — the format's signature at byte 0;
- docx, xlsx — a readable zip whose `[Content_Types].xml` is a content-types
  part and whose main part (`word/document.xml`, `xl/workbook.xml`) has the
  format's root element (transitional or strict namespace); only the root is
  read, what follows it may be anything; a zip that is not that is an archive
  under a document's name; one holding a `vbaProject.bin` carries macros;
- csv, ics, md, txt — anything that does not open with the signature of a
  zip, a Windows executable, an ELF binary, a 64-bit Mach-O or a universal
  binary / Java class (an image, a PDF, a gzip named .txt all pass).
"""

from __future__ import annotations

import base64
import binascii
import io
import zipfile
from xml.etree.ElementTree import ParseError, XMLPullParser

import httpx

from app.core.errors import AppHTTPException
from app.core.models.integrations import (
    EMAIL_ATTACHMENT_MAX_BYTES,
    EMAIL_ATTACHMENTS_MAX_BYTES,
    EmailAttachment,
)
from app.core.providers.email import Attachment
from app.core.storage_uri import own_url

CONTENT_TYPES = {
    "csv": "text/csv",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "gif": "image/gif",
    "ics": "text/calendar",
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
    "md": "text/markdown",
    "pdf": "application/pdf",
    "png": "image/png",
    "txt": "text/plain",
    "webp": "image/webp",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

_ZIP = b"PK\x03\x04"
_NOT_TEXT = (_ZIP, b"MZ", b"\x7fELF", b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe")
_SIGNATURES = {
    "png": lambda d: d.startswith(b"\x89PNG\r\n\x1a\n"),
    "jpg": lambda d: d.startswith(b"\xff\xd8\xff"),
    "jpeg": lambda d: d.startswith(b"\xff\xd8\xff"),
    "gif": lambda d: d.startswith((b"GIF87a", b"GIF89a")),
    "pdf": lambda d: d.startswith(b"%PDF-"),
    "webp": lambda d: d.startswith(b"RIFF") and d[8:12] == b"WEBP",
}
_CONTENT_TYPES_ROOT = "{http://schemas.openxmlformats.org/package/2006/content-types}Types"
_OFFICE = {
    "docx": ("word/document.xml", "document", "wordprocessingml"),
    "xlsx": ("xl/workbook.xml", "workbook", "spreadsheetml"),
}
_ROOT_READ = 64 * 1024


def _refuse(message: str) -> AppHTTPException:
    return AppHTTPException(422, message)


def _root(archive: zipfile.ZipFile, part: str) -> str | None:
    """The part's root element, `{namespace}tag` — None when the archive has
    no such part or the part does not open as XML."""
    try:
        with archive.open(part) as member:
            head = member.read(_ROOT_READ)
    except (KeyError, zipfile.BadZipFile, RuntimeError, NotImplementedError, OSError):
        return None
    parser = XMLPullParser(events=("start",))
    try:
        parser.feed(head)
        for _, element in parser.read_events():
            return element.tag
    except ParseError:
        pass
    return None


def _check_type(name: str, extension: str, data: bytes) -> None:
    mismatch = _refuse(f"Attachment '{name}' content doesn't match its file type.")
    if extension in _SIGNATURES:
        if not _SIGNATURES[extension](data):
            raise mismatch
        return
    if extension not in _OFFICE:
        if data.startswith(_NOT_TEXT):
            raise mismatch
        return

    if not data.startswith(_ZIP):
        raise mismatch
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise mismatch
    part, tag, family = _OFFICE[extension]
    roots = (
        f"{{http://schemas.openxmlformats.org/{family}/2006/main}}{tag}",
        f"{{http://purl.oclc.org/ooxml/{family}/main}}{tag}",
    )
    with archive:
        if _root(archive, "[Content_Types].xml") != _CONTENT_TYPES_ROOT or _root(archive, part) not in roots:
            raise _refuse(
                f"Attachment '{name}' isn't a valid Office document. "
                "Archives can't be attached, even under a document extension."
            )
        if any(entry.rpartition("/")[2].lower() == "vbaproject.bin" for entry in archive.namelist()):
            raise _refuse(f"Attachment '{name}' contains macros, which aren't supported.")


async def _stored(attachment: EmailAttachment, *, app_id: str, storage, http: httpx.AsyncClient) -> bytes:
    not_ours = _refuse(f"Attachment '{attachment.filename}' must reference a file stored by this app.")
    if storage is None:
        raise AppHTTPException(500, "Storage provider not configured")
    found = own_url(attachment.file_url, app_id, storage)
    if found is None:
        raise not_ours
    reference, private = found
    if private:
        url = await storage.sign(reference, ttl=300)
    else:
        url = reference if reference.startswith(("http://", "https://")) else storage.public_url_for(reference)
    res = await http.get(url)
    if res.status_code >= 400:
        # A file this app never stored (Base44's own answer here is a crash).
        raise not_ours
    return res.content


async def gather(attachments: list[EmailAttachment], *, app_id: str, storage) -> list[Attachment]:
    gathered: list[Attachment] = []
    total = 0
    async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as http:
        for attachment in attachments:
            name = attachment.filename
            if attachment.content is not None:
                try:
                    data = base64.b64decode(attachment.content, validate=True)
                except (binascii.Error, ValueError):
                    raise _refuse(f"Attachment '{name}' content is not valid base64.")
            else:
                data = await _stored(attachment, app_id=app_id, storage=storage, http=http)
            if not data:
                raise _refuse(f"Attachment '{name}' is empty.")
            if len(data) > EMAIL_ATTACHMENT_MAX_BYTES:
                raise _refuse(f"Attachment '{name}' exceeds the 5 MB limit.")
            total += len(data)
            if total > EMAIL_ATTACHMENTS_MAX_BYTES:
                raise _refuse("Attachments exceed the 10 MB total limit.")
            _check_type(name, attachment.extension, data)
            gathered.append(Attachment(filename=name, content=data, content_type=CONTENT_TYPES[attachment.extension]))
    return gathered
