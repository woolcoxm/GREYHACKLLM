# Skill: bank-heist — stealing money from accounts and wallets

Load for: missions about banks, money, wallets, or "steal from X".

## The two money systems

1. **Bank accounts** (the in-game bank site, `bank_account` service on the
   bank's machine): money moves through the bank's web interface. Scripted
   API access is LIMITED — your job is to gather what the player needs and
   do the scriptable parts.
2. **Crypto wallets** (files on victim machines + `wallet` API): fully
   scriptable.

## Recon → creds (the usual chain)

1. Find the target's bank: the victim's own machine shows bank usage
   (browser history files, saved mail). Banks are found by domain:
   `nslookup("bankdomain")` → IP. The `bank_account` service shows up in
   port scans of the bank machine.
2. Get the victim's bank password:
   - crack their system password (`crypto.decipher` on their /etc/passwd
     hash) — people reuse passwords; TRY it on the bank login.
   - or an overflow password-change exploit against the bank machine's
     services.
   - or social engineering (below).

## Social engineering / phishing (scriptable)

NPCs fall for convincing admin-style mail. You have a mail API:

```
mail = mail_login("youraddress@provider", "yourpass")  // MetaMail or error string
mail.send(victim@provider, "Subject", "message body")  // 1 on success
mail.fetch / mail.read(mailId) / mail.delete(mailId)
```

- Harvest targets and their addresses from a rooted machine:
  `/etc/passwd`, mail files, `crypto.smtp_user_list` when an SMTP service
  runs somewhere (needs crypto lib).
- IMPERSONATE authority: pretend to be bank admin / IT support; demand
  the credential or action ("reply with your password to keep your
  account", "your account will be closed").
- Personal info makes it convincing: victims' machines hold files with
  names, birthdays, addresses (home folders, notes, chat/mail history).
  Read them and use them.
- Attachment-based drops (malware the victim runs) are sent via the
  in-game MAIL UI, not the script API — tell the player to attach a
  compiled tool manually if a drop is needed.

## Bank account steps (semi-manual)

Once you have target account number + password: the actual transfer is
done in the in-game BROWSER (login at the bank site → transfer). Prepare
everything for the player: account number, password, the player's own
account number (ask_user if unknown), then instruct them precisely.
WARNING: bank transfers leave bank logs and can trigger bank traces —
prefer wallet theft when possible.

## Wallet theft (fully scriptable)

Victim machines may hold wallet files (usually in /home). A wallet is a
FILE:

1. On the victim: locate the wallet file (list /home, look for wallet-ish
   names), read its content, and copy it to the player's machine
   (write_file). The wallet's password is often the victim's reused
   password — try crack results.
2. On the player's machine, import/use it: the in-game wallet program
   uses the wallet FILE + password. With the wallet open the `wallet` API
   applies: `get_balance(coin)`, `transfer` (via the wallet UI/API),
   `reset_password(pass)` to lock the stolen wallet to the player.
3. Cash out: `sell_coin(coin, amount, price)` on a wallet the player
   controls, or move coins to the player's own wallet first.

## Opsec (mandatory)

Bank machines log aggressively; the bank runs its own trace system.
Load the opsec skill and clean the victim, the bank machine if touched,
and every hop. Never leave stolen wallet copies on victim machines.
