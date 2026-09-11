#!/usr/bin/env bash
# FLEET TEST — large-scale end-to-end exercise of the plague planner in
# the greybel Mock environment, in two truthful phases:
#
#   PHASE 1 "sweep"  — ONE process, N hosts (default 1000), no stub
#     binary built: recon, firing, ranking, crack, usepass logins,
#     harvest, verdicts, cleanup all run at scale. Deploy/spread is
#     skipped gracefully (no binary) — which also keeps the mock's
#     metaxploit node healthy: the mock's scp MOVES the source lib
#     (the real game copies and runs one process per host, so this
#     corruption cannot happen there).
#   PHASE 2 "ladder" — FLEETBATCHES fresh processes (default 40), each
#     building a stub ~/exploit and running the seeded rich host plus
#     two post-corruption hosts: the FULL ladder including deploy,
#     -L relay launch, spread launches, ledger cleanup; the trailing
#     hosts prove graceful degradation after the mock lib corruption.
#
# usage: bash tools/mock-fleet-test.sh [sweep-hosts]
set -u
cd "$(dirname "$0")/.."

HOSTS="${1:-120}"
BATCHES="${FLEETBATCHES:-40}"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

# harness = the real tool, entry call replaced by our fleet driver
sed 's/^main(params)$//' game/exploit.src > "$WORK/fleet.src"

cat >> "$WORK/fleet.src" <<'EOF'
// ---- FLEET DRIVER (test harness — not shipped to the game) ----

fleetMain = function(params)
	// params: ["ladder"] -> full-ladder mode (stub binary, 3 hosts)
	//         ["<N>"]    -> sweep mode (N hosts, no stub, no deploy)
	ladder = false
	hosts = 1000
	if params != null and params.len > 0 then
		if params[0] == "ladder" then
			ladder = true
			hosts = 3
		else
			h = val(params[0])
			if h != null and h > 0 then
				hosts = h
			end if
		end if
	end if
	comp = get_shell.host_computer
	globals.comp0 = comp
	globals.wComp = comp
	globals.durableUser = "greyllm"
	globals.durablePass = "Acc3ss2026x"
	globals.rootPassArg = "R00tPass26x"
	globals.exfilPath = home_dir + "/Desktop/bankintel.txt"
	globals.metaxPath = "/lib/metaxploit.so"
	globals.libDirVal = "/lib"
	globals.stealth = false
	globals.gArgVal = null
	globals.homeBase = home_dir
	globals.localBase = null
	globals.verdict = null
	globals.winners = []
	globals.winnersPath = null
	globals.wantArea = null
	globals.wantName = null
	globals.onlyPort = null
	globals.listOnly = false
	globals.quietFire = false
	globals.localRun = false
	globals.spreadDepth = 0
	globals.epBin = "exploit"
	globals.mintCount = 0
	globals.deployedBin = null
	globals.deployedMx = null
	globals.stagedBinPath = null
	globals.stagedBinName = null
	globals.stagedSrcPath = null
	globals.duds = []
	globals.dudsPath = null
	globals.persist = false
	if ladder then
		// stub child binary: a minimal program built as ~/exploit so
		// deploy/relay/spread launches run for real (the launched
		// child prints CHILD-OK; output pulls stay guarded nulls)
		bootSrc = "main = function(params)" + char(10) + char(9)
		bootSrc = bootSrc + "print(" + char(34) + "CHILD-OK" + char(34) + ")" + char(10)
		bootSrc = bootSrc + "end function" + char(10) + "main(params)" + char(10)
		bootF = ensureFile(comp, home_dir + "/exploit.src", bootSrc)
		if bootF != null then
			fbuild(get_shell, bootF.path, home_dir)
		end if
		print("FLEET-SETUP stub binary: " + (fget(comp, home_dir + "/exploit") != null))
	end if
	outP = home_dir + "/fleet_report.txt"
	ensureFile(comp, outP, " ")
	nTotal = 0
	nDead = 0
	nRootShell = 0
	nRootComp = 0
	nUser = 0
	nGuest = 0
	nNone = 0
	nCrashed = 0
	nSpread = 0
	nRelay = 0
	nCrack = 0
	nEvidence = 0
	nLibFail = 0
	for i in range(1, hosts)
		if i == 1 then
			// seed with the known-rich mock host so the full ladder
			// is always exercised; the rest stress every other path
			ip = "1.2.3.4"
		else
			o1 = 20 + i % 220
			o2 = 1 + (i * 7) % 250
			o3 = 1 + (i * 13) % 250
			o4 = 1 + (i * 29) % 250
			ip = o1 + "." + o2 + "." + o3 + "." + o4
		end if
		if is_valid_ip(ip) != 1 then
			continue
		end if
		nTotal = nTotal + 1
		globals.wOut = outP
		fwipe(fget(comp, outP))
		resetAssault()
		metax = finclude("/lib/metaxploit.so")
		if metax == null then
			// mock lib node consumed by an earlier host's deploy — the
			// real game runs one process per host, so this cannot
			// happen there; here we just record and move on
			nLibFail = nLibFail + 1
			continue
		end if
		globals.metaxGlobal = metax
		globals.modeIp = ip
		if get_shell.ping(ip) != 1 then
			nDead = nDead + 1
			continue
		end if
		runAssault(ip, metax)
		v = globals.verdict
		if v == null then
			nCrashed = nCrashed + 1
		else if containsStr(v, "root-shell") then
			nRootShell = nRootShell + 1
		else if containsStr(v, "root-computer") then
			nRootComp = nRootComp + 1
		else if containsStr(v, "OWNED user") then
			nUser = nUser + 1
		else if containsStr(v, "OWNED guest") then
			nGuest = nGuest + 1
		else
			nNone = nNone + 1
		end if
		if globals.spread then
			nSpread = nSpread + 1
		end if
		if globals.relayed then
			nRelay = nRelay + 1
		end if
		if globals.crackCount > 0 then
			nCrack = nCrack + 1
		end if
		if hasRoot() == false then
			nEvidence = nEvidence + 1
		end if
	end for
	print("FLEET-RESULT total=" + nTotal + " dead=" + nDead + " crashed=" + nCrashed + " libFail=" + nLibFail)
	print("FLEET-VERDICTS root-shell=" + nRootShell + " root-computer=" + nRootComp + " user=" + nUser + " guest=" + nGuest + " none=" + nNone)
	print("FLEET-ACTIONS spread=" + nSpread + " relayed=" + nRelay + " cracked=" + nCrack + " evidenceLeft=" + nEvidence)
	return null
end function

fleetMain(params)
EOF

fail=0

echo "=== PHASE 1: stability sweep — $HOSTS hosts in one process ==="
sweep=$(timeout 900 npx greybel execute -et Mock -p "$HOSTS" -- "$WORK/fleet.src" 2>&1)
sstatus=$?
echo "$sweep" | grep -E "^FLEET" || true
if [ $sstatus -ne 0 ]; then
    echo "FAIL sweep exited $sstatus — tail:"
    echo "$sweep" | tail -15
    exit 1
fi
if echo "$sweep" | grep -q "Runtime error"; then
    echo "FAIL runtime error during sweep"
    echo "$sweep" | grep "Runtime error" | head -3
    fail=1
fi
if echo "$sweep" | grep -q "FLEET-RESULT.*crashed=0 libFail=0"; then
    echo "PASS sweep: zero crashes, zero lib failures"
else
    echo "FAIL sweep: crashes or lib failures"
    fail=1
fi
total=$(echo "$sweep" | grep "FLEET-RESULT" | sed -n 's/.*total=\([0-9]*\).*/\1/p')
dead=$(echo "$sweep" | grep "FLEET-RESULT" | sed -n 's/.*dead=\([0-9]*\).*/\1/p')
classified=$(echo "$sweep" | grep "FLEET-VERDICTS" | awk -F'[= ]' '{print $3+$5+$7+$9+$11}')
if [ -n "$dead" ] && [ "$((total - dead))" = "$classified" ]; then
    echo "PASS sweep: all $((total - dead)) live hosts fully classified"
else
    echo "FAIL sweep accounting: total=$total dead=$dead classified=$classified"
    fail=1
fi

echo
echo "=== PHASE 2: full ladder — $BATCHES fresh processes ==="
agg_crashed=0; agg_owned=0; agg_spread=0; agg_relay=0; agg_runtime=0
for b in $(seq 1 "$BATCHES"); do
    lout=$(timeout 120 npx greybel execute -et Mock -p ladder -- "$WORK/fleet.src" 2>&1)
    if echo "$lout" | grep -q "Runtime error"; then
        agg_runtime=$((agg_runtime + 1))
        echo "batch $b runtime error:"
        echo "$lout" | grep "Runtime error" | head -2
    fi
    lr=$(echo "$lout" | grep "FLEET-RESULT" | sed -n 's/.*crashed=\([0-9]*\).*/\1/p')
    lo=$(echo "$lout" | grep "FLEET-VERDICTS" | awk -F'[= ]' '{print $3+$5+$7+$9}')
    ls=$(echo "$lout" | grep "FLEET-ACTIONS" | sed -n 's/.*spread=\([0-9]*\).*/\1/p')
    lrel=$(echo "$lout" | grep "FLEET-ACTIONS" | sed -n 's/.*relayed=\([0-9]*\).*/\1/p')
    agg_crashed=$((agg_crashed + ${lr:-1}))
    agg_owned=$((agg_owned + ${lo:-0}))
    agg_spread=$((agg_spread + ${ls:-0}))
    agg_relay=$((agg_relay + ${lrel:-0}))
done
echo "PHASE-2 TOTALS batches=$BATCHES owned=$agg_owned spread=$agg_spread relayed=$agg_relay crashed=$agg_crashed runtimeErrors=$agg_runtime"
if [ "$agg_crashed" -eq 0 ]; then
    echo "PASS ladder: zero crashes across $BATCHES full-ladder runs"
else
    echo "FAIL ladder: $agg_crashed crashed hosts"
    fail=1
fi
if [ "$agg_runtime" -eq 0 ]; then
    echo "PASS ladder: zero runtime errors"
else
    echo "FAIL ladder: $agg_runtime runtime errors"
    fail=1
fi
# every batch's seeded rich host must be OWNED and must relay + spread
if [ "$agg_owned" -ge "$BATCHES" ] && [ "$agg_spread" -ge "$BATCHES" ] && [ "$agg_relay" -ge "$BATCHES" ]; then
    echo "PASS ladder: every batch owned + relayed + spread (full chain)"
else
    echo "FAIL ladder: owned=$agg_owned spread=$agg_spread relayed=$agg_relay (need >= $BATCHES each)"
    fail=1
fi

exit $fail
