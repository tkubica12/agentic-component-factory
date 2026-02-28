"""Script execution skill for GitHub Copilot SDK.

Runs Python scripts in a working directory using the MCP server's Python interpreter.
"""

from __future__ import annotations

import json
import logging
import sys

from .az_helpers import run_script_async

logger = logging.getLogger(__name__)


class ScriptSkills:
    """Skills for executing generated Python scripts."""

    def __init__(self, env_overrides: dict[str, str] | None = None):
        self.env_overrides = env_overrides or {}

    async def run_python_script(self, script_path: str, working_directory: str) -> str:
        """Run a Python script and return its stdout/stderr."""
        python = sys.executable

        logger.info("Running script: %s in %s", script_path, working_directory)
        try:
            returncode, stdout, stderr = await run_script_async(
                [python, script_path],
                cwd=working_directory,
                timeout=300,
                env_extra=self.env_overrides,
            )

            output = stdout[-2000:] if stdout else ""
            errors = stderr[-2000:] if stderr else ""

            if returncode != 0:
                logger.error("Script failed (exit %d): %s", returncode, errors[:500])
                return json.dumps({
                    "status": "error",
                    "exit_code": returncode,
                    "stdout": output,
                    "stderr": errors,
                    "message": f"Script failed with exit code {returncode}. Fix the script and retry.",
                })

            logger.info("Script succeeded: %s", output[:200])
            return json.dumps({
                "status": "ok",
                "exit_code": 0,
                "stdout": output,
                "stderr": errors,
            })

        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})
