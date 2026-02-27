"""Test client for the MCP server using FastMCP Client.

Tests both create_mock_api and delete_mock_api, and verifies
that the deployed API actually works with CRUD operations.
"""

import asyncio
import json
import sys
import os
import time
import urllib.request
import urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from fastmcp import Client
from mcp_api_mock_gen.server import mcp


SAMPLE_PRODUCTS = [
    {"id": "1", "name": "Wireless Mouse", "price": 29.99, "category": "electronics", "in_stock": True},
    {"id": "2", "name": "Mechanical Keyboard", "price": 89.99, "category": "electronics", "in_stock": True},
    {"id": "3", "name": "USB-C Hub", "price": 49.99, "category": "accessories", "in_stock": False},
]


def _print_result(result):
    if result.is_error:
        print("ERROR!")
    for item in result.content:
        if hasattr(item, "text"):
            try:
                parsed = json.loads(item.text)
                print(json.dumps(parsed, indent=2))
            except json.JSONDecodeError:
                print(item.text)
        else:
            print(item)


def _extract_field(result, field):
    for item in result.content:
        if hasattr(item, "text"):
            try:
                return json.loads(item.text).get(field)
            except Exception:
                pass
    return None


def _http(method, url, body=None, timeout=30):
    """Simple HTTP helper that returns (status, body_str)."""
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, method=method, data=data)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode() if e.fp else ""


def _wait_for_ready(base_url, resource, max_wait=90):
    """Wait for the container to be ready, retrying every 10s."""
    url = f"{base_url}/api/{resource}"
    for i in range(max_wait // 10):
        try:
            status, body = _http("GET", url, timeout=15)
            if status < 500:
                return True
        except Exception:
            pass
        print(f"  Waiting for API to be ready... ({(i+1)*10}s)")
        time.sleep(10)
    return False


def test_crud(base_url, resource):
    """Test all CRUD operations on the deployed API. Returns (passed, failed) counts."""
    passed = 0
    failed = 0

    def check(name, condition, detail=""):
        nonlocal passed, failed
        if condition:
            print(f"  PASS: {name}")
            passed += 1
        else:
            print(f"  FAIL: {name} {detail}")
            failed += 1

    url = f"{base_url}/api/{resource}"

    # GET list — should return seeded data
    status, body = _http("GET", url)
    check("GET list returns 200", status == 200, f"got {status}")
    items = json.loads(body) if status == 200 else []
    check("GET list returns seeded records", len(items) >= 3, f"got {len(items)} items")

    # GET by ID
    status, body = _http("GET", f"{url}/1")
    check("GET /1 returns 200", status == 200, f"got {status}")
    if status == 200:
        item = json.loads(body)
        check("GET /1 has correct name", item.get("name") == "Wireless Mouse", f"got {item.get('name')}")

    # POST new record
    new_item = {"id": "test-99", "name": "Test Widget", "price": 5.0, "category": "test", "in_stock": True}
    status, body = _http("POST", url, new_item)
    check("POST returns 200/201", status in (200, 201), f"got {status}")
    created_id = None
    if status in (200, 201):
        created = json.loads(body)
        created_id = created.get("id", "test-99")

    # GET the new record (use the ID returned by POST, which may be auto-generated)
    if created_id:
        status, body = _http("GET", f"{url}/{created_id}")
        check("GET created record returns 200", status == 200, f"got {status} for id={created_id}")

        # PATCH the record
        status, body = _http("PATCH", f"{url}/{created_id}", {"price": 7.5})
        check("PATCH returns 200", status == 200, f"got {status}")
        if status == 200:
            patched = json.loads(body)
            check("PATCH updated price", patched.get("price") == 7.5, f"got {patched.get('price')}")

        # DELETE the record
        status, body = _http("DELETE", f"{url}/{created_id}")
        check("DELETE returns 200/204", status in (200, 204), f"got {status}")

        # Verify deleted
        status, body = _http("GET", f"{url}/{created_id}")
        check("GET deleted record returns 404", status == 404, f"got {status}")
    else:
        check("POST returned a valid record", False, "no id in response")

    return passed, failed


async def main():
    print("=" * 60)
    print("MCP API Mock Generator - E2E Test")
    print("=" * 60)

    async with Client(mcp) as client:
        tools = await client.list_tools()
        print(f"\nAvailable tools: {[t.name for t in tools]}")

        # --- Create ---
        print(f"\n{'='*60}")
        print(f"STEP 1: create_mock_api('products', {len(SAMPLE_PRODUCTS)} records)")
        print(f"{'='*60}")
        result = await client.call_tool(
            "create_mock_api",
            {"name": "products", "sample_records": SAMPLE_PRODUCTS},
            raise_on_error=False,
            timeout=900,
        )
        print("\nResult:")
        _print_result(result)

        api_url = _extract_field(result, "api_base_url")
        deployment_id = _extract_field(result, "deployment_id")
        status = _extract_field(result, "status")

        if status != "succeeded" or not api_url:
            print("\nCREATE FAILED — cannot test CRUD. Exiting.")
            return

        # --- CRUD tests ---
        print(f"\n{'='*60}")
        print(f"STEP 2: Testing CRUD at {api_url}")
        print(f"{'='*60}")

        print("\nWaiting for container to be ready...")
        if not _wait_for_ready(api_url, "products"):
            print("API never became ready. Skipping CRUD tests.")
        else:
            passed, failed = test_crud(api_url, "products")
            print(f"\nCRUD Tests: {passed} passed, {failed} failed")

        # --- Delete ---
        print(f"\n{'='*60}")
        print(f"STEP 3: delete_mock_api('{deployment_id}')")
        print(f"{'='*60}")
        delete_result = await client.call_tool(
            "delete_mock_api",
            {"deployment_id": deployment_id},
            raise_on_error=False,
            timeout=120,
        )
        print("\nResult:")
        _print_result(delete_result)

    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
