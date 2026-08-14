#!/usr/bin/env -S uv run --script
#
# /// script
# requires-python = ">=3.14"
# dependencies = [
#   "click",
# ]
# ///
"""email-tool: a small email CLI for AI agents."""

from contextlib import contextmanager, suppress
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from email.message import EmailMessage, Message
from email.parser import BytesParser
from email.policy import default as email_policy
from email.utils import formataddr, getaddresses, parsedate_to_datetime
import html
import imaplib
import json
import os
import re
import smtplib
import ssl
import sys
import tempfile
from pathlib import Path
from typing import Any, Final, Iterable, Iterator, Mapping, cast

import click

type JsonObject = dict[str, Any]

DEFAULT_TIMEOUT_SECONDS: Final = 30
DEFAULT_LIST_LIMIT: Final = 20
DEFAULT_ADDRESS_LIMIT: Final = 50
DEFAULT_IMAP_PORT: Final = 993
DEFAULT_SMTP_PORT: Final = 587
XDG_CONFIG_DIRECTORY: Final = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser()
SKILLS_NAMESPACE: Final = "steph-skills"
SKILL_NAME: Final = "use-email"
CONFIG_DIRECTORY: Final = XDG_CONFIG_DIRECTORY / SKILLS_NAMESPACE / SKILL_NAME
ACCOUNTS_PATH: Final = CONFIG_DIRECTORY / "accounts.json"
SECRETS_DIRECTORY: Final = CONFIG_DIRECTORY / "secrets"
EMAIL_ADDRESS_PATTERN: Final = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
HTML_BLOCK_PATTERN: Final = re.compile(
    r"</?(address|article|blockquote|br|div|h[1-6]|hr|li|p|pre|section|tr)(?:\s[^>]*)?>",
    flags=re.IGNORECASE,
)
HTML_TAG_PATTERN: Final = re.compile(r"<[^>]+>")
WHITESPACE_PATTERN: Final = re.compile(r"[ \t]+")

PROVIDER_PRESETS: Final[dict[str, dict[str, Any]]] = {
    "gmail.com": {
        "imap_host": "imap.gmail.com",
        "imap_port": 993,
        "imap_ssl": True,
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_ssl": False,
        "smtp_starttls": True,
    },
    "googlemail.com": {
        "imap_host": "imap.gmail.com",
        "imap_port": 993,
        "imap_ssl": True,
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_ssl": False,
        "smtp_starttls": True,
    },
    "outlook.com": {
        "imap_host": "outlook.office365.com",
        "imap_port": 993,
        "imap_ssl": True,
        "smtp_host": "smtp.office365.com",
        "smtp_port": 587,
        "smtp_ssl": False,
        "smtp_starttls": True,
    },
    "hotmail.com": {
        "imap_host": "outlook.office365.com",
        "imap_port": 993,
        "imap_ssl": True,
        "smtp_host": "smtp.office365.com",
        "smtp_port": 587,
        "smtp_ssl": False,
        "smtp_starttls": True,
    },
    "live.com": {
        "imap_host": "outlook.office365.com",
        "imap_port": 993,
        "imap_ssl": True,
        "smtp_host": "smtp.office365.com",
        "smtp_port": 587,
        "smtp_ssl": False,
        "smtp_starttls": True,
    },
    "msn.com": {
        "imap_host": "outlook.office365.com",
        "imap_port": 993,
        "imap_ssl": True,
        "smtp_host": "smtp.office365.com",
        "smtp_port": 587,
        "smtp_ssl": False,
        "smtp_starttls": True,
    },
    "office365.com": {
        "imap_host": "outlook.office365.com",
        "imap_port": 993,
        "imap_ssl": True,
        "smtp_host": "smtp.office365.com",
        "smtp_port": 587,
        "smtp_ssl": False,
        "smtp_starttls": True,
    },
    "fastmail.com": {
        "imap_host": "imap.fastmail.com",
        "imap_port": 993,
        "imap_ssl": True,
        "smtp_host": "smtp.fastmail.com",
        "smtp_port": 587,
        "smtp_ssl": False,
        "smtp_starttls": True,
    },
    "yahoo.com": {
        "imap_host": "imap.mail.yahoo.com",
        "imap_port": 993,
        "imap_ssl": True,
        "smtp_host": "smtp.mail.yahoo.com",
        "smtp_port": 587,
        "smtp_ssl": False,
        "smtp_starttls": True,
    },
    "icloud.com": {
        "imap_host": "imap.mail.me.com",
        "imap_port": 993,
        "imap_ssl": True,
        "smtp_host": "smtp.mail.me.com",
        "smtp_port": 587,
        "smtp_ssl": False,
        "smtp_starttls": True,
    },
    "me.com": {
        "imap_host": "imap.mail.me.com",
        "imap_port": 993,
        "imap_ssl": True,
        "smtp_host": "smtp.mail.me.com",
        "smtp_port": 587,
        "smtp_ssl": False,
        "smtp_starttls": True,
    },
    "mac.com": {
        "imap_host": "imap.mail.me.com",
        "imap_port": 993,
        "imap_ssl": True,
        "smtp_host": "smtp.mail.me.com",
        "smtp_port": 587,
        "smtp_ssl": False,
        "smtp_starttls": True,
    },
}


class EmlickError(click.ClickException):
    """email-tool command error."""


@dataclass(frozen=True)
class Account:
    """Stored email account settings."""

    email: str
    username: str
    imap_host: str
    imap_port: int
    imap_ssl: bool
    smtp_host: str
    smtp_port: int
    smtp_ssl: bool
    smtp_starttls: bool


@dataclass
class AccountStore:
    """Persisted account configuration."""

    default: str | None
    accounts: dict[str, Account]


@dataclass(frozen=True)
class MessageSummary:
    """Compact IMAP message listing row."""

    uid: str
    folder: str
    date: str
    sender: str
    recipients: str
    subject: str
    unseen: bool
    flagged: bool


@dataclass(frozen=True)
class Attachment:
    """Email attachment metadata."""

    index: int
    filename: str
    content_type: str
    size: int
    payload: bytes


@dataclass
class EmlickContext:
    """email-tool command context."""

    account: str | None


def normalize_email_address(value: str) -> str:
    """Normalize an email address."""
    email_address = value.strip()
    if email_address.startswith("<") and email_address.endswith(">"):
        email_address = email_address[1:-1].strip()
    email_address = email_address.casefold()
    if not EMAIL_ADDRESS_PATTERN.fullmatch(email_address):
        raise EmlickError(f"invalid email address: {value!r}")
    return email_address


def parse_address_list(value: str | None) -> list[tuple[str, str]]:
    """Parse a header into display-name and address pairs."""
    if not value:
        return []
    return [(name.strip(), address.casefold()) for name, address in getaddresses([value]) if address]


def format_address_pair(name: str, address: str) -> str:
    """Format a display name and email address."""
    return f"{name} <{address}>" if name else address


def format_address_header(value: str | None) -> str:
    """Format an address header for display."""
    pairs = parse_address_list(value)
    if not pairs:
        return value.strip() if value else "(none)"
    return ", ".join(format_address_pair(name, address) for name, address in pairs)


def email_domain(email_address: str) -> str:
    """Return the domain part of an email address."""
    return email_address.rsplit("@", 1)[1]


def provider_preset(email_address: str) -> dict[str, Any]:
    """Return built-in IMAP/SMTP defaults for a known provider."""
    return dict(PROVIDER_PRESETS.get(email_domain(email_address), {}))


def ensure_skill_directory(path: Path) -> Path:
    """Create a skill data directory under the shared XDG namespace."""
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)
    if path.parent.name == SKILLS_NAMESPACE:
        path.parent.chmod(0o700)
    return path


def ensure_config_directory() -> Path:
    """Create the email-tool config directory."""
    return ensure_skill_directory(CONFIG_DIRECTORY)


def write_secret_text(path: Path, value: str, *, temporary_prefix: str) -> None:
    """Write secret text atomically."""
    ensure_config_directory()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    file_descriptor, temporary_path_name = tempfile.mkstemp(prefix=temporary_prefix, dir=path.parent, text=True)
    temporary_path = Path(temporary_path_name)
    try:
        os.fchmod(file_descriptor, 0o600)
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as temporary_file:
            temporary_file.write(value)
            if not value.endswith("\n"):
                temporary_file.write("\n")
        temporary_path.replace(path)
        path.chmod(0o600)
    except Exception:
        with suppress(OSError):
            temporary_path.unlink()
        raise


def write_json(path: Path, value: JsonObject, *, temporary_prefix: str) -> None:
    """Write JSON atomically."""
    write_secret_text(path, json.dumps(value, indent=2, sort_keys=True), temporary_prefix=temporary_prefix)


def secret_path_for_email(email_address: str) -> Path:
    """Get the password file path for an account."""
    safe_name = re.sub(r"[^a-z0-9._+-]+", "_", email_address)
    return SECRETS_DIRECTORY / safe_name


def empty_store() -> AccountStore:
    """Return an empty account store."""
    return AccountStore(default=None, accounts={})


def account_from_mapping(value: Mapping[str, Any]) -> Account:
    """Build an account from stored JSON."""
    try:
        return Account(
            email=normalize_email_address(str(value["email"])),
            username=str(value.get("username") or value["email"]),
            imap_host=str(value["imap_host"]),
            imap_port=int(value.get("imap_port") or DEFAULT_IMAP_PORT),
            imap_ssl=bool(value.get("imap_ssl", True)),
            smtp_host=str(value["smtp_host"]),
            smtp_port=int(value.get("smtp_port") or DEFAULT_SMTP_PORT),
            smtp_ssl=bool(value.get("smtp_ssl", False)),
            smtp_starttls=bool(value.get("smtp_starttls", True)),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise EmlickError(f"invalid account record: {error}") from error


def load_account_store() -> AccountStore:
    """Load configured email accounts."""
    try:
        raw = ACCOUNTS_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return empty_store()
    except OSError as error:
        raise EmlickError(f"failed to read account config {ACCOUNTS_PATH}: {error}") from error

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise EmlickError(f"invalid account config {ACCOUNTS_PATH}: {error}") from error
    if not isinstance(payload, dict):
        raise EmlickError(f"invalid account config {ACCOUNTS_PATH}: expected an object")

    accounts: dict[str, Account] = {}
    raw_accounts = payload.get("accounts", {})
    if raw_accounts and not isinstance(raw_accounts, dict):
        raise EmlickError(f"invalid account config {ACCOUNTS_PATH}: accounts must be an object")
    for key, value in (raw_accounts or {}).items():
        if not isinstance(value, dict):
            raise EmlickError(f"invalid account record for {key}")
        account = account_from_mapping(value)
        accounts[account.email] = account

    default = payload.get("default")
    default_email = normalize_email_address(str(default)) if default else None
    if default_email and default_email not in accounts:
        default_email = None
    return AccountStore(default=default_email, accounts=accounts)


def store_to_json(store: AccountStore) -> JsonObject:
    """Serialize an account store."""
    return {
        "default": store.default,
        "accounts": {email: asdict(account) for email, account in sorted(store.accounts.items())},
    }


def save_account_store(store: AccountStore) -> None:
    """Persist configured email accounts."""
    write_json(ACCOUNTS_PATH, store_to_json(store), temporary_prefix="accounts.")


def read_account_password(email_address: str) -> str:
    """Read a stored account password."""
    path = secret_path_for_email(email_address)
    try:
        password = path.read_text(encoding="utf-8").rstrip("\r\n")
    except FileNotFoundError as error:
        raise EmlickError(
            f"no password stored for {email_address}; run `email-tool.py set-account {email_address}`",
        ) from error
    except OSError as error:
        raise EmlickError(f"failed to read password for {email_address}: {error}") from error
    if not password:
        raise EmlickError(f"stored password for {email_address} is empty")
    return password


def write_account_password(email_address: str, password: str) -> None:
    """Store an account password."""
    if not password:
        raise EmlickError("password must not be empty")
    write_secret_text(secret_path_for_email(email_address), password, temporary_prefix="password.")


def delete_account_password(email_address: str) -> None:
    """Delete a stored account password."""
    path = secret_path_for_email(email_address)
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError as error:
        raise EmlickError(f"failed to remove password for {email_address}: {error}") from error


def list_known_accounts(store: AccountStore | None = None) -> list[Account]:
    """List configured email accounts."""
    return list((store or load_account_store()).accounts.values())


def resolve_account(command_context: EmlickContext, email_address: str | None = None) -> Account:
    """Resolve the account to use for a command."""
    store = load_account_store()
    selected = email_address or command_context.account or store.default
    if not selected:
        if not store.accounts:
            raise EmlickError("no email accounts configured; run `email-tool.py set-account ADDRESS`")
        known = ", ".join(sorted(store.accounts))
        raise EmlickError(
            f"account is required (use --account or `email-tool.py set-default`); known addresses: {known}",
        )
    selected = normalize_email_address(selected)
    if selected not in store.accounts:
        known = ", ".join(sorted(store.accounts)) or "(none)"
        raise EmlickError(f"unknown email address {selected}; known addresses: {known}")
    return store.accounts[selected]


def prompt_for_password(email_address: str) -> str:
    """Prompt for an account password when stdin is a terminal."""
    if not sys.stdin.isatty():
        raise EmlickError(
            f"password is required for {email_address}; pass --password or run interactively",
        )
    return click.prompt(f"Password for {email_address}", hide_input=True, err=True)


def apply_account_updates(
    existing: Account | None,
    email_address: str,
    *,
    username: str | None,
    imap_host: str | None,
    imap_port: int | None,
    imap_ssl: bool | None,
    smtp_host: str | None,
    smtp_port: int | None,
    smtp_ssl: bool | None,
    smtp_starttls: bool | None,
) -> Account:
    """Create or update an account from CLI options and provider defaults."""
    preset = provider_preset(email_address)
    base = existing or Account(
        email=email_address,
        username=email_address,
        imap_host=str(preset.get("imap_host") or ""),
        imap_port=int(preset.get("imap_port") or DEFAULT_IMAP_PORT),
        imap_ssl=bool(preset.get("imap_ssl", True)),
        smtp_host=str(preset.get("smtp_host") or ""),
        smtp_port=int(preset.get("smtp_port") or DEFAULT_SMTP_PORT),
        smtp_ssl=bool(preset.get("smtp_ssl", False)),
        smtp_starttls=bool(preset.get("smtp_starttls", True)),
    )
    updates: dict[str, Any] = {}
    if username is not None:
        updates["username"] = username
    if imap_host is not None:
        updates["imap_host"] = imap_host
    if imap_port is not None:
        updates["imap_port"] = imap_port
    if imap_ssl is not None:
        updates["imap_ssl"] = imap_ssl
    if smtp_host is not None:
        updates["smtp_host"] = smtp_host
    if smtp_port is not None:
        updates["smtp_port"] = smtp_port
    if smtp_ssl is not None:
        updates["smtp_ssl"] = smtp_ssl
    if smtp_starttls is not None:
        updates["smtp_starttls"] = smtp_starttls
    account = replace(base, **updates)
    if not account.imap_host or not account.smtp_host:
        raise EmlickError(
            f"no IMAP/SMTP defaults for {email_domain(email_address)}; pass --imap-host and --smtp-host",
        )
    return account


def store_or_update_account(
    email_address: str,
    *,
    username: str | None,
    password: str | None,
    imap_host: str | None,
    imap_port: int | None,
    imap_ssl: bool | None,
    smtp_host: str | None,
    smtp_port: int | None,
    smtp_ssl: bool | None,
    smtp_starttls: bool | None,
    set_default: bool,
) -> Account:
    """Store or update credentials for an email address."""
    store = load_account_store()
    existing = store.accounts.get(email_address)
    account = apply_account_updates(
        existing,
        email_address,
        username=username,
        imap_host=imap_host,
        imap_port=imap_port,
        imap_ssl=imap_ssl,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_ssl=smtp_ssl,
        smtp_starttls=smtp_starttls,
    )
    if password is None and existing is None:
        password = prompt_for_password(email_address)
    if password is not None:
        write_account_password(email_address, password)
    elif not secret_path_for_email(email_address).is_file():
        write_account_password(email_address, prompt_for_password(email_address))
    store.accounts[email_address] = account
    if set_default or store.default is None:
        store.default = email_address
    save_account_store(store)
    return account


def remove_account(email_address: str) -> None:
    """Remove a stored email account."""
    store = load_account_store()
    if email_address not in store.accounts:
        raise EmlickError(f"unknown email address {email_address}")
    del store.accounts[email_address]
    if store.default == email_address:
        store.default = next(iter(sorted(store.accounts)), None)
    save_account_store(store)
    delete_account_password(email_address)


def imap_error_message(error: BaseException) -> str:
    """Format an IMAP or SMTP exception."""
    if isinstance(error, imaplib.IMAP4.error):
        return str(error)
    return str(error)


def connect_imap(account: Account) -> imaplib.IMAP4:
    """Connect and log in to an IMAP server."""
    password = read_account_password(account.email)
    client: imaplib.IMAP4 | None = None
    try:
        if account.imap_ssl:
            client = imaplib.IMAP4_SSL(account.imap_host, account.imap_port, timeout=DEFAULT_TIMEOUT_SECONDS)
        else:
            client = imaplib.IMAP4(account.imap_host, account.imap_port, timeout=DEFAULT_TIMEOUT_SECONDS)
        client.login(account.username, password)
    except (OSError, imaplib.IMAP4.error, ssl.SSLError) as error:
        if client is not None:
            with suppress(Exception):
                client.logout()
        raise EmlickError(f"IMAP login failed for {account.email}: {imap_error_message(error)}") from error
    return client


@contextmanager
def imap_session(account: Account) -> Iterator[imaplib.IMAP4]:
    """Connect to IMAP and log out when finished."""
    client = connect_imap(account)
    try:
        yield client
    finally:
        with suppress(Exception):
            client.logout()


def decode_imap_string(value: bytes | str) -> str:
    """Decode an IMAP atom or quoted string."""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def parse_list_folders(lines: Iterable[bytes | str | None]) -> list[str]:
    """Parse IMAP LIST responses into folder names."""
    folders: list[str] = []
    pattern = re.compile(r'\((?P<attrs>[^)]*)\)\s+(?P<delimiter>"[^"]*"|NIL)\s+(?P<name>".*"|[^ ]+)$')
    for line in lines:
        if not line:
            continue
        text = decode_imap_string(line).strip()
        match = pattern.search(text)
        if not match:
            continue
        name = match.group("name")
        if name.startswith('"') and name.endswith('"'):
            name = name[1:-1]
        folders.append(name)
    return folders


def expect_ok(status: str, payload: Any, action: str) -> None:
    """Raise when an IMAP command does not return OK."""
    if status == "OK":
        return
    detail = ""
    if payload:
        first = payload[0]
        detail = f": {decode_imap_string(first)}" if first else ""
    raise EmlickError(f"IMAP {action} failed ({status}){detail}")


def select_folder(client: imaplib.IMAP4, folder: str, *, readonly: bool = True) -> None:
    """Select an IMAP folder."""
    status, payload = client.select(folder, readonly=readonly)
    expect_ok(status, payload, f"SELECT {folder}")


def search_uids(client: imaplib.IMAP4, criteria: str) -> list[str]:
    """Search the selected folder and return UIDs newest-first."""
    status, payload = client.uid("search", None, criteria)
    expect_ok(status, payload, f"SEARCH {criteria}")
    if not payload or not payload[0]:
        return []
    uids = decode_imap_string(payload[0]).split()
    return list(reversed(uids))


def fetch_raw_message(client: imaplib.IMAP4, uid: str, spec: str) -> bytes:
    """Fetch raw IMAP payload for one UID."""
    status, payload = client.uid("fetch", uid, spec)
    expect_ok(status, payload, f"FETCH {uid}")
    for item in payload:
        if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], (bytes, bytearray)):
            return bytes(item[1])
    raise EmlickError(f"IMAP FETCH {uid} returned no message data")


def fetch_message(client: imaplib.IMAP4, uid: str, *, peek: bool = True) -> EmailMessage:
    """Fetch and parse one email message."""
    spec = "(BODY.PEEK[])" if peek else "(RFC822)"
    raw = fetch_raw_message(client, uid, spec)
    message = BytesParser(policy=email_policy).parsebytes(raw)
    return cast("EmailMessage", message)


def fetch_headers(client: imaplib.IMAP4, uid: str) -> tuple[EmailMessage, str]:
    """Fetch message headers and IMAP flags."""
    status, payload = client.uid("fetch", uid, "(FLAGS BODY.PEEK[HEADER])")
    expect_ok(status, payload, f"FETCH {uid} HEADER")
    raw = b""
    flags = ""
    for item in payload:
        if isinstance(item, tuple) and len(item) >= 2:
            meta = decode_imap_string(item[0])
            if match := re.search(r"FLAGS \(([^)]*)\)", meta):
                flags = match.group(1)
            if isinstance(item[1], (bytes, bytearray)):
                raw = bytes(item[1])
        elif isinstance(item, (bytes, bytearray)):
            meta = decode_imap_string(item)
            if match := re.search(r"FLAGS \(([^)]*)\)", meta):
                flags = match.group(1)
    if not raw:
        raise EmlickError(f"IMAP FETCH {uid} returned no headers")
    message = BytesParser(policy=email_policy).parsebytes(raw)
    return cast("EmailMessage", message), flags


def ordinal_day(value: int) -> str:
    """Format a day with an ordinal suffix."""
    if 11 <= value % 100 <= 13:
        suffix = "th"
    else:
        match value % 10:
            case 1:
                suffix = "st"
            case 2:
                suffix = "nd"
            case 3:
                suffix = "rd"
            case _:
                suffix = "th"
    return f"{value}{suffix}"


def format_message_date(value: str | None) -> str:
    """Format an email Date header in local time."""
    if not value:
        return "unknown-time"
    try:
        parsed = parsedate_to_datetime(value)
    except Exception:
        return value
    date_time = parsed if parsed.tzinfo is None else parsed.astimezone()
    hour = date_time.strftime("%I").lstrip("0") or "0"
    return f"{date_time:%a %b} {ordinal_day(date_time.day)} {hour}:{date_time:%M%p}"


def html_to_text(value: str) -> str:
    """Convert a simple HTML body to readable text."""
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", value)
    text = HTML_BLOCK_PATTERN.sub("\n", text)
    text = HTML_TAG_PATTERN.sub("", text)
    text = html.unescape(text)
    lines = [WHITESPACE_PATTERN.sub(" ", line).strip() for line in text.splitlines()]
    collapsed: list[str] = []
    previous_blank = False
    for line in lines:
        if not line:
            if not previous_blank and collapsed:
                collapsed.append("")
            previous_blank = True
            continue
        collapsed.append(line)
        previous_blank = False
    return "\n".join(collapsed).strip()


def part_charset(part: Message) -> str:
    """Get a MIME part charset."""
    return str(part.get_content_charset() or "utf-8")


def decode_part_text(part: Message) -> str:
    """Decode a text MIME part."""
    payload = part.get_payload(decode=True)
    if payload is None:
        content = part.get_content()
        return content if isinstance(content, str) else ""
    charset = part_charset(part)
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def extract_body(message: EmailMessage) -> tuple[str, str]:
    """Extract a preferred text body and its content type."""
    body = message.get_body(preferencelist=("plain", "html"))
    if body is None:
        return "", "text/plain"
    content_type = body.get_content_type()
    text = decode_part_text(body)
    if content_type == "text/html":
        return html_to_text(text), content_type
    return text.strip(), content_type


def iter_attachments(message: EmailMessage) -> list[Attachment]:
    """Collect attachment parts from a message."""
    attachments: list[Attachment] = []
    index = 0
    for part in message.walk():
        if part.is_multipart():
            continue
        disposition = str(part.get_content_disposition() or "")
        filename = part.get_filename()
        if disposition != "attachment" and not filename:
            continue
        index += 1
        payload = part.get_payload(decode=True) or b""
        attachments.append(
            Attachment(
                index=index,
                filename=filename or f"attachment-{index}",
                content_type=part.get_content_type(),
                size=len(payload),
                payload=bytes(payload),
            ),
        )
    return attachments


def format_file_size(size: int) -> str:
    """Format an attachment size."""
    units = ("B", "KB", "MB", "GB")
    display_size = float(size)
    unit = units[0]
    for unit in units:
        if display_size < 1024 or unit == units[-1]:
            break
        display_size /= 1024
    if unit == "B":
        return f"{size} {unit}"
    return f"{display_size:.1f} {unit}"


def flags_are_unseen(flags: str) -> bool:
    """Return whether IMAP flags indicate an unseen message."""
    tokens = {token.casefold() for token in flags.split()}
    return "\\seen" not in tokens


def flags_are_flagged(flags: str) -> bool:
    """Return whether IMAP flags include the flagged flag."""
    tokens = {token.casefold() for token in flags.split()}
    return "\\flagged" in tokens


def summarize_message(uid: str, folder: str, message: EmailMessage, flags: str) -> MessageSummary:
    """Build a listing row from headers and flags."""
    return MessageSummary(
        uid=uid,
        folder=folder,
        date=format_message_date(message.get("date")),
        sender=format_address_header(message.get("from")),
        recipients=format_address_header(message.get("to")),
        subject=(message.get("subject") or "(no subject)").strip(),
        unseen=flags_are_unseen(flags),
        flagged=flags_are_flagged(flags),
    )


def format_message_summary(summary: MessageSummary) -> str:
    """Format a message listing row as Markdown."""
    labels = []
    if summary.unseen:
        labels.append("unseen")
    if summary.flagged:
        labels.append("flagged")
    label_text = f" ({', '.join(labels)})" if labels else ""
    return (
        f"- `{summary.uid}`{label_text} | {summary.date} | {summary.sender}\n"
        f"  **{summary.subject}**\n"
        f"  To: {summary.recipients}"
    )


def format_account(account: Account, *, is_default: bool) -> str:
    """Format a stored account as Markdown."""
    marker = " (default)" if is_default else ""
    return (
        f"- {account.email}{marker}\n"
        f"  IMAP: {account.imap_host}:{account.imap_port} ssl={account.imap_ssl}\n"
        f"  SMTP: {account.smtp_host}:{account.smtp_port} "
        f"ssl={account.smtp_ssl} starttls={account.smtp_starttls}\n"
        f"  Username: {account.username}"
    )


def output_lines(lines: list[str]) -> None:
    """Print Markdown lines."""
    click.echo("\n".join(lines))


def list_folders(account: Account) -> list[str]:
    """List IMAP folders for an account."""
    with imap_session(account) as client:
        status, payload = client.list()
        expect_ok(status, payload, "LIST")
        return parse_list_folders(payload)


def list_messages(
    account: Account,
    *,
    folder: str,
    limit: int,
    unseen_only: bool,
    criteria: str | None,
) -> list[MessageSummary]:
    """List recent messages in a folder."""
    search = criteria.strip() if criteria else ("UNSEEN" if unseen_only else "ALL")
    if unseen_only and criteria and "UNSEEN" not in criteria.upper().split():
        search = f"(UNSEEN {search})"
    with imap_session(account) as client:
        select_folder(client, folder)
        uids = search_uids(client, search)[:limit]
        summaries: list[MessageSummary] = []
        for uid in uids:
            message, flags = fetch_headers(client, uid)
            summaries.append(summarize_message(uid, folder, message, flags))
    return summaries


def read_message(account: Account, uid: str, *, folder: str, mark_seen: bool) -> tuple[EmailMessage, list[Attachment]]:
    """Read one message and its attachments."""
    with imap_session(account) as client:
        select_folder(client, folder, readonly=not mark_seen)
        message = fetch_message(client, uid, peek=not mark_seen)
    return message, iter_attachments(message)


def normalize_message_uid(value: str) -> str:
    """Validate an IMAP UID."""
    uid = value.strip()
    if not uid or not uid.isdigit():
        raise EmlickError(f"invalid IMAP UID: {value!r}")
    return uid


def delete_messages(account: Account, uids: list[str], *, folder: str) -> list[MessageSummary]:
    """Delete messages by IMAP UID."""
    unique_uids = list(dict.fromkeys(normalize_message_uid(uid) for uid in uids))
    if not unique_uids:
        raise EmlickError("at least one IMAP UID is required")
    with imap_session(account) as client:
        select_folder(client, folder, readonly=False)
        summaries: list[MessageSummary] = []
        for uid in unique_uids:
            message, flags = fetch_headers(client, uid)
            summaries.append(summarize_message(uid, folder, message, flags))
            status, payload = client.uid("store", uid, "+FLAGS", r"(\Deleted)")
            expect_ok(status, payload, f"STORE {uid} +FLAGS \\Deleted")
        status, payload = client.expunge()
        expect_ok(status, payload, "EXPUNGE")
    return summaries


def collect_addresses_from_message(message: EmailMessage) -> list[tuple[str, str]]:
    """Collect unique addresses from common headers."""
    seen: set[str] = set()
    addresses: list[tuple[str, str]] = []
    for header in ("from", "to", "cc", "reply-to"):
        for name, address in parse_address_list(message.get(header)):
            if address in seen:
                continue
            seen.add(address)
            addresses.append((name, address))
    return addresses


def list_known_addresses(
    account: Account,
    *,
    folder: str,
    limit: int,
    message_scan: int,
) -> list[tuple[str, str]]:
    """List addresses seen in recent mail plus the configured account."""
    known: list[tuple[str, str]] = [("", account.email)]
    seen = {account.email}
    with imap_session(account) as client:
        select_folder(client, folder)
        for uid in search_uids(client, "ALL")[:message_scan]:
            message, _flags = fetch_headers(client, uid)
            for name, address in collect_addresses_from_message(message):
                if address in seen:
                    continue
                seen.add(address)
                known.append((name, address))
                if len(known) >= limit:
                    return known
    return known


def save_attachment(account: Account, uid: str, *, folder: str, index: int, output: Path) -> Attachment:
    """Save one attachment from a message."""
    _message, attachments = read_message(account, uid, folder=folder, mark_seen=False)
    if not attachments:
        raise EmlickError(f"message {uid} has no attachments")
    for attachment in attachments:
        if attachment.index == index:
            output.write_bytes(attachment.payload)
            return attachment
    raise EmlickError(f"message {uid} has no attachment {index}")


def get_message_text(text: str | None, *, require_text: bool) -> str | None:
    """Read message text from an argument or standard input."""
    if text is not None:
        return text
    if sys.stdin.isatty():
        if require_text:
            raise EmlickError("message text is required unless provided on stdin")
        return None
    standard_input_text = sys.stdin.read().rstrip("\n")
    if not standard_input_text:
        if require_text:
            raise EmlickError("message text from stdin is empty")
        return None
    return standard_input_text


def build_outgoing_message(
    account: Account,
    *,
    to_addresses: list[str],
    cc_addresses: list[str],
    bcc_addresses: list[str],
    subject: str,
    body: str,
    html_body: bool,
    attachments: tuple[Path, ...],
) -> EmailMessage:
    """Build an outgoing MIME message."""
    message = EmailMessage()
    message["From"] = formataddr(("", account.email))
    message["To"] = ", ".join(to_addresses)
    if cc_addresses:
        message["Cc"] = ", ".join(cc_addresses)
    message["Subject"] = subject
    message["Date"] = datetime.now().astimezone().strftime("%a, %d %b %Y %H:%M:%S %z")
    if html_body:
        message.add_alternative(body, subtype="html")
    else:
        message.set_content(body)
    for path in attachments:
        data = path.read_bytes()
        message.add_attachment(
            data,
            maintype="application",
            subtype="octet-stream",
            filename=path.name,
        )
    return message


def send_message(
    account: Account,
    *,
    to_addresses: list[str],
    cc_addresses: list[str],
    bcc_addresses: list[str],
    subject: str,
    body: str,
    html_body: bool,
    attachments: tuple[Path, ...],
) -> list[str]:
    """Send an email through SMTP."""
    recipients = [*to_addresses, *cc_addresses, *bcc_addresses]
    if not recipients:
        raise EmlickError("at least one recipient is required")
    message = build_outgoing_message(
        account,
        to_addresses=to_addresses,
        cc_addresses=cc_addresses,
        bcc_addresses=bcc_addresses,
        subject=subject,
        body=body,
        html_body=html_body,
        attachments=attachments,
    )
    password = read_account_password(account.email)
    context = ssl.create_default_context()
    try:
        if account.smtp_ssl:
            client: smtplib.SMTP = smtplib.SMTP_SSL(
                account.smtp_host,
                account.smtp_port,
                timeout=DEFAULT_TIMEOUT_SECONDS,
                context=context,
            )
        else:
            client = smtplib.SMTP(account.smtp_host, account.smtp_port, timeout=DEFAULT_TIMEOUT_SECONDS)
        with client:
            client.ehlo()
            if account.smtp_starttls and not account.smtp_ssl:
                client.starttls(context=context)
                client.ehlo()
            client.login(account.username, password)
            client.send_message(message, from_addr=account.email, to_addrs=recipients)
    except (OSError, smtplib.SMTPException, ssl.SSLError) as error:
        raise EmlickError(f"SMTP send failed for {account.email}: {error}") from error
    return recipients


def test_account(account: Account) -> tuple[bool, bool]:
    """Verify IMAP and SMTP credentials."""
    with imap_session(account) as client:
        status, _payload = client.noop()
        expect_ok(status, _payload, "NOOP")
    password = read_account_password(account.email)
    context = ssl.create_default_context()
    try:
        if account.smtp_ssl:
            client_smtp: smtplib.SMTP = smtplib.SMTP_SSL(
                account.smtp_host,
                account.smtp_port,
                timeout=DEFAULT_TIMEOUT_SECONDS,
                context=context,
            )
        else:
            client_smtp = smtplib.SMTP(account.smtp_host, account.smtp_port, timeout=DEFAULT_TIMEOUT_SECONDS)
        with client_smtp:
            client_smtp.ehlo()
            if account.smtp_starttls and not account.smtp_ssl:
                client_smtp.starttls(context=context)
                client_smtp.ehlo()
            client_smtp.login(account.username, password)
    except (OSError, smtplib.SMTPException, ssl.SSLError) as error:
        raise EmlickError(f"SMTP login failed for {account.email}: {error}") from error
    return True, True


def format_full_message(uid: str, folder: str, message: EmailMessage, attachments: list[Attachment]) -> str:
    """Format a full email for display."""
    body, content_type = extract_body(message)
    lines = [
        f"# Message `{uid}` in {folder}",
        "",
        f"- **From:** {format_address_header(message.get('from'))}",
        f"- **To:** {format_address_header(message.get('to'))}",
    ]
    if message.get("cc"):
        lines.append(f"- **Cc:** {format_address_header(message.get('cc'))}")
    lines.extend(
        [
            f"- **Subject:** {(message.get('subject') or '(no subject)').strip()}",
            f"- **Date:** {format_message_date(message.get('date'))}",
            f"- **Message-ID:** {message.get('message-id') or '(none)'}",
        ],
    )
    if attachments:
        lines.append("- **Attachments:**")
        lines.extend(
            f"  - `{attachment.index}` {attachment.filename} "
            f"({attachment.content_type}, {format_file_size(attachment.size)})"
            for attachment in attachments
        )
    lines.extend(["", "## Body", ""])
    if body:
        if content_type == "text/html":
            lines.append("_Converted from HTML._")
            lines.append("")
        lines.append(body)
    else:
        lines.append("_No text body._")
    return "\n".join(lines)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--account",
    "-a",
    help="Email address to use. Overrides the default from `email-tool.py set-default`.",
)
@click.pass_context
def cli(click_context: click.Context, account: str | None) -> None:
    """Small email CLI for AI models."""
    click_context.obj = EmlickContext(account=account)


@cli.command("list-accounts")
def command_list_accounts() -> None:
    """List known email addresses and their server settings."""
    store = load_account_store()
    accounts = list_known_accounts(store)
    if not accounts:
        click.echo("_No email accounts configured._")
        return
    output_lines(
        [
            f"Found {len(accounts)} email address{'es' if len(accounts) != 1 else ''}:",
            "",
            *[format_account(account, is_default=account.email == store.default) for account in accounts],
        ],
    )


@cli.command("list-addresses")
@click.option("--folder", "-f", default="INBOX", show_default=True, help="Folder to scan for addresses.")
@click.option(
    "--limit",
    default=DEFAULT_ADDRESS_LIMIT,
    show_default=True,
    type=click.IntRange(1),
    help="Max addresses.",
)
@click.option(
    "--scan",
    default=100,
    show_default=True,
    type=click.IntRange(1, 1000),
    help="Recent messages to scan.",
)
@click.pass_obj
def command_list_addresses(command_context: EmlickContext, folder: str, limit: int, scan: int) -> None:
    """List known email addresses from configured accounts and recent mail."""
    account = resolve_account(command_context)
    addresses = list_known_addresses(account, folder=folder, limit=limit, message_scan=scan)
    output_lines(
        [
            f"Found {len(addresses)} email addresses via {account.email}:",
            "",
            *[f"- {format_address_pair(name, address)}" for name, address in addresses],
        ],
    )


@cli.command("set-account")
@click.argument("email_address")
@click.option("--username", help="IMAP/SMTP username. Defaults to the email address.")
@click.option("--password", help="IMAP/SMTP password or app password. Prompted if omitted.")
@click.option("--imap-host", help="IMAP hostname.")
@click.option("--imap-port", type=click.IntRange(1, 65535), help="IMAP port.")
@click.option("--imap-ssl/--no-imap-ssl", default=None, help="Use IMAP SSL. Default: enabled.")
@click.option("--smtp-host", help="SMTP hostname.")
@click.option("--smtp-port", type=click.IntRange(1, 65535), help="SMTP port.")
@click.option("--smtp-ssl/--no-smtp-ssl", default=None, help="Use SMTP SSL. Default: disabled.")
@click.option("--smtp-starttls/--no-smtp-starttls", default=None, help="Use SMTP STARTTLS. Default: enabled.")
@click.option("--set-default", is_flag=True, help="Make this the default account.")
def command_set_account(
    email_address: str,
    username: str | None,
    password: str | None,
    imap_host: str | None,
    imap_port: int | None,
    imap_ssl: bool | None,
    smtp_host: str | None,
    smtp_port: int | None,
    smtp_ssl: bool | None,
    smtp_starttls: bool | None,
    set_default: bool,
) -> None:
    """Store or update credentials for an email address, then test login."""
    normalized = normalize_email_address(email_address)
    account = store_or_update_account(
        normalized,
        username=username,
        password=password,
        imap_host=imap_host,
        imap_port=imap_port,
        imap_ssl=imap_ssl,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_ssl=smtp_ssl,
        smtp_starttls=smtp_starttls,
        set_default=set_default,
    )
    store = load_account_store()
    output_lines(
        [
            f"Stored credentials for {account.email}.",
            f"Config: `{ACCOUNTS_PATH}`",
            *([f"Default account: {store.default}"] if store.default else []),
        ],
    )
    try:
        test_account(account)
    except EmlickError as error:
        raise EmlickError(f"Stored credentials for {account.email}, but login failed: {error}") from error
    click.echo(f"IMAP and SMTP login succeeded for {account.email}.")


@cli.command("set-default")
@click.argument("email_address")
def command_set_default(email_address: str) -> None:
    """Set the default email address."""
    store = load_account_store()
    normalized = normalize_email_address(email_address)
    if normalized not in store.accounts:
        raise EmlickError(f"unknown email address {normalized}; run `email-tool.py set-account` first")
    store.default = normalized
    save_account_store(store)
    click.echo(f"Default account set to {normalized}.")


@cli.command("remove-account")
@click.argument("email_address")
def command_remove_account(email_address: str) -> None:
    """Remove a stored email address and its password."""
    normalized = normalize_email_address(email_address)
    remove_account(normalized)
    click.echo(f"Removed {normalized}.")


@cli.command("test")
@click.pass_obj
def command_test(command_context: EmlickContext) -> None:
    """Test IMAP and SMTP login for an account."""
    account = resolve_account(command_context)
    test_account(account)
    click.echo(f"IMAP and SMTP login succeeded for {account.email}.")


@cli.command("folders")
@click.pass_obj
def command_folders(command_context: EmlickContext) -> None:
    """List IMAP folders."""
    account = resolve_account(command_context)
    folders = list_folders(account)
    if not folders:
        click.echo("_No folders found._")
        return
    output_lines([f"Found {len(folders)} folders for {account.email}:", "", *[f"- {folder}" for folder in folders]])


@cli.command("list")
@click.option("--folder", "-f", default="INBOX", show_default=True, help="IMAP folder.")
@click.option("--limit", default=DEFAULT_LIST_LIMIT, show_default=True, type=click.IntRange(1), help="Max messages.")
@click.option("--unseen", is_flag=True, help="Only list unseen messages.")
@click.option("--search", "criteria", help="IMAP search criteria, for example `FROM alice@example.com`.")
@click.pass_obj
def command_list(
    command_context: EmlickContext,
    folder: str,
    limit: int,
    unseen: bool,
    criteria: str | None,
) -> None:
    """List recent email in a folder."""
    account = resolve_account(command_context)
    summaries = list_messages(account, folder=folder, limit=limit, unseen_only=unseen, criteria=criteria)
    if not summaries:
        click.echo(f"_No messages found in {folder} for {account.email}._")
        return
    output_lines(
        [
            f"Found {len(summaries)} messages in {folder} for {account.email}:",
            "",
            *[format_message_summary(summary) for summary in summaries],
        ],
    )


@cli.command("read")
@click.argument("uid")
@click.option("--folder", "-f", default="INBOX", show_default=True, help="IMAP folder.")
@click.option("--mark-seen", is_flag=True, help="Mark the message as seen on the server.")
@click.pass_obj
def command_read(command_context: EmlickContext, uid: str, folder: str, mark_seen: bool) -> None:
    """Read one email by IMAP UID."""
    account = resolve_account(command_context)
    message, attachments = read_message(account, uid, folder=folder, mark_seen=mark_seen)
    click.echo(format_full_message(uid, folder, message, attachments))


@cli.command("delete")
@click.argument("uids", nargs=-1, required=True)
@click.option("--folder", "-f", default="INBOX", show_default=True, help="IMAP folder.")
@click.pass_obj
def command_delete(command_context: EmlickContext, uids: tuple[str, ...], folder: str) -> None:
    """Delete one or more emails by IMAP UID."""
    account = resolve_account(command_context)
    summaries = delete_messages(account, list(uids), folder=folder)
    output_lines(
        [
            f"Deleted {len(summaries)} message{'s' if len(summaries) != 1 else ''} from {folder} for {account.email}:",
            "",
            *[format_message_summary(summary) for summary in summaries],
        ],
    )


@cli.command("save-attachment")
@click.argument("uid")
@click.argument("index", type=click.IntRange(1))
@click.option("--folder", "-f", default="INBOX", show_default=True, help="IMAP folder.")
@click.option(
    "--output",
    "-o",
    required=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="Destination file path.",
)
@click.pass_obj
def command_save_attachment(
    command_context: EmlickContext,
    uid: str,
    index: int,
    folder: str,
    output: Path,
) -> None:
    """Save an attachment from a message."""
    account = resolve_account(command_context)
    attachment = save_attachment(account, uid, folder=folder, index=index, output=output)
    click.echo(f"Saved attachment {attachment.index} ({attachment.filename}) to {output}.")


@cli.command("send")
@click.argument("to_addresses", nargs=-1, required=True)
@click.option("--subject", "-s", required=True, help="Email subject.")
@click.option("--body", "body_text", help="Email body. Reads stdin when omitted.")
@click.option("--html", "html_body", is_flag=True, help="Treat the body as HTML.")
@click.option("--cc", "cc_addresses", multiple=True, help="Cc recipient. May be used more than once.")
@click.option("--bcc", "bcc_addresses", multiple=True, help="Bcc recipient. May be used more than once.")
@click.option(
    "--file",
    "file_paths",
    multiple=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="File path to attach. May be used more than once.",
)
@click.pass_obj
def command_send(
    command_context: EmlickContext,
    to_addresses: tuple[str, ...],
    subject: str,
    body_text: str | None,
    html_body: bool,
    cc_addresses: tuple[str, ...],
    bcc_addresses: tuple[str, ...],
    file_paths: tuple[Path, ...],
) -> None:
    """Send an email."""
    account = resolve_account(command_context)
    body = get_message_text(body_text, require_text=True)
    if body is None:
        raise EmlickError("message text is required")
    recipients = send_message(
        account,
        to_addresses=[normalize_email_address(address) for address in to_addresses],
        cc_addresses=[normalize_email_address(address) for address in cc_addresses],
        bcc_addresses=[normalize_email_address(address) for address in bcc_addresses],
        subject=subject,
        body=body,
        html_body=html_body,
        attachments=file_paths,
    )
    click.echo(f"Sent mail from {account.email} to {', '.join(recipients)}.")


if __name__ == "__main__":
    cli()
