#!/usr/bin/env python3
"""Diagnostic: fetch /bin/agent from the game hook and report markers."""
import json
import re
import socket
import sys

req = {"op": "read", "path": "/bin/agent"}
s = socket.create_connection(("127.0.0.1", 7788), timeout=10)
s.sendall((json.dumps(req) + "\n").encode())
buf = b""
while not buf.endswith(b"\n"):
    chunk = s.recv(65536)
    if not chunk:
        break
    buf += chunk
s.close()
data = json.loads(buf.decode())
content = data.get("content") or ""
print("ok:", data.get("ok"))
print("installed length:", len(content))
print("AGENT_VERSION:", re.search(r'AGENT_VERSION = "(\d+)"', content).group(1))
print("thinking stream:", "thinking.txt" in content)
print("disk sysinfo:", "bytes total" in content)
print("interactive chat:", "interactive session" in content)
print("tail:", repr(content[-90:]))
sys.exit(0)
