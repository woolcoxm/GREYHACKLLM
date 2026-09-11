# Skill: recon — profiling targets before attacking

Load for: the start of any attack mission, and whenever you know nothing
about a target. Recon first, exploit second — every fact goes in notes.txt.

## Local network (where am I, who's around)

```
router = get_router
router.local_ip        // your LAN ip
router.public_ip       // your internet ip
for ip in router.devices_lan_ip          // every device on this network
    for port in router.device_ports(ip)
        if port.is_closed then continue
        info = router.port_info(port)    // "ssh 1.0.3" style
        // record: ip, port number, service, version
```

## A specific remote target (ip known)

```
get_shell.ping(ip)                        // 1 reachable / 0 not
r = get_router(ip)                        // its network's router
for port in r.used_ports                  // ports on that router
    if port.is_closed then continue
    r.port_info(port)
// or per-device if you know its LAN ip on that network:
r.device_ports(lanIp)
```

Service names to care about: `ssh` (login target), `ftp` (file moves),
`http` (sites + recon), `smtp` (mail + user lists), `bank_account`
(money), `rshell` (reverse shell listener), `sql`, `chat`.

## Deep fingerprint a service (versions → vulnerabilities)

```
metax = include_lib("/lib/metaxploit.so")
ns = metax.net_use(ip, port)     // null = nothing exploitable there
if ns != null then
    lib = ns.dump_lib
    lib.lib_name + " " + lib.version   // e.g. "ssh 1.0.3"
    areas = metax.scan(lib)            // memory areas with vulns
    details = metax.scan_address(lib, areas[0])  // parse "<b>name</b>"
```

Version info goes in notes.txt — requirements for exploits depend on
versions (of the target's libs AND your libs).

## Profile the people (for social engineering / password reuse)

On any machine you can read:
- `/etc/passwd` → usernames + password hashes (crackable via
  `crypto.decipher`).
- `/home/*` folders → personal files: names, birthdays, addresses, notes,
  chat logs, mail — the material for phishing and security questions.
- Browser/mail files → habits, bank domains, account numbers.

## Building the attack graph

Record in notes.txt as you learn:
- every machine: ip → open ports → service+version → vulns found
- every credential: user → password → where it works (try reuse!)
- every hop candidate: weak machine close to the target
Then load post-exploit.md and opsec.md, pick the path with the fewest
touches, and execute.
