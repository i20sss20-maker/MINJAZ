#!/usr/bin/env python3
"""Read-only smoke checks for MINJAZ sandbox. Never creates accounts or orders."""
import json
import os
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

BASE = os.getenv("MINJAZ_SMOKE_URL", "https://minjaz-digital-services-api-sandbox.up.railway.app").rstrip("/")

def check(path, expected, key=None):
    req=Request(BASE+path,headers={"Accept":"application/json","User-Agent":"MINJAZ-sandbox-smoke/1"})
    try:
        with urlopen(req,timeout=15) as response:
            status=response.status
            body=response.read(131072)
    except HTTPError as error:
        status=error.code
        body=error.read(131072)
    data=json.loads(body.decode("utf-8")) if body else {}
    if status!=expected or (key is not None and key not in data):
        raise AssertionError(f"{path}: expected {expected} and key {key}, got {status} {str(data)[:250]}")
    print(f"PASS {path}: HTTP {status}")

def main():
    check("/api/digital-services/catalog",200,"services")
    check("/api/digital-services/catalog?category=unknown",400,"error")
    check("/api/digital-services/orders",401,"error")
    check("/api/digital-services/orders/1",401,"error")
    print("All read-only sandbox checks passed.")

if __name__=="__main__":
    try: main()
    except (AssertionError,URLError,ValueError,TimeoutError) as error:
        print(f"FAIL: {error}",file=sys.stderr)
        sys.exit(1)
