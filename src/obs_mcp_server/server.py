import asyncio

from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server, McpError
import mcp.server.stdio
from dotenv import load_dotenv
import logging
import os
from typing import List, Optional, Dict
from mcp.types import (
    Resource, LoggingLevel, EmptyResult, Tool, TextContent,
    ImageContent, EmbeddedResource, BlobResourceContents, ReadResourceResult,
)

from .resources.obs_resource import OBSResource
from pydantic import AnyUrl

import base64

# Initialize server
server = Server("obs_service")

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_obs_server")

# Get max buckets from environment or use default
max_buckets = int(os.getenv('OBS_MAX_BUCKETS', '5'))

# Initialize OBS resource provider (replaces the original object-storage provider)
obs_resource = OBSResource(
    region_name=os.getenv('OBS_REGION', 'cn-north-4'),
    max_buckets=max_buckets
)


@server.set_logging_level()
async def set_logging_level(level: LoggingLevel) -> EmptyResult:
    logger.setLevel(level.lower())
    await server.request_context.session.send_log_message(
        level="info",
        data=f"Log level set to {level}",
        logger="mcp_obs_server"
    )
    return EmptyResult()


@server.list_resources()
async def list_resources(start_after: Optional[str] = None) -> List[Resource]:
    """
    List OBS buckets and their contents as resources with pagination.
    Args:
        start_after: Start listing after this bucket name
    """
    resources = []
    logger.debug("Starting to list resources")
    logger.debug(f"Configured buckets: {obs_resource.configured_buckets}")

    try:
        buckets = await obs_resource.list_buckets(start_after)
        logger.debug(f"Processing {len(buckets)} buckets (max: {obs_resource.max_buckets})")

        async def process_bucket(bucket):
            bucket_name = bucket['Name']
            logger.debug(f"Processing bucket: {bucket_name}")

            try:
                objects = await obs_resource.list_objects(bucket_name, max_keys=1000)

                for obj in objects:
                    if 'Key' in obj and not obj['Key'].endswith('/'):
                        object_key = obj['Key']
                        mime_type = "text/plain" if obs_resource.is_text_file(object_key) else "text/markdown"

                        resource = Resource(
                            uri=f"obs://{bucket_name}/{object_key}",
                            name=object_key,
                            mimeType=mime_type
                        )
                        resources.append(resource)
                        logger.debug(f"Added resource: {resource.uri}")

            except Exception as e:
                logger.error(f"Error listing objects in bucket {bucket_name}: {str(e)}")

        semaphore = asyncio.Semaphore(3)
        async def process_bucket_with_semaphore(bucket):
            async with semaphore:
                await process_bucket(bucket)

        await asyncio.gather(*[process_bucket_with_semaphore(bucket) for bucket in buckets])

    except Exception as e:
        logger.error(f"Error listing buckets: {str(e)}")
        raise

    logger.info(f"Returning {len(resources)} resources")
    return resources


@server.read_resource()
async def read_resource(uri: AnyUrl) -> str:
    """
    Read content from an OBS resource and return structured response.
    """
    uri_str = str(uri)
    logger.debug(f"Reading resource: {uri_str}")

    if not uri_str.startswith("obs://"):
        raise ValueError("Invalid OBS URI")

    from urllib.parse import unquote
    path = uri_str[6:]  # Remove "obs://"
    path = unquote(path)
    parts = path.split("/", 1)

    if len(parts) < 2:
        raise ValueError("Invalid OBS URI format")

    bucket_name = parts[0]
    key = parts[1]

    logger.debug(f"Attempting to read - Bucket: {bucket_name}, Key: {key}")

    try:
        response = await obs_resource.get_object(bucket_name, key)
        content_type = response.get("ContentType", "")
        logger.debug(f"Read MIME type response: {content_type}")

        content_type_mapping = {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "application/markdown",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "application/csv",
            "application/vnd.ms-excel": "application/csv"
        }

        export_mime_type = content_type_mapping.get(content_type, content_type)
        logger.debug(f"Export MIME type: {export_mime_type}")

        if 'Body' in response:
            if isinstance(response['Body'], bytes):
                data = response['Body']
            else:
                async with response['Body'] as stream:
                    data = await stream.read()

            if obs_resource.is_text_file(key):
                text_content = base64.b64encode(data).decode('utf-8')
                return text_content
            else:
                text_content = str(base64.b64encode(data))
                result = ReadResourceResult(
                    contents=[
                        BlobResourceContents(
                            blob=text_content,
                            uri=uri_str,
                            mimeType=export_mime_type
                        )
                    ]
                )
                logger.debug(result)
                return text_content

        else:
            raise ValueError("No data in response body")

    except Exception as e:
        logger.error(f"Error reading object {key} from bucket {bucket_name}: {str(e)}")
        if 'NoSuchKey' in str(e):
            try:
                objects = await obs_resource.list_objects(bucket_name, prefix=key.split('/')[0])
                similar_objects = [obj['Key'] for obj in objects if 'Key' in obj]
                logger.debug(f"Similar objects found: {similar_objects}")
            except Exception as list_err:
                logger.error(f"Error listing similar objects: {str(list_err)}")
        raise ValueError(f"Error reading resource: {str(e)}")


@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    return [
        Tool(
            name="ListBuckets",
            description="Returns a list of buckets owned by the authenticated account. Constrained by OBS_MAX_BUCKETS and the OBS_BUCKETS allow-list when configured.",
            inputSchema={
                "type": "object",
                "properties": {
                    "start_after": {"type": "string", "description": "Start listing after this bucket name"}
                },
                "required": [],
            },
        ),
        Tool(
            name="ListObjects",
            description="Returns some or all (up to 1,000) of the objects in a bucket. Use the prefix parameter to filter by key prefix.",
            inputSchema={
                "type": "object",
                "properties": {
                    "bucket_name": {"type": "string", "description": "Name of the bucket to list objects from."},
                    "prefix": {"type": "string", "description": "The key prefix used to filter objects."},
                    "max_keys": {"type": "integer", "description": "Maximum number of keys returned (default 1,000)."}
                },
                "required": ["bucket_name"],
            },
        ),
        Tool(
            name="GetObject",
            description="Retrieves an object from Object Storage. Specify the full key name for the object.",
            inputSchema={
                "type": "object",
                "properties": {
                    "bucket_name": {"type": "string", "description": "Name of the bucket containing the object."},
                    "key": {"type": "string", "description": "Key of the object to get. Minimum length of 1."},
                    "max_retries": {"type": "string", "description": "Maximum number of attempts to download the file."},
                },
                "required": ["bucket_name", "key"],
            },
        ),
    ]


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[TextContent | ImageContent | EmbeddedResource]:
    logger.info(f"handle_call_tool got name {name}, args {arguments}")
    try:
        match name:
            case "ListBuckets":
                start_after = arguments.get("start_after", None) if arguments else None
                buckets = await obs_resource.list_buckets(start_after)
                logger.info(f"listBuckets returning buckets {buckets}")
                return [TextContent(type="text", text=str(buckets))]

            case "ListObjects":
                args = {"bucket_name": arguments['bucket_name']}
                if 'prefix' in arguments:
                    args['prefix'] = arguments['prefix']
                if "max_retries" in arguments:
                    args['max_retries'] = arguments['max_retries']

                objects = await obs_resource.list_objects(**args)
                logger.info(f"ListObjects returning objects {objects}")
                return [TextContent(type="text", text=str(objects))]

            case "GetObject":
                args = {
                    "bucket_name": arguments['bucket_name'],
                    "key": arguments['key'],
                }
                if "max_retries" in arguments:
                    args['max_retries'] = arguments['max_retries']
                response = await obs_resource.get_object(**args)
                logger.info(f"GetObject got response for {args['key']}")
                file_content = response['Body'].read().decode('utf-8')
                logger.info(f"GetObject got file_content length {len(file_content)}")
                return [TextContent(type="text", text=str(file_content))]

    except Exception as error:
        return [TextContent(type="text", text=f"Error: {str(error)}")]


async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="obs-mcp-server",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
