#!/usr/bin/env python3
"""
Download resume-like email attachments from IMAP mailboxes into a local resumes folder.

Designed as an upstream collector for resume_screening_pipeline.py.
Supports Tencent Enterprise Email via --provider tencent-exmail and generic IMAP via
--server/--port.
"""

from __future__ import annotations

import argparse
import csv
import email
import hashlib
import imaplib
import json
import os
import re
import sys
from datetime import datetime, timedelta
from email.header import decode_header
from email.message import Message
from pathlib import Path
from typing import Any


PROVIDERS = {
    "tencent-exmail": ("imap.exmail.qq.com", 993),
    "tencent-exmail-hw": ("hwimap.exmail.qq.com", 993),
    "qq": ("imap.qq.com", 993),
    "gmail": ("imap.gmail.com", 993),
    "outlook": ("outlook.office365.com", 993),
    "office365": ("outlook.office365.com", 993),
    "netease-163": ("imap.163.com", 993),
    "netease-126": ("imap.126.com", 993),
    "netease-enterprise": ("imap.qiye.163.com", 993),
    "netease-enterprise-hw": ("hwimap.qiye.163.com", 993),
    "aliyun": ("imap.qiye.aliyun.com", 993),
    "zoho": ("imap.zoho.com", 993),
}

DEFAULT_EXTENSIONS = [".pdf", ".docx", ".doc", ".jpg", ".jpeg", ".png"]


def decode_mime(value: str | None) -> str:
    if not value:
        return ""
    chunks = []
    for part, enc in decode_header(value):
        if isinstance(part, bytes):
            chunks.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            chunks.append(str(part))
    return "".join(chunks)


def sanitize_filename(name: str) -> str:
    name = decode_mime(name)
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", name)
    name = re.sub(r"\s+", " ", name).strip(" ._")
    return name or "attachment"


def sha1_bytes(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def load_state(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"seen_keys": [], "seen_hashes": []}


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def append_manifest(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    exists = path.exists()
    fieldnames = [
        "local_file",
        "source_type",
        "mailbox",
        "sender",
        "subject",
        "date",
        "message_id",
        "uid",
        "original_attachment",
        "sha1",
        "size_bytes",
    ]
    with path.open("a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerows(rows)


def unique_path(save_dir: Path, filename: str) -> Path:
    base = sanitize_filename(filename)
    stem = Path(base).stem or "attachment"
    suffix = Path(base).suffix
    candidate = save_dir / f"{stem}{suffix}"
    n = 2
    while candidate.exists():
        candidate = save_dir / f"{stem}_{n}{suffix}"
        n += 1
    return candidate


def msg_text_header(msg: Message, header: str) -> str:
    return decode_mime(msg.get(header))


def should_keep_message(msg: Message, args: argparse.Namespace) -> bool:
    sender = msg_text_header(msg, "From").lower()
    subject = msg_text_header(msg, "Subject").lower()
    if args.from_keyword and args.from_keyword.lower() not in sender:
        return False
    for keyword in args.subject_keyword:
        if keyword.lower() not in subject:
            return False
    return True


def should_keep_attachment(filename: str, args: argparse.Namespace) -> bool:
    lower = filename.lower()
    if Path(lower).suffix not in args.extensions:
        return False
    for keyword in args.filename_keyword:
        if keyword.lower() not in lower:
            return False
    return True


def connect(args: argparse.Namespace) -> imaplib.IMAP4_SSL:
    server = args.server
    port = args.port
    if args.provider:
        if args.provider not in PROVIDERS:
            known = ", ".join(sorted(PROVIDERS))
            raise SystemExit(f"Unknown provider {args.provider!r}. Known providers: {known}")
        server, port = PROVIDERS[args.provider]
    if not server:
        raise SystemExit("Provide --provider or --server")
    mail = imaplib.IMAP4_SSL(server, port)
    mail.login(args.username, args.password)
    return mail


def select_mailbox(mail: imaplib.IMAP4_SSL, mailbox: str) -> None:
    status, _ = mail.select(mailbox)
    if status != "OK":
        raise RuntimeError(f"Could not select mailbox {mailbox!r}")


def search_uids(mail: imaplib.IMAP4_SSL, days_back: int) -> list[bytes]:
    since = (datetime.now() - timedelta(days=days_back)).strftime("%d-%b-%Y")
    status, data = mail.uid("search", None, f"(SINCE {since})")
    if status != "OK" or not data:
        return []
    return data[0].split()


def fetch_message(mail: imaplib.IMAP4_SSL, uid: bytes) -> Message | None:
    status, data = mail.uid("fetch", uid, "(RFC822)")
    if status != "OK" or not data or not data[0]:
        return None
    return email.message_from_bytes(data[0][1])


def download(args: argparse.Namespace) -> int:
    save_dir = Path(args.save_dir).expanduser().resolve()
    save_dir.mkdir(parents=True, exist_ok=True)
    state_path = save_dir / ".email_download_state.json"
    manifest_path = save_dir / "_source_manifest.csv"
    state = load_state(state_path)
    seen_keys = set(state.get("seen_keys", []))
    seen_hashes = set(state.get("seen_hashes", []))
    rows: list[dict[str, Any]] = []
    new_count = 0

    mail = connect(args)
    try:
        select_mailbox(mail, args.mailbox)
        uids = search_uids(mail, args.days_back)
        if args.limit:
            uids = uids[-args.limit :]
        print(f"Mailbox {args.mailbox}: {len(uids)} messages in the last {args.days_back} days")
        for uid in uids:
            uid_str = uid.decode("ascii", errors="replace")
            msg = fetch_message(mail, uid)
            if msg is None or not should_keep_message(msg, args):
                continue
            message_id = msg_text_header(msg, "Message-ID") or uid_str
            sender = msg_text_header(msg, "From")
            subject = msg_text_header(msg, "Subject")
            date = msg_text_header(msg, "Date")
            for part in msg.walk():
                if part.get_content_maintype() == "multipart":
                    continue
                filename = part.get_filename()
                if not filename:
                    continue
                original_name = decode_mime(filename)
                safe_name = sanitize_filename(original_name)
                if not should_keep_attachment(safe_name, args):
                    continue
                payload = part.get_payload(decode=True) or b""
                if not payload:
                    continue
                digest = sha1_bytes(payload)
                dedupe_key = f"{message_id}|{safe_name}|{digest}"
                if dedupe_key in seen_keys or digest in seen_hashes:
                    continue
                target = unique_path(save_dir, safe_name)
                target.write_bytes(payload)
                seen_keys.add(dedupe_key)
                seen_hashes.add(digest)
                new_count += 1
                rows.append({
                    "local_file": target.name,
                    "source_type": "email",
                    "mailbox": args.mailbox,
                    "sender": sender,
                    "subject": subject,
                    "date": date,
                    "message_id": message_id,
                    "uid": uid_str,
                    "original_attachment": original_name,
                    "sha1": digest,
                    "size_bytes": len(payload),
                })
                print(f"downloaded: {target.name}")
    finally:
        try:
            mail.logout()
        except Exception:
            pass

    state["seen_keys"] = sorted(seen_keys)
    state["seen_hashes"] = sorted(seen_hashes)
    save_state(state_path, state)
    append_manifest(manifest_path, rows)
    print(f"new attachments: {new_count}")
    print(f"manifest: {manifest_path}")
    return new_count


def parse_extensions(raw: str) -> list[str]:
    values = []
    for item in raw.split(","):
        item = item.strip().lower()
        if not item:
            continue
        values.append(item if item.startswith(".") else f".{item}")
    return values or DEFAULT_EXTENSIONS


def main() -> None:
    parser = argparse.ArgumentParser(description="Download resume attachments from an IMAP mailbox.")
    parser.add_argument("--provider", choices=sorted(PROVIDERS), default="", help="Known IMAP provider preset")
    parser.add_argument("--server", default="", help="Custom IMAP server")
    parser.add_argument("--port", type=int, default=993)
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", default=os.getenv("IMAP_PASSWORD", ""), help="IMAP/client password; can also use IMAP_PASSWORD env var")
    parser.add_argument("--save-dir", required=True)
    parser.add_argument("--mailbox", default="INBOX")
    parser.add_argument("--days-back", type=int, default=30)
    parser.add_argument("--limit", type=int, default=0, help="Only inspect the newest N matching messages after date search")
    parser.add_argument("--from-keyword", default="", help="Require sender header to contain this text")
    parser.add_argument("--subject-keyword", action="append", default=[], help="Require subject to contain this text; repeatable")
    parser.add_argument("--filename-keyword", action="append", default=[], help="Require attachment filename to contain this text; repeatable")
    parser.add_argument("--extensions", type=parse_extensions, default=DEFAULT_EXTENSIONS, help="Comma-separated extensions; default pdf,docx,doc,jpg,jpeg,png")
    args = parser.parse_args()
    if not args.password:
        raise SystemExit("Missing --password or IMAP_PASSWORD")
    try:
        download(args)
    except imaplib.IMAP4.error as e:
        print(f"IMAP error: {e}", file=sys.stderr)
        print("For Tencent Enterprise Email, use --provider tencent-exmail and a client/app password if required.", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
