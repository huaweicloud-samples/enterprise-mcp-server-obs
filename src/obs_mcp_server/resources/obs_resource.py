import logging
import os
import asyncio
import time
from typing import List, Dict, Any, Optional

from obs import ObsClient

logger = logging.getLogger("obs_mcp_server")


class OBSResource:
    """
    Object Storage (OBS) resource provider for the MCP server.

    Replaces the original object-storage provider with the Huawei Cloud OBS SDK
    (esdk-obs-python). It exposes the same three capabilities the server needs:
    listing buckets, listing objects in a bucket, and fetching an object.
    """

    def __init__(self, region_name: str = None, max_buckets: int = 5):
        """
        Initialize the OBS resource provider.

        Args:
            region_name: Huawei Cloud region (informational; the SDK global
                         endpoint routes requests to the correct region by bucket).
            max_buckets: Maximum number of buckets to surface (default: 5).
        """
        self.region_name = region_name or os.getenv('OBS_REGION', 'cn-north-4')
        self.max_buckets = max_buckets
        # The OBS global endpoint routes bucket/object requests to the right
        # region automatically, so a single client works account-wide.
        self.server = os.getenv('OBS_ENDPOINT', 'https://obs.myhuaweicloud.com')

        self.client = ObsClient(
            access_key_id=os.getenv('HW_ACCESS_KEY', ''),
            secret_access_key=os.getenv('HW_SECRET_KEY', ''),
            server=self.server,
            # 关闭签名协商：SDK 默认开启时会在线程局部变量 thread_local 上读写
            # signature，而请求内部线程（上传/下载流、响应解析）未初始化该属性，
            # 多线程 / asyncio.to_thread 调用会抛
            # '_thread._local' object has no attribute 'signature'。关闭后统一使用
            # 实例级固定签名，避免线程局部变量问题。
            is_signature_negotiation=False,
        )
        self.configured_buckets = self._get_configured_buckets()

    def _get_configured_buckets(self) -> List[str]:
        """
        Read the bucket allow-list from environment variables.
        Format in .env file:
            OBS_BUCKETS=bucket1,bucket2,bucket3
        or
            OBS_BUCKET_1=bucket1
            OBS_BUCKET_2=bucket2
        """
        bucket_list = os.getenv('OBS_BUCKETS')
        if bucket_list:
            return [b.strip() for b in bucket_list.split(',') if b.strip()]

        buckets = []
        i = 1
        while True:
            bucket = os.getenv(f'OBS_BUCKET_{i}')
            if not bucket:
                break
            buckets.append(bucket.strip())
            i += 1

        return buckets

    def _list_buckets_sync(self, start_after: Optional[str] = None) -> List[dict]:
        """List OBS buckets (sync, wrapped by the async method)."""
        resp = self.client.listBuckets()
        if resp.status >= 300:
            logger.error(f"listBuckets failed: {resp.errorCode} {resp.errorMessage}")
            return []

        all_buckets = resp.body.buckets or []
        result = [{'Name': b.name, 'CreationDate': b.create_date} for b in all_buckets]

        if self.configured_buckets:
            result = [b for b in result if b['Name'] in self.configured_buckets]

        if start_after:
            result = [b for b in result if b['Name'] > start_after]

        return result[:self.max_buckets]

    def _list_objects_sync(self, bucket_name: str, prefix: str = "", max_keys: int = 1000) -> List[dict]:
        """List objects in a bucket (sync, wrapped by the async method)."""
        if self.configured_buckets and bucket_name not in self.configured_buckets:
            logger.warning(f"list_objects skipped: bucket {bucket_name} not in configured bucket list")
            return []

        resp = self.client.listObjects(bucketName=bucket_name, prefix=prefix, max_keys=max_keys)
        if resp.status >= 300:
            logger.error(f"listObjects failed: {resp.errorCode} {resp.errorMessage}")
            return []

        contents = resp.body.contents or []
        return [{'Key': c.key, 'Size': c.size, 'LastModified': c.lastModified} for c in contents]

    def _get_object_sync(self, bucket_name: str, key: str, max_retries: int = 3) -> Dict[str, Any]:
        """Fetch an object, reading the full stream into memory (sync)."""
        if self.configured_buckets and bucket_name not in self.configured_buckets:
            raise ValueError(f"get_object failed! Bucket {bucket_name} not in configured bucket list")

        attempt = 0
        last_exception = None
        while attempt < max_retries:
            try:
                resp = self.client.getObject(
                    bucketName=bucket_name,
                    objectKey=key,
                    loadStreamInMemory=True,
                )
                if resp.status >= 300:
                    raise Exception(f"getObject failed status {resp.status}: {resp.errorMessage}")

                # loadStreamInMemory=True 时 resp.body.buffer 已是 bytes；
                # 否则 buffer 为可读流，需 .read()。两者兼容处理。
                raw = resp.body.buffer
                data = raw if isinstance(raw, (bytes, bytearray)) else raw.read()
                content_type = resp.body.contentType or 'application/octet-stream'
                return {'Body': data, 'ContentType': content_type}

            except Exception as e:
                last_exception = e
                # NoSuchKey is terminal — do not retry.
                if 'NoSuchKey' in str(e):
                    raise
                attempt += 1
                if attempt < max_retries:
                    wait_time = 2 ** attempt
                    logger.warning(f"Attempt {attempt} failed, retrying in {wait_time}s: {e}")
                    time.sleep(wait_time)
                continue

        raise last_exception or Exception("Failed to get object after all retries")

    async def list_buckets(self, start_after: Optional[str] = None) -> List[dict]:
        return await asyncio.to_thread(self._list_buckets_sync, start_after)

    async def list_objects(self, bucket_name: str, prefix: str = "", max_keys: int = 1000) -> List[dict]:
        return await asyncio.to_thread(self._list_objects_sync, bucket_name, prefix, max_keys)

    async def get_object(self, bucket_name: str, key: str, max_retries: int = 3) -> Dict[str, Any]:
        return await asyncio.to_thread(self._get_object_sync, bucket_name, key, max_retries)

    def is_text_file(self, key: str) -> bool:
        """Determine if a file is text-based by its extension."""
        text_extensions = {
            '.txt', '.log', '.json', '.xml', '.yml', '.yaml', '.md',
            '.csv', '.ini', '.conf', '.py', '.js', '.html', '.css',
            '.sh', '.bash', '.cfg', '.properties'
        }
        return any(key.lower().endswith(ext) for ext in text_extensions)
