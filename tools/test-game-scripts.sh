#!/usr/bin/env bash
# Integration tests for the GreyLLM in-game scripts, run in the greybel
# Mock environment (a faithful reimplementation of the Grey Hack runtime).
# Timeouts are shortened so every path finishes in seconds.
#
# Covers agent.src (bridge chat) and the v30 plague tool exploit.src:
# planner decisions, sweep-stop, verdict protocol, local -L ladder,
# epidemic guards, list mode, and the metaxploit FATAL path.
set -u
cd "$(dirname "$0")/.."

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

sed -e 's/STALL_TIMEOUT = [0-9]*/STALL_TIMEOUT = 2/' \
    -e 's/while waited < 60/while waited < 2/' \
    game/agent.src > "$WORK/agent.src"

# a copy with NO metaxploit path default — exercises the FATAL guard
sed 's|"/lib/metaxploit.so"|"nosuchlib.so"|g' \
    game/exploit.src > "$WORK/exploit-nometax.src"

PASS=0
FAIL=0

# check NAME EXPECT [args...] — runs $SRCTGT with the given program args
SRCTGT="$WORK/agent.src"
check() {
    local name="$1"; shift
    local expect="$1"; shift
    local out
    if [ $# -gt 0 ]; then
        out=$(npx greybel execute -et Mock -p "$@" -- "$SRCTGT" 2>&1)
    else
        out=$(npx greybel execute -et Mock -- "$SRCTGT" 2>&1)
    fi
    if echo "$out" | grep -q "$expect"; then
        echo "PASS  $name"
        PASS=$((PASS + 1))
    else
        echo "FAIL  $name"
        echo "      expected: $expect"
        echo "      got: ${out:0:300}"
        FAIL=$((FAIL + 1))
    fi
}

# ---- agent (bridge chat) ----

check "agent: no args opens chat session" "interactive session" ""
check "agent: -t bridge test"            "bridge files live in" -t
check "agent: -t times out gracefully"   "no answer within" -t
check "agent: -r no answer yet"          "no answer yet" -r
check "agent: -s no answer yet"          "no answer yet" -s foo
check "agent: task sends joined prompt"  "task sent: hello world task" hello world task
check "agent: task enters serve loop"    "timed out waiting" hello

# ---- plague (exploit.src v30+) ----
# the Mock environment simulates a deterministic vulnerable host at
# 1.2.3.4: the sweep finds a guest shell + a root computer foothold,
# which drives the planner through sweep-stop -> secure -> finish.

SRCTGT=game/exploit.src

check "plague: invalid ip rejected"       "invalid ip: 999.999.999.999" 999.999.999.999
check "plague: assault reaches a verdict" "VERDICT OWNED" 1.2.3.4
check "plague: sweep stops at root"       "SWEEP-STOP" 1.2.3.4
check "plague: planner secures durable"   "[secure]" 1.2.3.4
check "plague: verdict names the access"  "VERDICT OWNED root" 1.2.3.4
check "plague: list mode fires nothing"   "(listed)" -l 1.2.3.4
check "plague: local -L ladder"           "LSTATUS" -L
check "plague: local -L verdict"          "=== exploit done ===" -L
check "plague: epidemic self-heal guard"  "no ~/exploit binary" -cycles=1
check "plague: scan mode writes targets"  "scan complete" -scan

SRCTGT="$WORK/exploit-nometax.src"
check "plague: FATAL without metaxploit"  "FATAL no metaxploit" -L

echo
echo "passed: $PASS  failed: $FAIL"
[ "$FAIL" -eq 0 ]
