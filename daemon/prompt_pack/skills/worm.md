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

## Driving the epidemic

```
compile_program ~/worm.src -> ~/worm        # once
~/worm <seed-ip> -auto                      # LAUNCH ONCE
```
The default run is INFINITE: infect -> harvest -> scan -> infect,
breadth-first, until killed — random public IPs keep the frontier
alive when networks are picked clean. `-auto` also installs the worm
into the PLAYER's /etc/init.d (autorun, verified in game source): the
epidemic auto-resumes at every game login. Kill with the terminal
close / process kill; state (`~/worm.state`) resumes on next launch.
Multiple terminals with different `-s=` state files = parallel
epidemics (GreyScript has no threads — instances are the parallelism).
Flags: `-g=` cap cycles (0=infinite), `-t=` hosts/cycle, `-r=` random
IPs/cycle, `-o=` exfil, `-u/-w` creds, `-rp=` root password.

IMPORTANT for the harness: an infinite worm blocks the serve loop
forever. When launching via run_program, ALWAYS pass a bounded -g=
(e.g. -g=3) and re-invoke for more; reserve raw infinite runs for a
terminal the player opens directly (or -auto autorun at login).

## CPU WEAR — the hard lesson

The game DEGRADES hardware under sustained process load: an infinite
worm variant ran for hours of game-time on the player's machine and the
processor DIED. Rules: never run unbounded loops on a machine that
matters; the worm self-caps (default: 10 min runtime, exits after 3
idle cycles, probes randoms only when starved, 5s pacing); drive the
epidemic with repeated bounded runs (`-g=`/`-max=`); heavy sustained
work belongs on a rented/throwaway machine, never home.

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
