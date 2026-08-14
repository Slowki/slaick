---
name: use-email
description: Interact with email. Use when you need to read, list, search, send, or delete email, or when you need to store or update IMAP/SMTP credentials for known addresses.
disable-model-invocation: true
---

# email-client

Use `scripts/email-tool.py` from this skill.

```bash
scripts/email-tool.py --help
```

## Accounts and Authentication

Store or update credentials before the first mail operation:

```bash
scripts/email-tool.py set-account you@example.com
scripts/email-tool.py set-account you@gmail.com --password 'app-password'
scripts/email-tool.py set-account you@custom.example --imap-host imap.example.com --smtp-host smtp.example.com
```

Gmail, Outlook, Fastmail, Yahoo, and iCloud hosts are filled in automatically.
Other domains need `--imap-host` and `--smtp-host`. Many providers require an
app password rather than the normal account password. `set-account` stores the
credentials, then tests IMAP and SMTP login immediately.

List configured addresses and change the default account:

```bash
scripts/email-tool.py list-accounts
scripts/email-tool.py set-default you@example.com
```

Use `--account` or `-a` to override the default for one command:

```bash
scripts/email-tool.py --account you@example.com list
```

The CLI stores account settings in `~/.config/steph-skills/use-email/accounts.json` and
passwords in `~/.config/steph-skills/use-email/secrets`. Update an existing address with the
same `set-account` command; omitted server options keep their previous values.

Remove a stored address:

```bash
scripts/email-tool.py remove-account you@example.com
```

Verify IMAP and SMTP login:

```bash
scripts/email-tool.py test
```

## Discover Addresses

List configured accounts:

```bash
scripts/email-tool.py list-accounts
```

List addresses seen in recent mail, including the authenticated account:

```bash
scripts/email-tool.py list-addresses
scripts/email-tool.py list-addresses --folder INBOX --limit 20 --scan 50
```

## Read Email

List IMAP folders:

```bash
scripts/email-tool.py folders
```

List recent messages. Each row includes the IMAP UID needed by `read`:

```bash
scripts/email-tool.py list
scripts/email-tool.py list --folder INBOX --limit 10
scripts/email-tool.py list --unseen
scripts/email-tool.py list --search 'FROM alice@example.com'
```

Read one message by UID. Reading does not mark the message seen unless
`--mark-seen` is passed:

```bash
scripts/email-tool.py read 12345
scripts/email-tool.py read 12345 --folder INBOX --mark-seen
```

Save an attachment shown in `read` output:

```bash
scripts/email-tool.py save-attachment 12345 1 --output invoice.pdf
```

Delete one or more messages by IMAP UID. Treat deletes as live side effects and
only run this after the user has clearly asked to delete those messages:

```bash
scripts/email-tool.py delete 12345
scripts/email-tool.py delete 12345 12346 --folder INBOX
```

## Send Email

Send a message after the recipients, subject, and body are clear:

```bash
scripts/email-tool.py send alice@example.com --subject 'hello' --body 'hello from email-tool'
printf 'hello from stdin' | scripts/email-tool.py send alice@example.com --subject 'hello'
scripts/email-tool.py send alice@example.com bob@example.com --subject 'notes' --cc carol@example.com
scripts/email-tool.py send alice@example.com --subject 'report' --body 'see attached' --file report.txt
```

When `send` omits `--body`, pipe the message through standard input. This is
useful for generated multi-line messages.

Treat email sends as live side effects. Only send mail when the user has asked
for that action and clearly approved the exact recipients, subject, and body.

## Debugging

If a command fails with `account is required` or `no email accounts configured`,
ask the user for the address and store credentials:

```bash
scripts/email-tool.py set-account you@example.com
scripts/email-tool.py test
```

If login fails, confirm the username, app password, and IMAP/SMTP hosts:

```bash
scripts/email-tool.py set-account you@example.com --username you@example.com --imap-host imap.example.com --smtp-host smtp.example.com
scripts/email-tool.py test
```

Use a one-command account override when testing an address without changing the
saved default:

```bash
scripts/email-tool.py --account you@example.com test
```

## Practical Workflow

1. Confirm the account with `list-accounts` or add one with `set-account`.
2. Discover people with `list-addresses` and recent mail with `list`.
3. Read a specific message with `read` before asking repeated questions.
4. Send mail with `send` only after the recipients, subject, and body are clear.
