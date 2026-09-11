# Skill: worm — epidemic bank-detail harvesting

Load for: missions like "steal bank details from everything", "spread
across the network", mass credential harvesting. The standard worm
(`~/worm.src`, daemon-managed like ~/exploit.src) does the whole cycle.

## The worm's cycle (per host)

1. **Entry**: launches `~/exploit <ip> -q -u=worm -w=...` — quiet
   (no-requirement exploits only), converting any foothold to a durable
   user on the spot.
2. **Escalation**: enters with the durable user, drops + compiles
   `exploit.src` ON the victim, and runs `exploit -L` there — local
   /lib attacks for root, including password-change attempts
   (`-rp=` root password). If root lands, harvest runs as root (every
   home + /etc/passwd hashes). If not, harvest as the user and move on.
3. **Harvest**: every readable `*bank*`/`*mail*` file in every
   `/home/*` — appended to the exfil file (default
   `~/Desktop/bankintel.txt`).
4. **Spread**: builds `worm` on the victim, runs `worm -scan` there to
   enumerate THAT network's public attack surface + LAN, reads the map
   back. Plus fresh random public IPs every generation — the frontier
   never runs dry.
5. **Stealth**: every dropped artifact deleted, victim `/var/system.log`
   wiped. State saved after EVERY host — any death resumes on rerun.

## Driving it (staged generations)

```
compile_program ~/worm.src -> ~/worm        # once
run_program ~/worm <seed-ip>                # generation 1
run_program ~/worm                          # next generations (state-driven)
```
Flags: `-g=` generations per run, `-t=` hosts per generation (≤10),
`-r=` random IPs per generation, `-o=` exfil path, `-u/-w` durable
creds, `-rp=` root password. One run = a few hosts (bounded so the
harness's synchronous launch doesn't stall); loop runs for an epidemic.
Check `~/worm.state` (frontier/owned/done) and the exfil file between
runs; report stolen credentials from the exfil file.

## Constraints (verified)

- Binary files (metaxploit.so) move between machines ONLY via
  `shell.scp`; `get_content` refuses binaries. Sources move as text +
  compile locally (`shell.build`).
- Victims without metaxploit (and where scp fails) are harvested but
  cannot escalate or scan — the worm moves on.
- `rnd()` is deterministic; the worm mixes `time()` for per-run address
  variety.
- Every host is one pass — machines that get cleaned by admins simply
  drop out; reruns re-seed from the frontier.
