from __future__ import annotations

import argparse
import hashlib
import json
import sys
import os
import mimetypes
import re
import urllib.parse
import urllib.request
from collections import deque
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
from official_download import open_official


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.links.append(value)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalized_url(base: str, href: str) -> str | None:
    try:
        url = urllib.parse.urljoin(base, href)
        p = urllib.parse.urlsplit(url)
        if p.scheme not in {"http", "https"}:
            return None
        return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, p.query, ""))
    except Exception:
        return None


def extension_for(url: str, content_type: str | None) -> str:
    path_suffix = Path(urllib.parse.urlsplit(url).path).suffix.lower()
    if 0 < len(path_suffix) <= 10:
        return path_suffix
    if content_type:
        guess = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if guess:
            return guess
    return ".bin"


def fetch(url: str, timeout: int = 45) -> tuple[bytes, str | None, str]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "fire-ai-local-official-regulation-collector/0.1",
            "Accept": "*/*",
        },
    )
    with open_official(req, timeout=timeout) as response:
        return response.read(), response.headers.get("Content-Type"), response.geturl()


def collect(
    *,
    index_url: str,
    allowed_host: str,
    include_regex: str,
    crawl_regex: str,
    output_dir: Path,
    max_pages: int = 3000,
    max_depth: int = 4,
    signing_key_file: Path | None = None,
) -> dict:
    include = re.compile(include_regex)
    crawl = re.compile(crawl_regex)
    output_dir.mkdir(parents=True, exist_ok=True)
    if signing_key_file and (output_dir / "manifest.json").exists():raise ValueError("signed output directory must be new")
    files_dir = output_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=True)

    queue = deque([(index_url, 0)])
    seen: set[str] = set()
    captured: list[dict] = []
    failures: list[dict] = []
    truncated = False

    while queue:
        if len(seen) >= max_pages:
            truncated = True
            break
        url, depth = queue.popleft()
        if url in seen:
            continue
        p = urllib.parse.urlsplit(url)
        if p.hostname != allowed_host:
            continue
        seen.add(url)

        try:
            fetched=fetch(url)
            body,content_type=fetched[:2]
            effective_url=fetched[2] if len(fetched)>2 else url
        except Exception as exc:
            failures.append({"url": url, "error": type(exc).__name__})
            continue

        digest = sha256_bytes(body)
        capture = url == index_url or bool(include.search(url))
        if capture:
            ext = extension_for(url, content_type)
            filename = f"{digest}{ext}"
            path = files_dir / filename
            if not path.exists():
                path.write_bytes(body)
            captured.append(
                {
                    "url": url,
                    "effective_url": effective_url,
                    "sha256": digest,
                    "size_bytes": len(body),
                    "content_type": content_type,
                    "file": f"files/{filename}",
                    "depth": depth,
                }
            )

        is_html = bool(content_type and "html" in content_type.lower())
        if depth >= max_depth or not is_html:
            continue
        parser = LinkParser()
        try:
            parser.feed(body.decode("utf-8", errors="replace"))
        except Exception:
            continue
        for href in parser.links:
            child = normalized_url(url, href)
            if not child:
                continue
            cp = urllib.parse.urlsplit(child)
            if cp.hostname != allowed_host:
                continue
            if child not in seen and (crawl.search(child) or include.search(child)):
                queue.append((child, depth + 1))

    manifest = {
        "bundle_format": "fire-ai-local-regulation-snapshot-v1",
        "authority": "official-domain-restricted",
        "retrieval_policy": "https-exact-host-redirect-checked-v1",
        "index_url": index_url,
        "allowed_host": allowed_host,
        "include_regex": include_regex,
        "crawl_regex": crawl_regex,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "visited_count": len(seen),
        "captured_count": len(captured),
        "failure_count": len(failures),
        "truncated": truncated,
        "complete_candidate": not failures and not truncated,
        "documents": captured,
        "failures": failures,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if signing_key_file:
        from app.legal_update_bundle import sign_manifest
        sign_manifest(output_dir / 'manifest.json',signing_key_file)
    return manifest


def main() -> None:
    p = argparse.ArgumentParser(description="Collect an official local regulation corpus from an approved domain.")
    p.add_argument("--index-url", required=True)
    p.add_argument("--allowed-host", required=True)
    p.add_argument("--include-regex", required=True)
    p.add_argument("--crawl-regex", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--max-pages", type=int, default=3000)
    p.add_argument("--max-depth", type=int, default=4)
    p.add_argument('--signing-key-file',default=os.environ.get('FIRE_AI_COLLECTOR_SIGNING_KEY_FILE'))
    args = p.parse_args()

    result = collect(
        index_url=args.index_url,
        allowed_host=args.allowed_host,
        include_regex=args.include_regex,
        crawl_regex=args.crawl_regex,
        output_dir=Path(args.output_dir),
        max_pages=max(1, args.max_pages),
        max_depth=max(0, args.max_depth),
        signing_key_file=Path(args.signing_key_file) if args.signing_key_file else None,
    )
    print(json.dumps({
        "captured_count": result["captured_count"],
        "failure_count": result["failure_count"],
        "truncated": result["truncated"],
        "complete_candidate": result["complete_candidate"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
