#!/usr/bin/env bash
# Integration tests for the GreyLLM in-game scripts, run in the greybel
# Mock environment (a faithful reimplementation of the Grey Hack runtime).
# Timeouts are shortened so every path finishes in seconds.
set -u
cd "$(dirname "$0")/.."

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

sed -e 's/STALL_TIMEOUT = 300/STALL_TIMEOUT = 2/' \
    -e 's/while waited < 60/while waited < 2/' \
    game/agent.src > "$WORK/agent.src"
sed -e 's/TIMEOUT = 240/TIMEOUT = 2/' game/llm.src > "$WORK/llm.src"

PASS=0
FAIL=0

check() {
    local name="$1"; shift
    local expect="$1"; shift
    local out
    if [ $# -gt 0 ]; then
        out=$(npx greybel execute -et Mock -p "$@" -- "$WORK/agent.src" 2>&1)
    else
        out=$(npx greybel execute -et Mock -- "$WORK/agent.src" 2>&1)
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

checkl() {
    local name="$1"; shift
    local expect="$1"; shift
    local out
    if [ $# -gt 0 ]; then
        out=$(npx greybel execute -et Mock -p "$@" -- "$WORK/llm.src" 2>&1)
    else
        out=$(npx greybel execute -et Mock -- "$WORK/llm.src" 2>&1)
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

check "agent: no args shows usage"       "usage: agent" ""
check "agent: -t bridge test"            "bridge files live in" -t
check "agent: -t times out gracefully"   "no answer within" -t
check "agent: -r no answer yet"          "no answer yet" -r
check "agent: -s no answer yet"          "no answer yet" -s foo
check "agent: task sends joined prompt"  "task sent: hello world task" hello world task
check "agent: task enters serve loop"    "timed out waiting" hello

checkl "llm: no args shows usage"        "usage: llm" ""
checkl "llm: -t bridge test"             "testing bridge" -t
checkl "llm: prompt reaches wait"        "timeout: daemon did not answer" hello
checkl "llm: -r no reply yet"            "no reply yet" -r
checkl "llm: -w nothing to wait for"    "nothing to wait for" -w

echo
echo "passed: $PASS  failed: $FAIL"
[ "$FAIL" -eq 0 ]
