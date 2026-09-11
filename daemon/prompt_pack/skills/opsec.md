# Skill: opsec — covering your tracks

Load for: ANY mission that touches a machine you don't own, and for cleanup
at the end of every such mission. Leaving evidence gets the player traced
and hacked back.

## How tracing works in this game (verified)

- Every machine keeps its log in **`/var/system.log`** (a special DB-backed
  file). Actions like shell logins, file removals and downloads append
  entries recording the **source IP, port, time, affected file, and bounce
  IP**.
- **Passive traces:** NPC admins later read their logs, follow the recorded
  IPs/bounce chain, and attack the origin. Clean logs = no passive trace.
- **Active traces:** some actions (shell/remove/download against protected
  machines) can start an immediate trace. Bounces (attacking through
  intermediates) buy time. Finish fast and clean.
- Actions you take on YOUR OWN machine only log locally — no risk.

## Log clearing (the core technique)

`/var/system.log` is rewritable with the normal file API:

```
f = victimComp.File("/var/system.log")
logTxt = f.get_content            // read what's there
// keep innocent lines, drop yours — or blank it:
f.set_content("")                 // verified: rewrites the machine's log
```

Rules:
- Clear the log on the TARGET last, after you have everything you need
  (clearing is itself a logged action if done clumsily — one final clean
  write covers it).
- Clear logs on every HOP machine too — the chain is what traces you.
- Read the log first; deleting only your lines looks less suspicious than
  an empty log, but an empty log is acceptable in-game.

## Attacking through hops (bounces)

Direct attacks put YOUR IP in the target's log. Instead:

1. Root a low-value INTERMEDIATE machine first (it becomes the hop).
2. From the hop, attack the real target. With a shell on the hop:
   `hopShell.launch("/path/tool", args)` runs a tool ON the hop, and
   `hopShell.host_computer` gives you file I/O there (upload tool → run →
   read its result file → download results).
3. The target's log then shows the HOP's IP, not yours.
4. After the mission: clean the target's log AND the hop's log, remove
   your tools from the hop.

## Cleanup checklist (run at mission end — always)

- [ ] Delete every file/binary you uploaded to victims and hops
      (source, binary, result files — e.g. anything in /home, /tmp).
- [ ] Remove accounts you created: `victimComp.delete_user(name)`.
      Restore any password you changed if you recorded the old one.
- [ ] Remove reverse shells: `metax.rshell_client` persists on the victim —
      delete the dropped binary/process (`show_procs`, `close_program`) and
      any startup entry when done with it.
- [ ] Restore modified system files (e.g. /etc/passwd) from the copy you
      saved BEFORE editing (always save one first).
- [ ] Clear `/var/system.log` on target and every hop.
- [ ] Remove evidence of the mission from YOUR notes in chat if the user
      wants deniability — notes.txt lives on the player's own machine only.

## Standing rules

- Save a copy of any system file BEFORE you modify it.
- Record every artifact you create on a victim in notes.txt (path + why)
  so the cleanup checklist is complete.
- Prefer reading over writing; prefer the fewest touched files.
