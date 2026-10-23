import httpx


class VercelBlobStorageProvider:
    """Vercel Blob over its REST API. One read-write token, no S3 protocol.

    Pathnames are kept stable (x-add-random-suffix: 0) so public URLs are
    `{public_url}/{key}`, and overwrite is allowed to match S3 put_object
    semantics. The store is public with unguessable keys — the same effective
    access model as the R2 setup (bucket-wide public domain), so sign()
    returns the stable public URL.
    """

    def __init__(self, token: str, public_url: str):
        self._token = token
        self._public_url = public_url.rstrip("/")

    async def upload(self, data: bytes, filename: str, content_type: str, private: bool = False) -> str:
        prefix = "private" if private else "public"
        key = f"{prefix}/{filename}"

        async with httpx.AsyncClient(timeout=60.0) as client:
            res = await client.put(
                f"https://blob.vercel-storage.com/{key}",
                content=data,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "x-api-version": "7",
                    "x-add-random-suffix": "0",
                    "x-allow-overwrite": "1",
                    "x-content-type": content_type,
                },
            )
        if res.status_code >= 400:
            raise RuntimeError(f"Vercel Blob upload failed ({res.status_code}): {res.text[:200]}")

        if private:
            return key
        return f"{self._public_url}/{key}"

    async def sign(self, file_uri: str, ttl: int = 300) -> str:
        return f"{self._public_url}/{file_uri.lstrip('/')}"

    def public_url_for(self, key: str) -> str:
        return f"{self._public_url}/{key.lstrip('/')}"
