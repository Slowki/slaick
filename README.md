# slaick

`slaick` is a small Slack CLI intended for AI-agent use. It runs as a [uv script](https://docs.astral.sh/uv/guides/scripts/).

Made by AI for AI.

## Authentication and storage

`slaick` reads the Slack desktop app's local cookie and uses that for authentication.

Set your default workspace:

```bash
slaick set-workspace myworkspace.slack.com
# or just the subdomain:
slaick set-workspace myworkspace
```

The config is stored in `~/.config/slaick/` and cached data is under `~/.cache/slaick/<workspace>/`.

## Commands

```bash
# Set default workspace
slaick set-workspace myworkspace.slack.com

# Authentication information
slaick user

# Authenticated user details
slaick user --me

# User details by user ID
slaick user --user U123456

# List users
slaick list-users

# List channels you belong to
slaick list-channels

# List all public/private channels
slaick list-channels --all

# Include IMs/MPIMs too
slaick list-channels --types public_channel,private_channel,im,mpim --all

# Search messages
slaick search 'from:@alice budget after:2026-01-01'

# Send a message to a channel
slaick send lobsters-r-us 'hello from slaick'
printf 'hello from stdin' | slaick send lobsters-r-us

# Upload files to a channel
slaick send lobsters-r-us --file report.txt
slaick send lobsters-r-us 'see attached' --file report.txt --file chart.png
printf 'generated summary' | slaick send lobsters-r-us --file summary.md

# Send a direct message to yourself
slaick dm me 'hello from slaick'
slaick send @me 'hello from slaick'

# Send a direct message by username or user ID
slaick dm alice 'hello from slaick'
slaick dm U123456 'hello from slaick'
printf 'hello from stdin' | slaick dm alice
slaick dm alice --file report.txt

# Follow new messages without history
slaick tail -f general

# Follow after printing recent messages
slaick tail -n 20 -f general

# Print recent direct messages
slaick tail @alice

# Forget cached token
slaick logout

# Rebuild workspace cache
slaick clear-cache
```
