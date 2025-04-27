# app/services/azure_blob.py
import os, uuid
from datetime import datetime, timezone
from typing import BinaryIO
from azure.storage.blob import BlobServiceClient, ContentSettings

__all__ = ["upload_image_and_get_url"]

# ────────────────────────────────────────────────────────────────────────────────
# Configuration (env vars → .env)
AZ_BLOB_CONN_STR = os.getenv("AZURE_BLOB_CONNECTION_STRING")
AZ_CONTAINER     = os.getenv("AZURE_BLOB_CONTAINER", "image-upload")

if not AZ_BLOB_CONN_STR:
    raise RuntimeError("AZURE_BLOB_CONNECTION_STRING is not set")

blob_service = BlobServiceClient.from_connection_string(AZ_BLOB_CONN_STR)
container_client = blob_service.get_container_client(AZ_CONTAINER)

MAX_SIZE = 10 * 1024 * 1024                                     # 10 MB
ALLOWED  = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
    "image/bmp": ".bmp",  "image/webp": ".webp",
    "image/tiff": ".tiff","image/svg+xml": ".svg"
}


async def upload_image_and_get_url(
    file_content: bytes,
    mime_type: str,
    user_id: str,
    original_name: str
) -> str:
    if mime_type not in ALLOWED:
        raise ValueError(
            f"File type not allowed. Allowed: {', '.join(ALLOWED)}"
        )
    if len(file_content) > MAX_SIZE:
        raise ValueError("File exceeds 10 MB limit")

    ts   = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ext  = ALLOWED[mime_type]
    blob_name = f"{user_id}/{ts}-{uuid.uuid4()}{ext}"

    blob_client = container_client.get_blob_client(blob_name)
    blob_client.upload_blob(
        file_content,
        overwrite=True,
        content_settings=ContentSettings(content_type=mime_type),
        metadata={
            "original": original_name,
            "user_id": user_id
        },
    )

    return (
        f"https://{blob_service.account_name}.blob.core.windows.net/"
        f"{AZ_CONTAINER}/{blob_name}"
    )