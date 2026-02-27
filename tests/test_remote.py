"""Remote test client — tests MCP server running in Azure Container Apps."""

import asyncio
import json
import sys
import os
import time
import urllib.request
import urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from fastmcp import Client

MCP_URL = os.environ.get(
    "MCP_URL",
    "https://mcp-api-mock-gen.kindstone-92a455f4.swedencentral.azurecontainerapps.io/mcp",
)

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


def _wait_for_ready(base_url, resource, max_wait=120):
    url = f"{base_url}/api/{resource}"
    for i in range(max_wait // 10):
        try:
            status, body = _http("GET", url, timeout=15)
            if status < 500:
                return True
        except Exception:
            pass
        print(f"  Waiting for API... ({(i+1)*10}s)")
        time.sleep(10)
    return False


def test_crud(base_url, resource, expected_min=3):
    passed = failed = 0

    def check(name, ok, detail=""):
        nonlocal passed, failed
        if ok:
            print(f"  PASS: {name}")
            passed += 1
        else:
            print(f"  FAIL: {name} {detail}")
            failed += 1

    url = f"{base_url}/api/{resource}"

    status, body = _http("GET", url)
    check("GET list 200", status == 200, f"got {status}")
    items = json.loads(body) if status == 200 else []
    check(f"GET list >= {expected_min} records", len(items) >= expected_min, f"got {len(items)}")
    print(f"  INFO: Total records: {len(items)}")

    status, body = _http("GET", f"{url}/1")
    check("GET /1 returns 200", status == 200, f"got {status}")

    new_item = {"name": "Test Widget", "price": 5.0, "category": "test", "in_stock": True}
    status, body = _http("POST", url, new_item)
    check("POST 200/201", status in (200, 201), f"got {status}")
    cid = json.loads(body).get("id") if status in (200, 201) else None

    if cid:
        status, _ = _http("GET", f"{url}/{cid}")
        check("GET created 200", status == 200, f"got {status}")
        status, body = _http("PATCH", f"{url}/{cid}", {"price": 7.5})
        check("PATCH 200", status == 200, f"got {status}")
        status, _ = _http("DELETE", f"{url}/{cid}")
        check("DELETE 200/204", status in (200, 204), f"got {status}")
        status, _ = _http("GET", f"{url}/{cid}")
        check("GET deleted 404", status == 404, f"got {status}")

    return passed, failed


async def main():
    print("=" * 60)
    print("Remote MCP Server - E2E Test")
    print(f"MCP URL: {MCP_URL}")
    print("=" * 60)

    async with Client(MCP_URL) as client:
        tools = await client.list_tools()
        print(f"\nTools: {[t.name for t in tools]}")

        # Create with data generation
        print(f"\n{'='*60}")
        print("create_mock_api with record_count=10")
        print(f"{'='*60}")
        result = await client.call_tool(
            "create_mock_api",
            {
                "name": "products",
                "sample_records": SAMPLE_PRODUCTS,
                "record_count": 10,
                "data_description": "realistic tech products with varied categories and pricing $5-$500",
            },
            raise_on_error=False,
            timeout=900,
        )
        print("\nResult:")
        _print_result(result)

        api_url = _extract_field(result, "api_base_url")
        dep_id = _extract_field(result, "deployment_id")

        if _extract_field(result, "status") == "succeeded" and api_url:
            print(f"\n{'='*60}")
            print(f"CRUD Tests at {api_url}")
            print(f"{'='*60}")
            if _wait_for_ready(api_url, "products"):
                p, f = test_crud(api_url, "products", expected_min=5)
                print(f"\nCRUD: {p} passed, {f} failed")

            print(f"\n{'='*60}")
            print(f"delete_mock_api('{dep_id}')")
            print(f"{'='*60}")
            dr = await client.call_tool("delete_mock_api", {"deployment_id": dep_id}, raise_on_error=False, timeout=120)
            print("\nResult:")
            _print_result(dr)
        else:
            print("CREATE FAILED")

    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
