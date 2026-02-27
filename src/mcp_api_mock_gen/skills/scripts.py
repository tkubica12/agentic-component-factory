"""Script execution skill for GitHub Copilot SDK.

Runs Python scripts in a working directory using the MCP server's Python interpreter.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys

logger = logging.getLogger(__name__)


class ScriptSkills:
    """Skills for executing generated Python scripts."""

    def __init__(self, env_overrides: dict[str, str] | None = None):
        self.env_overrides = env_overrides or {}

    def run_python_script(self, script_path: str, working_directory: str) -> str:
        """Run a Python script and return its stdout/stderr."""
        python = sys.executable
        env = {**os.environ, **self.env_overrides}

        logger.info("Running script: %s in %s", script_path, working_directory)
        try:
            result = subprocess.run(
                [python, script_path],
                capture_output=True,
                text=True,
                timeout=300,
                cwd=working_directory,
                env=env,
            )

            output = result.stdout[-2000:] if result.stdout else ""
            errors = result.stderr[-2000:] if result.stderr else ""

            if result.returncode != 0:
                logger.error("Script failed (exit %d): %s", result.returncode, errors[:500])
                return json.dumps({
                    "status": "error",
                    "exit_code": result.returncode,
                    "stdout": output,
                    "stderr": errors,
                    "message": f"Script failed with exit code {result.returncode}. Fix the script and retry.",
                })

            logger.info("Script succeeded: %s", output[:200])
            return json.dumps({
                "status": "ok",
                "exit_code": 0,
                "stdout": output,
                "stderr": errors,
            })

        except subprocess.TimeoutExpired:
            return json.dumps({"status": "error", "message": "Script timed out after 300s"})
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})
