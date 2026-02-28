"""ACR build skill for GitHub Copilot SDK.

Builds Docker images using Azure Container Registry remote build (az acr build).
Returns build output including errors so Copilot SDK can fix code issues.
"""

from __future__ import annotations

import json
import logging

from .az_helpers import az_async

logger = logging.getLogger(__name__)


class AcrSkills:
    """Skills for building Docker images via ACR remote build."""

    def __init__(self, acr_name: str, subscription_id: str):
        self.acr_name = acr_name
        self.subscription_id = subscription_id

    async def build_image(self, image_tag: str, code_directory: str) -> str:
        """Build a Docker image using ACR remote build. Returns build log on success or error details on failure."""
        try:
            # Use --no-logs to avoid Windows colorama encoding issues; check run status after
            returncode, stdout, stderr = await az_async([
                "acr", "build",
                "--registry", self.acr_name,
                "--subscription", self.subscription_id,
                "--image", image_tag,
                "--no-logs",
                code_directory,
            ], check=False, timeout=600, env_extra={"PYTHONIOENCODING": "utf-8", "NO_COLOR": "1"})

            if returncode != 0:
                error_output = (stderr + "\n" + stdout)[-2000:]
                logger.error("ACR build failed for %s: %s", image_tag, error_output[:500])
                return json.dumps({
                    "status": "error",
                    "message": f"Docker build failed. Fix the code and retry.\nBuild output:\n{error_output}",
                })

            logger.info("ACR build succeeded for %s", image_tag)
            return json.dumps({"status": "ok", "image": image_tag, "registry": self.acr_name})

        except Exception as e:
            logger.exception("ACR build exception")
            return json.dumps({"status": "error", "message": str(e)})
