#!/usr/bin/env python3
"""Read files from the live game through the GreyLLM hook."""
import json
import socket
import sys

def call(req):
    s = socket.create_connection(("127.0.0.1", 7788), timeout=10)
    s.sendall((json.dumps(req) + "\n").encode())
    buf = b""
    while not buf.endswith(b"\n"):
        c = s.recv(65536)
        if not c:
            break
        buf += c
    s.close()
    return json.loads(buf.decode())

if __name__ == "__main__":
    tail = int(sys.argv[2]) if len(sys.argv) > 2 else 2000
    d = call({"op": "read", "path": sys.argv[1]})
    print((d.get("content") or "")[-tail:])
