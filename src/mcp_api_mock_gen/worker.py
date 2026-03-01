"""Worker that processes mock API creation jobs from Service Bus.

Receives messages from the 'mock-api-jobs' queue, runs the codegen pipeline,
and updates job state in CosmosDB.
"""

from __future__ import annotations

import json
import logging

from azure.identity import DefaultAzureCredential
from azure.servicebus.aio import ServiceBusClient

from .config import Settings
from .state import update_job

logger = logging.getLogger(__name__)

_QUEUE_NAME = "mock-api-jobs"


async def _process_message(msg_body: dict, settings: Settings) -> None:
    """Run the codegen pipeline for a single message."""
    deployment_id = msg_body["deployment_id"]
    name = msg_body["name"]
    sample_records = msg_body["sample_records"]
    record_count = msg_body.get("record_count", 0)
    data_description = msg_body.get("data_description", "")

    logger.info("Processing job %s: resource=%s, record_count=%d", deployment_id, name, record_count)

    try:
        from .codegen import run_codegen

        result = await run_codegen(
            resource_name=name,
            sample_records=sample_records,
            settings=settings,
            record_count=record_count,
            data_description=data_description,
            deployment_id=deployment_id,
        )

        update_job(settings.cosmos_endpoint, deployment_id, {
            "status": result["status"],
            "api_base_url": result.get("api_base_url"),
            "cosmos_database": result.get("cosmos_database"),
            "cosmos_container": result.get("cosmos_container"),
            "container_app_name": result.get("container_app_name"),
            "endpoints": result.get("endpoints", []),
            "records_seeded": result.get("records_seeded", 0),
            "records_generated": result.get("records_generated", 0),
            "error": result.get("error"),
        })
        logger.info("Job %s completed with status=%s", deployment_id, result["status"])

    except Exception as e:
        logger.exception("Job %s failed", deployment_id)
        update_job(settings.cosmos_endpoint, deployment_id, {
            "status": "failed",
            "error": str(e),
        })
        raise


async def run_worker() -> None:
    """Run the worker loop, processing messages from Service Bus indefinitely."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    logger.info("Starting worker...")

    settings = Settings.from_env()
    namespace = settings.service_bus_namespace
    credential = DefaultAzureCredential()

    async with ServiceBusClient(fully_qualified_namespace=namespace, credential=credential) as sb_client:
        receiver = sb_client.get_queue_receiver(queue_name=_QUEUE_NAME)
        async with receiver:
            logger.info("Listening on queue '%s' at %s", _QUEUE_NAME, namespace)
            async for msg in receiver:
                try:
                    body = json.loads(str(msg))
                    await _process_message(body, settings)
                    await receiver.complete_message(msg)
                    logger.info("Message completed for job %s", body.get("deployment_id"))
                except Exception:
                    logger.exception("Failed to process message, dead-lettering")
                    await receiver.dead_letter_message(msg, reason="ProcessingFailed")
