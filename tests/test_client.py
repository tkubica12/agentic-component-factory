"""Test client for the MCP server using FastMCP Client.

Tests create_mock_api (with and without data generation) and delete_mock_api,
and verifies that the deployed API actually works with CRUD operations.
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


def test_crud(base_url, resource, expected_min_records=3):
    """Test CRUD operations. Returns (passed, failed) counts."""
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

    # GET list
    status, body = _http("GET", url)
    check("GET list returns 200", status == 200, f"got {status}")
    items = json.loads(body) if status == 200 else []
    check(f"GET list has >= {expected_min_records} records", len(items) >= expected_min_records, f"got {len(items)} items")
    if items:
        print(f"  INFO: Total records in API: {len(items)}")

    # GET by ID
    status, body = _http("GET", f"{url}/1")
    check("GET /1 returns 200", status == 200, f"got {status}")
    if status == 200:
        item = json.loads(body)
        check("GET /1 has correct name", item.get("name") == "Wireless Mouse", f"got {item.get('name')}")

    # POST
    new_item = {"id": "test-crud", "name": "Test Widget", "price": 5.0, "category": "test", "in_stock": True}
    status, body = _http("POST", url, new_item)
    check("POST returns 200/201", status in (200, 201), f"got {status}")
    created_id = None
    if status in (200, 201):
        created_id = json.loads(body).get("id", "test-crud")

    if created_id:
        # GET created
        status, body = _http("GET", f"{url}/{created_id}")
        check("GET created returns 200", status == 200, f"got {status}")

        # PATCH
        status, body = _http("PATCH", f"{url}/{created_id}", {"price": 7.5})
        check("PATCH returns 200", status == 200, f"got {status}")
        if status == 200:
            check("PATCH updated price", json.loads(body).get("price") == 7.5)

        # DELETE
        status, body = _http("DELETE", f"{url}/{created_id}")
        check("DELETE returns 200/204", status in (200, 204), f"got {status}")

        # Verify deleted
        status, body = _http("GET", f"{url}/{created_id}")
        check("GET deleted returns 404", status == 404, f"got {status}")

    return passed, failed


async def main():
    print("=" * 60)
    print("MCP API Mock Generator - E2E Test")
    print("=" * 60)

    async with Client(mcp) as client:
        tools = await client.list_tools()
        print(f"\nAvailable tools: {[t.name for t in tools]}")

        # === Test 1: Create with data generation ===
        print(f"\n{'='*60}")
        print("TEST: create_mock_api with synthetic data generation")
        print(f"{'='*60}")
        result = await client.call_tool(
            "create_mock_api",
            {
                "name": "products",
                "sample_records": SAMPLE_PRODUCTS,
                "record_count": 10,
                "data_description": "realistic tech products with varied categories (electronics, accessories, peripherals, cables) and realistic pricing between $5 and $500",
            },
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

        # CRUD tests — expect at least 3 seeded + some generated
        print(f"\n{'='*60}")
        print(f"Testing CRUD at {api_url}")
        print(f"{'='*60}")

        if _wait_for_ready(api_url, "products"):
            passed, failed = test_crud(api_url, "products", expected_min_records=5)
            print(f"\nCRUD Tests: {passed} passed, {failed} failed")
        else:
            print("API never became ready.")

        # Delete
        print(f"\n{'='*60}")
        print(f"delete_mock_api('{deployment_id}')")
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
