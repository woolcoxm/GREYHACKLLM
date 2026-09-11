# Skill: worm — epidemic bank-detail harvesting

Load for: missions like "steal bank details from everything", "spread
across the network", mass credential harvesting. The standard worm
(`~/worm.src`, daemon-managed like ~/exploit.src) does the whole cycle.

## Distributed execution (v17)

The player's machine must NOT do the epidemic's compute — every
processor death traced to exactly that. Now: when the exploit tool
holds a shell foothold, it DELEGATES the next generation — drops
worm+exploit sources on the victim, builds them there, and launches
`worm -child` ON the victim (depth-limited tree, default 3). The
victim's CPU attacks the next hosts, harvests, and writes loot to its
/tmp; when the synchronous launch returns, the parent pulls the loot
home and surfaces NEWTARGETs. CPU wear lands on the infected, where it
belongs. `-depth=` tunes the tree depth.

## The worm's cycle (per host)

The worm is the FRONTIER DRIVER — it never touches victims itself.
For each host it launches `~/exploit <ip> -u=... -w=... -g=<rootpass>
-E=<exfil> -depth=<n>`, and the exploit does everything IN-PROCESS while
its foothold object is alive:

1. **Entry**: full-fire across every open port (quiet `-q` mode only
   fires no-requirement exploits and starves the worm to zero — do not
   use it). The first shell/computer foothold wins.
2. **Harvest**: every readable `*bank*`/`*mail*` file in every
   `/home/*` — appended to the exfil file right through the foothold
   (default `~/Desktop/bankintel.txt`). Re-login is impossible on
   http-only hosts, so nothing waits for "later".
3. **Escalation**: the exploit drops + compiles itself on the victim
   and runs `exploit -L` THERE — local /lib attacks for root
   (password-change attempts with `-rp=`). A root foothold re-harvests
   every home.
4. **Delegation**: with depth > 0 it also drops + builds `worm` on the
   victim and launches `worm -child -depth-1` there — the infected
   machine attacks the NEXT generation. Loot bucket-brigades home: each
   parent pulls its child's exfil file up through the foothold after
   the synchronous launch returns.
5. **Spread**: the child (or a depth-0 scan) enumerates THAT network's
   public attack surface — results ride the report home as NEWTARGET
   lines. Plus fresh random public IPs every cycle — the frontier
   never runs dry.
6. **Stealth**: dropped artifacts deleted, victim `/var/system.log`
   wiped (best-effort — it is root-owned). State saved after EVERY
   host — any death resumes on rerun.

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
`-fanout=N` automates it: splits the frontier across N shard state
files and prints the N launch commands to paste into N terminals;
`-install-workers=N` additionally installs N compiled launchers into
/etc/init.d so every login auto-starts N parallel workers;
`-merge` unions the shards back into ~/worm.state.
Flags: `-g=` cap cycles (0=infinite), `-t=` hosts/cycle, `-r=` random
IPs/cycle, `-depth=` infection-tree depth, `-o=` exfil, `-u/-w` creds,
`-rp=` root password.

IMPORTANT for the harness: an infinite worm blocks the serve loop
forever. When launching via run_program, ALWAYS pass a bounded -g=
(e.g. -g=3) and re-invoke for more; reserve raw infinite runs for a
terminal the player opens directly (or -auto autorun at login).

## CPU WEAR — the hard lesson

The game DEGRADES hardware under sustained process load: a processor
was lost to an unbounded run. Per operator directive the worm is now
IMMORTAL (no runtime cap, no idle shutdown — only 5s pacing and the
ping gate restrain it): run it on hardware you can afford to lose,
never your home box. The AGENT must still launch it bounded
(run_program ~/worm <ip> -g=3) — an unbounded run blocks the serve
loop forever.

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
