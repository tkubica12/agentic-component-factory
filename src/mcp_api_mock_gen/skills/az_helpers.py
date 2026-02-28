"""Shared async helpers for running Azure CLI commands without blocking the event loop."""

from __future__ import annotations

import asyncio
import json
import logging
import os

logger = logging.getLogger(__name__)


async def az_async(args: list[str], check: bool = True, timeout: int = 300, env_extra: dict | None = None) -> tuple[int, str, str]:
    """Run an Azure CLI command asynchronously. Returns (returncode, stdout, stderr)."""
    cmd = ["az"] + args + ["--output", "json"]
    logger.info("az %s", " ".join(args[:8]))

    env = {**os.environ, **(env_extra or {})}

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise RuntimeError(f"az {' '.join(args[:5])}... timed out after {timeout}s")

    stdout = stdout_bytes.decode() if stdout_bytes else ""
    stderr = stderr_bytes.decode() if stderr_bytes else ""

    if check and proc.returncode != 0:
        raise RuntimeError(f"az {' '.join(args[:5])}... failed: {stderr[:500]}")

    return proc.returncode, stdout, stderr


async def run_script_async(cmd: list[str], cwd: str | None = None, timeout: int = 300, env_extra: dict | None = None) -> tuple[int, str, str]:
    """Run an arbitrary command asynchronously. Returns (returncode, stdout, stderr)."""
    env = {**os.environ, **(env_extra or {})}

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=env,
    )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise RuntimeError(f"Command timed out after {timeout}s")

    stdout = stdout_bytes.decode() if stdout_bytes else ""
    stderr = stderr_bytes.decode() if stderr_bytes else ""
    return proc.returncode, stdout, stderr
