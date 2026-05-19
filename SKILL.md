---
name: slack-client
description: Interact with Slack. Use when you need to search, send, read, or listen for Slack messages. This can also be used to discover Slack users and channels.
---

# slack-client

Use `scripts/slaick` from this repository.

```bash
scripts/slaick --help
```

## Workspace and Authentication

Set the default workspace before the first Slack operation:

```bash
scripts/slaick set-workspace myworkspace
scripts/slaick set-workspace myworkspace.slack.com
```

Use `--workspace` or `-w` to override the configured workspace for one command:

```bash
scripts/slaick --workspace myworkspace user --me
```

The CLI reads the local Slack desktop app cookie, caches a user token under
`~/.cache/slaick`, and stores the workspace under `~/.config/slaick`. If auth
looks stale, run:

```bash
scripts/slaick logout
scripts/slaick clear-cache
```

## Discover Users

Identify the authenticated user:

```bash
scripts/slaick user --me
```

List other users:

```bash
scripts/slaick list-users
```

User references accept `me`, a Slack user ID, a username, or an `@username`
where supported.

## Discover Channels and Conversations

List joined public and private channels:

```bash
scripts/slaick list-channels
```

## Search Messages

Use Slack search syntax directly:

```bash
scripts/slaick search 'from:@alice budget after:2026-01-01'
scripts/slaick search 'in:general "release notes"' --count 10
scripts/slaick search 'from:me has:link' --sort timestamp --sort-dir desc
```

Results are formatted as Markdown with the conversation context, timestamp,
sender, permalink, and message text.

## Send Messages

Send a message to a channel:

```bash
scripts/slaick send random 'hello from slaick'
```

Send a direct message:

```bash
scripts/slaick send @alice 'hello from slaick'
scripts/slaick send @me 'test message'
```

Reply in a thread when the thread timestamp is known:

```bash
scripts/slaick send general 'reply text' --thread-ts 1716153058.123456
scripts/slaick dm alice 'reply text' --thread-ts 1716153058.123456
```

Treat Slack writes as live side effects. Only send messages when the user has asked for that action and clearly approved the exact content.

## Tail and Wait for Responses

Print recent messages from a channel or direct message:

```bash
scripts/slaick tail --lines 20 general
scripts/slaick tail @alice
```

Watch a conversation for new messages:

```bash
scripts/slaick tail --follow @alice
scripts/slaick tail --follow --lines 20 general
```

Use `tail --follow` when the user asks to wait for Slack replies. It defaults
to `--lines 0`, so it only prints new messages. Add `--lines <count>` only
when recent history is useful. Start the command in a long-running terminal
session, monitor output, and stop it after the expected response arrives or the
wait is no longer useful.

## Debugging

If a command fails with `workspace is required`, ask the user for the name of their slack workspace and set the default workspace:

```bash
scripts/slaick set-workspace myworkspace
scripts/slaick user --me
```

Use a one-command workspace override when testing a workspace without changing the saved default:

```bash
scripts/slaick --workspace myworkspace user --me
```

If authentication fails with `invalid_auth`, `token_revoked`, `not_authed`, or `account_inactive`, refresh the cached token and workspace cache:

```bash
scripts/slaick logout
scripts/slaick clear-cache
```

If Slack cookie access fails, confirm the Slack desktop app is installed and logged in.

If user or channel names do not resolve, rebuild the workspace cache:

```bash
scripts/slaick clear-cache
```

## Practical Workflow

1. Discover people with `list-users` and conversations with `list-channels`.
2. Search existing context with `search` before asking repeated questions.
3. Send messages with `send` or `dm` only after the target and text are clear.
4. Use `tail --follow` to watch for replies, then summarize the response and continue the user task.
