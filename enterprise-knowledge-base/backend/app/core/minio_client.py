"""MinIO 对象存储客户端 — 文档文件管理"""

import io

from minio import Minio

from app.core.config import settings
from app.core.logging import logger

_minio_client: Minio | None = None


def get_minio_client() -> Minio:
    global _minio_client
    if _minio_client is None:
        _minio_client = Minio(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=False,
        )
    return _minio_client


def ensure_bucket(bucket_name: str = "knowledge-docs") -> None:
    client = get_minio_client()
    if not client.bucket_exists(bucket_name):
        client.make_bucket(bucket_name)
        logger.info("minio_bucket_created", bucket=bucket_name)


def upload_file(
    bucket: str,
    object_name: str,
    data: bytes,
    content_type: str,
) -> str:
    client = get_minio_client()
    client.put_object(
        bucket_name=bucket,
        object_name=object_name,
        data=io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    return object_name


def delete_file(bucket: str, object_name: str) -> None:
    client = get_minio_client()
    client.remove_object(bucket_name=bucket, object_name=object_name)


def get_file_url(bucket: str, object_name: str) -> str:
    return f"/files/{bucket}/{object_name}"
