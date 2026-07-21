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
import getpass
import hashlib
import imaplib
import json
import os
import re
import sys
from datetime import datetime, timedelta
from email.header import decode_header
from email.message import Message
from html.parser import HTMLParser
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

DEFAULT_EXTENSIONS = [".pdf", ".docx", ".doc", ".txt", ".jpg", ".jpeg", ".png"]
HTTP_URL_RE = re.compile(r"https?://[^\s<>\"']+")


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value and value.startswith(("http://", "https://")):
                self.links.append(value)


def decode_mime(value: str | None) -> str:
    if not value:
        return ""
    chunks = []
    for part, enc in decode_header(value):
        if isinstance(part, bytes):
            try:
                chunks.append(part.decode(enc or "utf-8", errors="replace"))
            except LookupError:
                chunks.append(part.decode("utf-8", errors="replace"))
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
        writer.writerows({key: csv_safe(value) for key, value in row.items()} for row in rows)


def append_message_manifest(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    exists = path.exists()
    fieldnames = [
        "mailbox",
        "sender",
        "subject",
        "date",
        "message_id",
        "uid",
        "matching_attachment_count",
        "new_download_count",
        "web_link_count",
        "web_links",
    ]
    with path.open("a", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerows({key: csv_safe(value) for key, value in row.items()} for row in rows)


def load_manifest_hashes(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return {
            str(row.get("sha1") or "").strip()
            for row in csv.DictReader(handle)
            if str(row.get("sha1") or "").strip()
        }


def csv_safe(value: Any) -> Any:
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


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


def fetch_message_headers(mail: imaplib.IMAP4_SSL, uid: bytes) -> Message | None:
    status, data = mail.uid(
        "fetch",
        uid,
        "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)])",
    )
    if status != "OK" or not data or not data[0]:
        return None
    return email.message_from_bytes(data[0][1])


def decode_text_part(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if not isinstance(payload, bytes):
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def extract_http_links(msg: Message, limit: int = 30) -> list[str]:
    links: list[str] = []
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        if (part.get_content_disposition() or "").lower() == "attachment":
            continue
        content_type = part.get_content_type().lower()
        if content_type not in {"text/plain", "text/html"}:
            continue
        text = decode_text_part(part)
        candidates = HTTP_URL_RE.findall(text)
        if content_type == "text/html":
            parser = LinkParser()
            try:
                parser.feed(text)
            except Exception:
                pass
            candidates.extend(parser.links)
        for link in candidates:
            clean = link.rstrip(".,;:!?)]}\"")
            if clean and clean not in links:
                links.append(clean)
                if len(links) >= limit:
                    return links
    return links


def download(args: argparse.Namespace) -> int:
    save_dir = Path(args.save_dir).expanduser().resolve()
    save_dir.mkdir(parents=True, exist_ok=True)
    state_path = save_dir / ".email_download_state.json"
    manifest_path = save_dir / "_source_manifest.csv"
    message_manifest_path = save_dir / "_email_message_manifest.csv"
    state = load_state(state_path)
    seen_keys = set(state.get("seen_keys", []))
    seen_hashes = set(state.get("seen_hashes", [])) | load_manifest_hashes(manifest_path)
    new_count = 0
    matched_message_count = 0
    messages_with_attachments = 0
    link_only_message_count = 0

    mail = connect(args)
    try:
        select_mailbox(mail, args.mailbox)
        uids = search_uids(mail, args.days_back)
        if args.limit:
            uids = uids[-args.limit :]
        print(f"Mailbox {args.mailbox}: {len(uids)} messages in the last {args.days_back} days")
        for uid in uids:
            uid_str = uid.decode("ascii", errors="replace")
            header_msg = fetch_message_headers(mail, uid)
            if header_msg is None or not should_keep_message(header_msg, args):
                continue
            msg = fetch_message(mail, uid)
            if msg is None:
                continue
            matched_message_count += 1
            message_id = msg_text_header(msg, "Message-ID") or uid_str
            sender = msg_text_header(msg, "From")
            subject = msg_text_header(msg, "Subject")
            date = msg_text_header(msg, "Date")
            matching_attachment_count = 0
            message_new_count = 0
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
                matching_attachment_count += 1
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
                message_new_count += 1
                row = {
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
                }
                append_manifest(manifest_path, [row])
                save_state(state_path, {
                    "seen_keys": sorted(seen_keys),
                    "seen_hashes": sorted(seen_hashes),
                })
                print(f"downloaded: {target.name}")
            links = extract_http_links(msg)
            if matching_attachment_count:
                messages_with_attachments += 1
            elif links:
                link_only_message_count += 1
            append_message_manifest(message_manifest_path, [{
                "mailbox": args.mailbox,
                "sender": sender,
                "subject": subject,
                "date": date,
                "message_id": message_id,
                "uid": uid_str,
                "matching_attachment_count": matching_attachment_count,
                "new_download_count": message_new_count,
                "web_link_count": len(links),
                "web_links": "\n".join(links),
            }])
    finally:
        try:
            mail.logout()
        except Exception:
            pass

    state["seen_keys"] = sorted(seen_keys)
    state["seen_hashes"] = sorted(seen_hashes)
    save_state(state_path, state)
    print(f"new attachments: {new_count}")
    print(f"manifest: {manifest_path}")
    print(f"matched messages: {matched_message_count}")
    print(f"messages with matching attachments: {messages_with_attachments}")
    print(f"link-only messages: {link_only_message_count}")
    print(f"message manifest: {message_manifest_path}")
    if matched_message_count and not messages_with_attachments and link_only_message_count:
        print(
            "提示：命中邮件没有可下载附件，主要是网页链接通知。不要用浏览器逐封处理大量邮件；"
            "优先使用招聘平台批量导出/API，或基于本地 _email_message_manifest.csv 设计批处理。",
            file=sys.stderr,
        )
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
    parser.add_argument("--password", default=os.getenv("IMAP_PASSWORD", ""), help=argparse.SUPPRESS)
    parser.add_argument("--save-dir", required=True)
    parser.add_argument("--mailbox", default="INBOX")
    parser.add_argument("--days-back", type=int, default=30)
    parser.add_argument("--limit", type=int, default=0, help="Only inspect the newest N messages after the date filter, before subject/sender filters")
    parser.add_argument("--from-keyword", default="", help="Require sender header to contain this text")
    parser.add_argument("--subject-keyword", action="append", default=[], help="Require subject to contain this text; repeatable")
    parser.add_argument("--filename-keyword", action="append", default=[], help="Require attachment filename to contain this text; repeatable")
    parser.add_argument("--extensions", type=parse_extensions, default=DEFAULT_EXTENSIONS, help="Comma-separated extensions; default pdf,docx,doc,txt,jpg,jpeg,png")
    args = parser.parse_args()
    if not args.password:
        args.password = getpass.getpass("请输入邮箱客户端专用密码/授权码（输入不会显示）：")
    if not args.password:
        raise SystemExit("未输入邮箱客户端专用密码/授权码")
    try:
        download(args)
    except imaplib.IMAP4.error as e:
        print(f"IMAP error: {e}", file=sys.stderr)
        print("For Tencent Enterprise Email, use --provider tencent-exmail and a client/app password if required.", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
