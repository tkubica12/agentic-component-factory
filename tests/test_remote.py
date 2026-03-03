"""Remote test client - tests MCP server running in Azure (async pattern).

Uses poll loop: create -> poll status -> test CRUD -> delete.
"""

import asyncio
import json
import sys
import os
import time
import urllib.request
import urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from fastmcp import Client

MCP_URL = os.environ.get("MCP_URL", "https://mcp-api-mock-gen.whitebay-138fe014.swedencentral.azurecontainerapps.io/mcp")

SAMPLE_PRODUCTS = [
    {"id": "1", "name": "Wireless Mouse", "price": 29.99, "category": "electronics", "in_stock": True},
    {"id": "2", "name": "Mechanical Keyboard", "price": 89.99, "category": "electronics", "in_stock": True},
    {"id": "3", "name": "USB-C Hub", "price": 49.99, "category": "accessories", "in_stock": False},
]


def _parse(result):
    for item in result.content:
        if hasattr(item, "text"):
            try: return json.loads(item.text)
            except Exception: pass
    return {}


def _http(method, url, body=None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, method=method, data=data)
    if data: req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode() if e.fp else ""


async def poll_status(client, deployment_id, timeout=600, interval=15):
    start = time.time()
    while time.time() - start < timeout:
        result = await client.call_tool("get_deployment_status", {"deployment_id": deployment_id}, raise_on_error=False)
        data = _parse(result)
        status = data.get("status", "unknown")
        print(f"  Status: {status} ({int(time.time()-start)}s)")
        if status in ("succeeded", "failed"):
            return data
        await asyncio.sleep(interval)
    return {"status": "timeout"}


def test_crud(base_url, resource, expected_min=3):
    passed = failed = 0
    def check(name, ok, detail=""):
        nonlocal passed, failed
        if ok: print(f"  PASS: {name}"); passed += 1
        else: print(f"  FAIL: {name} {detail}"); failed += 1

    url = f"{base_url}/api/{resource}"
    for i in range(12):
        try:
            s, _ = _http("GET", url)
            if s < 500: break
        except Exception: pass
        time.sleep(10); print(f"  Waiting... ({(i+1)*10}s)")

    s, body = _http("GET", url)
    check("GET list 200", s == 200, f"got {s}")
    items = json.loads(body) if s == 200 else []
    check(f"GET list >= {expected_min}", len(items) >= expected_min, f"got {len(items)}")
    print(f"  INFO: {len(items)} records")

    # Test query param filtering (limit/offset must not crash the API)
    s, body = _http("GET", f"{url}?limit=2")
    check("GET ?limit=2 returns 200", s == 200, f"got {s}")
    if s == 200:
        limited = json.loads(body)
        check("GET ?limit=2 returns <= 2", len(limited) <= 2, f"got {len(limited)}")

    s, body = _http("GET", f"{url}?limit=2&offset=1")
    check("GET ?limit=2&offset=1 returns 200", s == 200, f"got {s}")

    s, body = _http("GET", f"{url}/1"); check("GET /1 200", s == 200, f"got {s}")
    s, body = _http("POST", url, {"name": "Test", "price": 5.0, "category": "test", "in_stock": True})
    check("POST 200/201", s in (200, 201), f"got {s}")
    cid = json.loads(body).get("id") if s in (200, 201) else None
    if cid:
        s, _ = _http("GET", f"{url}/{cid}"); check("GET created 200", s == 200)
        s, _ = _http("PATCH", f"{url}/{cid}", {"price": 7.5}); check("PATCH 200", s == 200)
        s, _ = _http("DELETE", f"{url}/{cid}"); check("DELETE 200/204", s in (200, 204))
        s, _ = _http("GET", f"{url}/{cid}"); check("GET deleted 404", s == 404)
    return passed, failed


async def main():
    print("=" * 60)
    print(f"Remote MCP - Async E2E Test")
    print(f"MCP URL: {MCP_URL}")
    print("=" * 60)

    async with Client(MCP_URL) as client:
        tools = await client.list_tools()
        print(f"\nTools: {[t.name for t in tools]}")

        print(f"\n{'='*60}")
        print("create_mock_api (async)")
        print(f"{'='*60}")
        result = await client.call_tool("create_mock_api", {
            "name": "products", "sample_records": SAMPLE_PRODUCTS,
            "record_count": 10,
            "data_description": "realistic tech products $5-$500",
        }, raise_on_error=False, timeout=120)
        data = _parse(result)
        dep_id = data.get("deployment_id")
        print(f"  Started: deployment_id={dep_id}")

        if not dep_id:
            print("FAILED"); return

        print(f"\n{'='*60}")
        print(f"Polling status...")
        print(f"{'='*60}")
        final = await poll_status(client, dep_id)
        print(f"\nResult: {json.dumps(final, indent=2)}")

        api_url = final.get("api_base_url")
        if final.get("status") == "succeeded" and api_url:
            print(f"\n{'='*60}")
            print(f"CRUD Tests")
            print(f"{'='*60}")
            p, f = test_crud(api_url, "products", expected_min=5)
            print(f"\nCRUD: {p} passed, {f} failed")

            print(f"\n{'='*60}")
            print(f"Deleting...")
            print(f"{'='*60}")
            dr = await client.call_tool("delete_mock_api", {"deployment_id": dep_id}, raise_on_error=False, timeout=120)
            print(f"  Delete: {_parse(dr).get('status')}")
        else:
            print(f"FAILED: {final.get('error')}")

    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
