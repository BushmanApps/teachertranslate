from typing import Protocol


class StorageProvider(Protocol):
    async def upload(self, data: bytes, filename: str, content_type: str, private: bool = False) -> str:
        """Returns file_url (public) or file_uri (private)."""
        ...

    async def sign(self, file_uri: str, ttl: int = 300) -> str:
        """Returns a signed URL for a private file."""
        ...

    def public_url_for(self, key: str) -> str:
        """Absolute public URL for a bare storage key (e.g. 'public/foo.png').

        Used by `resolve_storage_uri` to turn user-supplied bare public URIs
        ('mp/public/...' or 'public/...') into something the LLM/HTTP layer
        can fetch directly.
        """
        ...
