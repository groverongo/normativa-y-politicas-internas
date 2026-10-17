import re
from collections.abc import Iterator
from functools import lru_cache
from pathlib import PureWindowsPath
from typing import Any, BinaryIO
from urllib.parse import quote
from uuid import uuid4

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import get_settings

_NOT_FOUND_CODES = {"404", "NoSuchKey", "NotFound"}
_EXTENSION_RE = re.compile(r"\.[a-z0-9]{1,10}")


class S3ObjectNotFoundError(Exception):
    def __init__(self, key: str):
        super().__init__(f"Objeto no encontrado en S3: {key}")
        self.key = key


def content_disposition(filename: str) -> str:
    # filename* (RFC 5987) soporta tildes y caracteres no ASCII
    return f"attachment; filename*=UTF-8''{quote(filename)}"


class S3Service:
    def __init__(
        self,
        client: BaseClient,
        bucket: str,
        presigned_expiration: int = 3600,
        key_prefix: str = "uploads",
    ):
        self.client = client
        self.bucket = bucket
        self.presigned_expiration = presigned_expiration
        self.key_prefix = key_prefix.strip("/")

    def new_key(self, filename: str) -> str:
        """Key única; el nombre original se guarda en la BD, no en S3."""
        extension = PureWindowsPath(filename).suffix.lower()
        if not _EXTENSION_RE.fullmatch(extension):
            extension = ""
        name = f"{uuid4().hex}{extension}"
        return f"{self.key_prefix}/{name}" if self.key_prefix else name

    def check_bucket(self) -> None:
        self.client.head_bucket(Bucket=self.bucket)

    def upload(self, key: str, fileobj: BinaryIO, content_type: str | None = None) -> dict[str, Any]:
        """Sube al bucket por defecto y devuelve los metadatos reales del objeto."""
        extra_args = {"ContentType": content_type} if content_type else None
        self.client.upload_fileobj(fileobj, self.bucket, key, ExtraArgs=extra_args)
        return self.head(key)

    def head(self, key: str, bucket: str | None = None) -> dict[str, Any]:
        try:
            return self.client.head_object(Bucket=bucket or self.bucket, Key=key)
        except ClientError as exc:
            if exc.response["Error"]["Code"] in _NOT_FOUND_CODES:
                raise S3ObjectNotFoundError(key) from exc
            raise

    def download(
        self, key: str, bucket: str | None = None, chunk_size: int = 1024 * 1024
    ) -> tuple[Iterator[bytes], dict[str, Any]]:
        try:
            obj = self.client.get_object(Bucket=bucket or self.bucket, Key=key)
        except ClientError as exc:
            if exc.response["Error"]["Code"] in _NOT_FOUND_CODES:
                raise S3ObjectNotFoundError(key) from exc
            raise
        return obj["Body"].iter_chunks(chunk_size), obj

    def delete(self, key: str, bucket: str | None = None) -> None:
        # Idempotente: S3 no falla si la key ya no existe.
        self.client.delete_object(Bucket=bucket or self.bucket, Key=key)

    def presigned_url(
        self,
        key: str,
        bucket: str | None = None,
        expires_in: int | None = None,
        filename: str | None = None,
    ) -> str:
        params = {"Bucket": bucket or self.bucket, "Key": key}
        if filename:
            params["ResponseContentDisposition"] = content_disposition(filename)
        return self.client.generate_presigned_url(
            "get_object", Params=params, ExpiresIn=expires_in or self.presigned_expiration
        )


@lru_cache
def get_s3_service() -> S3Service:
    settings = get_settings()
    # Si las keys vienen vacías, boto3 usa la cadena por defecto
    # (variables de entorno, ~/.aws/credentials, rol IAM de EC2/ECS/Lambda).
    client = boto3.client(
        "s3",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id or None,
        aws_secret_access_key=settings.aws_secret_access_key or None,
        aws_session_token=settings.aws_session_token or None,
        config=Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}),
    )
    return S3Service(
        client,
        settings.s3_bucket_name,
        presigned_expiration=settings.s3_presigned_url_expiration,
        key_prefix=settings.s3_key_prefix,
    )
