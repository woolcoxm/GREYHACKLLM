#!/usr/bin/env python3
"""Test client for the GreyLLM Hook plugin.

Usage:
  python tools/hook-client.py health
  python tools/hook-client.py read /home/<you>/.greyllm/prompt.txt
  python tools/hook-client.py write /path "content"
  python tools/hook-client.py list /home
  python tools/hook-client.py run tools/hello-ingame.src
"""
import json
import socket
import sys
import time

HOST, PORT = "127.0.0.1", 7788


def call(request, timeout=330):
    with socket.create_connection((HOST, PORT), timeout=10) as sock:
        sock.settimeout(timeout)
        sock.sendall((json.dumps(request) + "\n").encode("utf-8"))
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = sock.recv(65536)
            if not chunk:
                break
            buf += chunk
        return json.loads(buf.decode("utf-8"))


def main():
    op = sys.argv[1] if len(sys.argv) > 1 else "health"
    if op == "health":
        req = {"op": "health"}
    elif op == "read":
        req = {"op": "read", "path": sys.argv[2]}
    elif op == "write":
        req = {"op": "write", "path": sys.argv[2], "content": sys.argv[3]}
    elif op in ("exists", "list", "mkdir", "delete"):
        req = {"op": op, "path": sys.argv[2]}
    elif op == "run":
        with open(sys.argv[2], encoding="utf-8") as f:
            req = {
                "op": "run",
                "code": f.read(),
                "params": sys.argv[3:],
                "timeout": 120,
            }
    else:
        print(f"unknown op {op}")
        sys.exit(1)

    started = time.time()
    result = call(req)
    elapsed = time.time() - started
    print(json.dumps(result, indent=2)[:4000])
    print(f"-- {elapsed:.2f}s")


if __name__ == "__main__":
    main()
