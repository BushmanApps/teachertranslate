import aioboto3
from botocore.config import Config

# The S3 protocol as every S3-compatible store speaks it:
#  - no request checksums beyond what an operation requires — botocore
#    >= 1.36 attaches a CRC32 checksum (aws-chunked framing) to every upload
#    by default, which Google Cloud Storage's XML API rejects (measured
#    2026-09-16: every put_object answered SignatureDoesNotMatch "Invalid
#    argument" until this); AWS S3, Cloudflare R2 and Supabase accept both;
#  - Signature Version 4 for presigned URLs, always — left to botocore, a
#    session-token client (Supabase Storage) signs presigned URLs with the
#    legacy query-string scheme (`AWSAccessKeyId`/`Signature`/`Expires`),
#    which Supabase answers 403 "Missing signature" (measured 2026-09-17:
#    every private file of a Supabase-storage app was unservable); AWS, R2
#    and GCS already got V4 and are unchanged.
_S3_COMPATIBLE = Config(
    request_checksum_calculation="when_required",
    response_checksum_validation="when_required",
    signature_version="s3v4",
)


class S3StorageProvider:
    def __init__(
        self,
        bucket: str,
        region: str,
        access_key_id: str,
        secret_access_key: str,
        endpoint_url: str | None = None,
        public_url: str | None = None,
        session_token: str | None = None,
    ):
        self._bucket = bucket
        self._session = aioboto3.Session()
        self._client_kwargs = {
            "service_name": "s3",
            "region_name": region,
            "aws_access_key_id": access_key_id,
            "aws_secret_access_key": secret_access_key,
            "config": _S3_COMPATIBLE,
        }
        if session_token:
            self._client_kwargs["aws_session_token"] = session_token
        if endpoint_url:
            self._client_kwargs["endpoint_url"] = endpoint_url

        if public_url:
            self._public_url = public_url.rstrip("/")
        elif endpoint_url:
            self._public_url = f"{endpoint_url.rstrip('/')}/{bucket}"
        else:
            self._public_url = f"https://{bucket}.s3.{region}.amazonaws.com"

    async def upload(self, data: bytes, filename: str, content_type: str, private: bool = False) -> str:
        prefix = "private" if private else "public"
        key = f"{prefix}/{filename}"

        async with self._session.client(**self._client_kwargs) as s3:
            await s3.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )

        if private:
            return key
        return f"{self._public_url}/{key}"

    async def sign(self, file_uri: str, ttl: int = 300) -> str:
        async with self._session.client(**self._client_kwargs) as s3:
            return await s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": file_uri},
                ExpiresIn=ttl,
            )

    def public_url_for(self, key: str) -> str:
        return f"{self._public_url}/{key.lstrip('/')}"
