"""
Couche de stockage des fichiers — abstraction local / S3.
Sélection via settings.STORAGE_BACKEND ("local" | "s3").
S3 compatible AWS, MinIO et Scaleway (via S3_ENDPOINT_URL).
"""
import os
from functools import lru_cache
from typing import Optional

from app.core.config import get_settings

settings = get_settings()
UPLOAD_DIR = "uploads"


class LocalStorage:
    """Stockage disque (développement)."""
    def __init__(self):
        os.makedirs(UPLOAD_DIR, exist_ok=True)

    def _path(self, key: str) -> str:
        return os.path.join(UPLOAD_DIR, key)

    def save(self, key: str, content: bytes, content_type: Optional[str] = None) -> str:
        p = self._path(key)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(content)
        return key

    def load(self, key: str) -> bytes:
        with open(self._path(key), "rb") as f:
            return f.read()

    def delete(self, key: str) -> None:
        try:
            os.remove(self._path(key))
        except FileNotFoundError:
            pass

    def url(self, key: str, expires: int = 3600) -> Optional[str]:
        return None  # pas d'URL signée en local : on sert via l'API


class S3Storage:
    """Stockage objet S3 (production)."""
    def __init__(self):
        import boto3
        kwargs = {"region_name": settings.S3_REGION,
                  "aws_access_key_id": settings.AWS_ACCESS_KEY_ID,
                  "aws_secret_access_key": settings.AWS_SECRET_ACCESS_KEY}
        if settings.S3_ENDPOINT_URL:
            kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL
        self.s3 = boto3.client("s3", **kwargs)
        self.bucket = settings.S3_BUCKET

    def save(self, key: str, content: bytes, content_type: Optional[str] = None) -> str:
        extra = {"ContentType": content_type} if content_type else {}
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=content, **extra)
        return key

    def load(self, key: str) -> bytes:
        obj = self.s3.get_object(Bucket=self.bucket, Key=key)
        return obj["Body"].read()

    def delete(self, key: str) -> None:
        self.s3.delete_object(Bucket=self.bucket, Key=key)

    def url(self, key: str, expires: int = 3600) -> Optional[str]:
        return self.s3.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires)


@lru_cache()
def get_storage():
    if settings.STORAGE_BACKEND.lower() == "s3":
        return S3Storage()
    return LocalStorage()
