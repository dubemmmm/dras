from __future__ import annotations

import shutil
from pathlib import Path

import boto3

from dras.config import Settings


class LocalPrivateStorage:
    """Development adapter. Production uses the same key contract with private S3."""

    def __init__(self, settings: Settings):
        self.root = settings.storage_dir.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, assessment_id: str, name: str, data: bytes) -> str:
        folder = self.root / assessment_id
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / Path(name).name
        path.write_bytes(data)
        return str(path.relative_to(self.root))

    def read(self, key: str) -> bytes:
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError("Invalid storage key")
        return path.read_bytes()

    def delete_assessment(self, assessment_id: str) -> None:
        path = (self.root / assessment_id).resolve()
        if self.root not in path.parents or path == self.root:
            raise ValueError("Invalid assessment storage path")
        if path.exists():
            shutil.rmtree(path)

    def signed_url(self, key: str) -> str | None:
        return None


class S3PrivateStorage:
    def __init__(self, settings: Settings):
        if not settings.s3_bucket:
            raise ValueError("S3 bucket is not configured")
        self.bucket = settings.s3_bucket
        self.expires = settings.signed_url_seconds
        self.client = boto3.client("s3", region_name=settings.s3_region)

    def put(self, assessment_id: str, name: str, data: bytes) -> str:
        key = f"assessments/{assessment_id}/{Path(name).name}"
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ServerSideEncryption="AES256")
        return key

    def read(self, key: str) -> bytes:
        if not key.startswith("assessments/"):
            raise ValueError("Invalid storage key")
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def delete_assessment(self, assessment_id: str) -> None:
        prefix = f"assessments/{assessment_id}/"
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
            if objects:
                self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": objects, "Quiet": True})

    def signed_url(self, key: str) -> str:
        return self.client.generate_presigned_url("get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=self.expires)


def private_storage(settings: Settings) -> LocalPrivateStorage | S3PrivateStorage:
    return S3PrivateStorage(settings) if settings.s3_bucket else LocalPrivateStorage(settings)

