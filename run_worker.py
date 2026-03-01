"""Run the worker that processes Service Bus messages."""

import asyncio

from mcp_api_mock_gen.worker import run_worker

asyncio.run(run_worker())
