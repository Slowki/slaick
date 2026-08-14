---
name: use-slack
description: Interact with Slack. Use when you need to search, send, read, or listen for Slack messages. This can also be used to discover Slack users and channels.
disable-model-invocation: true
---

# slack-client

Use `scripts/slack-tool.py` from this skill.

```bash
scripts/slack-tool.py --help
```

## Workspace and Authentication

Set the default workspace before the first Slack operation:

```bash
scripts/slack-tool.py set-workspace myworkspace
scripts/slack-tool.py set-workspace myworkspace.slack.com
```

Use `--workspace` or `-w` to override the configured workspace for one command:

```bash
scripts/slack-tool.py --workspace myworkspace user --me
```

The CLI reads the local Slack desktop app cookie, caches a user token under
`~/.cache/steph-skills/use-slack`, and stores the workspace under `~/.config/steph-skills/use-slack`. If auth
looks stale, run:

```bash
scripts/slack-tool.py logout
scripts/slack-tool.py clear-cache
```

## Discover Users

Identify the authenticated user:

```bash
scripts/slack-tool.py user --me
```

List other users:

```bash
scripts/slack-tool.py list-users
```

User references accept `me`, a Slack user ID, a username, or an `@username`
where supported.

## Discover Channels and Conversations

List joined public and private channels:

```bash
scripts/slack-tool.py list-channels
```

## Search Messages

Use Slack search syntax directly:

```bash
scripts/slack-tool.py search 'from:@alice budget after:2026-01-01'
scripts/slack-tool.py search 'in:general "release notes"' --count 10
scripts/slack-tool.py search 'from:me has:link' --sort timestamp --sort-dir desc
```

Results are formatted as Markdown with the conversation context, timestamp,
sender, permalink, and message text.

## Send Messages

Send a message to a channel:

```bash
scripts/slack-tool.py send random 'hello from slack-tool'
printf 'hello from stdin' | scripts/slack-tool.py send random
```

Upload files to a channel:

```bash
scripts/slack-tool.py send random --file report.txt
scripts/slack-tool.py send random 'see attached' --file report.txt --file chart.png
printf 'generated summary' | scripts/slack-tool.py send random --file summary.md
```

Send a direct message:

```bash
scripts/slack-tool.py send @alice 'hello from slack-tool'
scripts/slack-tool.py send @me 'test message'
printf 'hello from stdin' | scripts/slack-tool.py dm alice
scripts/slack-tool.py dm alice --file report.txt
```

When `send` or `dm` omits the message argument, pipe the message body through standard input.
This is useful for generated multi-line messages. When `--file` is provided,
the message body is optional and becomes the upload comment.

Reply in a thread when the thread timestamp is known:

```bash
scripts/slack-tool.py send general 'reply text' --thread 1716153058.123456
scripts/slack-tool.py dm alice 'reply text' --thread 1716153058.123456
```

`--thread-ts` is also accepted as an alias for `--thread`.

Add an emoji reaction to a message when the message timestamp is known:

```bash
scripts/slack-tool.py react general 1716153058.123456 white_check_mark
scripts/slack-tool.py react @alice 1716153058.123456 :eyes:
```

Edit a message when the message timestamp is known:

```bash
scripts/slack-tool.py edit general 1716153058.123456 'corrected text'
printf 'corrected text from stdin' | scripts/slack-tool.py edit @alice 1716153058.123456
scripts/slack-tool.py edit 'https://workspace.slack.com/archives/C123/p1716153058123456' 'corrected text'
```

Treat Slack writes as live side effects. Only send messages, edit messages, or add reactions when the user has
asked for that action and clearly approved the exact content.

## Tail and Wait for Responses

Print recent messages from a channel or direct message. Each line includes the message timestamp as `ts MESSAGE_TS`; threaded messages include `| thread` in the timestamp bracket:

```bash
scripts/slack-tool.py tail --lines 20 general
scripts/slack-tool.py tail @alice
```

Print a thread by the thread timestamp shown in tail output:

```bash
scripts/slack-tool.py tail @alice --thread 1780103312.121629
```

Watch a conversation for new messages:

```bash
scripts/slack-tool.py tail --follow @alice
scripts/slack-tool.py tail --follow --lines 20 general
scripts/slack-tool.py tail --follow @alice --thread 1780103312.121629
```

Tail output includes shared files as `[file F123...: filename]`. Download a shared file to stdout with:

```bash
scripts/slack-tool.py cat-file F1234567890 > filename
```

Use `tail --follow` when the user asks to wait for Slack replies. It defaults
to `--lines 0`, so it only prints new messages. Add `--lines <count>` only
when recent history is useful. Start the command in a long-running terminal
session, monitor output, and stop it after the expected response arrives or the
wait is no longer useful.

## Debugging

If a command fails with `workspace is required`, ask the user for the name of
their Slack workspace and set the default workspace:

```bash
scripts/slack-tool.py set-workspace myworkspace
scripts/slack-tool.py user --me
```

Use a one-command workspace override when testing a workspace without changing the saved default:

```bash
scripts/slack-tool.py --workspace myworkspace user --me
```

If authentication fails with `invalid_auth`, `token_revoked`, `not_authed`, or
`account_inactive`, refresh the cached token and workspace cache:

```bash
scripts/slack-tool.py logout
scripts/slack-tool.py clear-cache
```

If Slack cookie access fails, confirm the Slack desktop app is installed and logged in.

If user or channel names do not resolve, rebuild the workspace cache:

```bash
scripts/slack-tool.py clear-cache
```

## Practical Workflow

1. Discover people with `list-users` and conversations with `list-channels`.
2. Search existing context with `search` before asking repeated questions.
3. Send messages with `send` or `dm` only after the target and text are clear.
4. Use `tail --follow` to watch for replies, then summarize the response and continue the user task.
