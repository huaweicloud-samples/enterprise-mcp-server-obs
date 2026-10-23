from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import asyncio
import os
import sys

async def main():
    # Absolute path to the server script (same directory as this client)
    server_script = os.path.join(os.path.dirname(__file__), "obs_mcp_server/server.py")

    server_params = StdioServerParameters(
        command=sys.executable,  # Python interpreter
        args=[server_script],    # Path to the server script
        env=None                 # Optional environment variables
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            resources = await session.list_resources()
            for resource in resources:
                print(f"Resource: {resource.name} ({resource.uri})")

if __name__ == "__main__":
    asyncio.run(main())
