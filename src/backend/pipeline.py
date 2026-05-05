from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse, urldefrag

import chromadb
import ipaddress
import requests
import trafilatura
from bs4 import BeautifulSoup
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction


DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; demo-rag-bot/1.0)"
}


@dataclass(frozen=True)
class Page:
    url: str
    status: int
    content_type: str
    html: str


def normalize_start_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        raise ValueError("URL is required.")
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http/https URLs are supported.")
    if not parsed.netloc:
        raise ValueError("Invalid URL.")
    return parsed.geturl()


def _host_is_private_or_local(host: str) -> bool:
    host = (host or "").strip().lower()
    if not host:
        return True
    if host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        return True
    if host.endswith(".local"):
        return True

    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        pass

    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return True

    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return True
        except ValueError:
            continue

    return False


def validate_crawl_target(url: str) -> str:
    start_url = normalize_start_url(url)
    host = urlparse(start_url).hostname or ""
    if _host_is_private_or_local(host):
        raise ValueError("Refusing to crawl local/private network hosts.")
    return start_url


def is_same_site(url: str, allowed_netloc: str) -> bool:
    try:
        return urlparse(url).netloc == allowed_netloc
    except Exception:
        return False


def normalize_url(base: str, href: str) -> str | None:
    if not href:
        return None
    href = href.strip()
    if href.startswith(("mailto:", "tel:", "#")):
        return None
    full = urljoin(base, href)
    full, _frag = urldefrag(full)
    return full


def should_skip_url(url: str) -> bool:
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        return True

    path = (p.path or "").lower()
    if any(
        path.endswith(ext)
        for ext in (
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".webp",
            ".svg",
            ".pdf",
            ".zip",
            ".mp4",
            ".mov",
            ".avi",
            ".css",
            ".js",
        )
    ):
        return True

    # avoid known app/auth subdomains for the original demo site
    if p.netloc == "app.twodots.net":
        return True

    return False


def fetch(session: requests.Session, url: str, timeout: int = 20) -> Page | None:
    r = session.get(url, headers=DEFAULT_HEADERS, timeout=timeout, allow_redirects=True)
    ct = r.headers.get("content-type", "")
    if "text/html" not in ct:
        return None
    return Page(url=r.url, status=r.status_code, content_type=ct, html=r.text)


def extract_links(base_url: str, html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        u = normalize_url(base_url, a["href"])
        if u:
            links.append(u)
    return links


def crawl_site(
    *,
    start_url: str,
    out_path: Path,
    max_pages: int = 80,
    delay_s: float = 0.2,
) -> int:
    parsed = urlparse(start_url)
    allowed_netloc = parsed.netloc

    seen: set[str] = set()
    queue: list[str] = [start_url]

    session = requests.Session()

    written = 0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        while queue and written < max_pages:
            url = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)

            if should_skip_url(url):
                continue
            if not is_same_site(url, allowed_netloc):
                continue

            try:
                page = fetch(session, url)
            except Exception:
                continue

            if not page or page.status >= 400:
                continue

            f.write(
                json.dumps(
                    {
                        "url": page.url,
                        "status": page.status,
                        "content_type": page.content_type,
                        "html": page.html,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            written += 1

            for link in extract_links(page.url, page.html):
                if (
                    link not in seen
                    and not should_skip_url(link)
                    and is_same_site(link, allowed_netloc)
                ):
                    queue.append(link)

            time.sleep(delay_s)

    return written


def get_title(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    t = soup.title.string.strip() if soup.title and soup.title.string else ""
    return t


def stable_id(url: str, text: str) -> str:
    h = hashlib.sha256((url + "\n" + text).encode("utf-8")).hexdigest()[:16]
    return h


def split_text(text: str, max_chars: int = 2400) -> list[str]:
    paras = [p.strip() for p in text.split("\n") if p.strip()]
    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for p in paras:
        if cur_len + len(p) + 1 > max_chars and cur:
            chunks.append("\n".join(cur))
            cur = []
            cur_len = 0
        cur.append(p)
        cur_len += len(p) + 1
    if cur:
        chunks.append("\n".join(cur))
    return chunks


def iter_pages(raw_path: Path) -> Iterable[dict]:
    with raw_path.open("r", encoding="utf-8") as f:
        for line in f:
            yield json.loads(line)


def html_to_main_text(html: str) -> str | None:
    extracted = trafilatura.extract(html, include_comments=False, include_tables=True)
    if not extracted:
        return None
    cleaned = "\n".join([ln.strip() for ln in extracted.splitlines() if ln.strip()])
    return cleaned if len(cleaned) > 200 else None


def build_chunks(*, raw_pages_path: Path, out_chunks_path: Path) -> int:
    written = 0
    seen: set[str] = set()
    out_chunks_path.parent.mkdir(parents=True, exist_ok=True)

    with out_chunks_path.open("w", encoding="utf-8") as out:
        for page in iter_pages(raw_pages_path):
            url = page["url"]
            html = page["html"]

            text = html_to_main_text(html)
            if not text:
                continue

            title = get_title(html)

            for part in split_text(text):
                cid = stable_id(url, part)
                if cid in seen:
                    continue
                seen.add(cid)
                out.write(
                    json.dumps(
                        {
                            "chunk_id": cid,
                            "url": url,
                            "title": title,
                            "text": part,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                written += 1

    return written


def build_index(
    *,
    chunks_path: Path,
    persist_dir: Path,
    collection_name: str,
    source_url: str,
) -> None:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY in environment.")

    persist_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(persist_dir))

    embed_fn = OpenAIEmbeddingFunction(
        api_key=api_key,
        model_name=os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large"),
    )

    col = client.get_or_create_collection(
        name=collection_name,
        embedding_function=embed_fn,
        metadata={"source": source_url},
    )

    ids: list[str] = []
    docs: list[str] = []
    metas: list[dict] = []

    with chunks_path.open("r", encoding="utf-8") as f:
        for line in f:
            c = json.loads(line)
            ids.append(c["chunk_id"])
            docs.append(c["text"])
            metas.append({"url": c["url"], "title": c.get("title", "")})

            if len(ids) >= 100:
                col.upsert(ids=ids, documents=docs, metadatas=metas)
                ids, docs, metas = [], [], []

    if ids:
        col.upsert(ids=ids, documents=docs, metadatas=metas)


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)


def index_site(
    *,
    url: str,
    work_dir: Path,
    max_pages: int = 80,
) -> dict:
    start_url = validate_crawl_target(url)
    reset_dir(work_dir)

    raw_pages_path = work_dir / "raw_pages.jsonl"
    chunks_path = work_dir / "chunks.jsonl"
    chroma_dir = work_dir / "chroma"
    collection_name = "site"

    pages = crawl_site(start_url=start_url, out_path=raw_pages_path, max_pages=max_pages)
    if pages <= 0:
        raise RuntimeError("No HTML pages were crawled.")

    chunks = build_chunks(raw_pages_path=raw_pages_path, out_chunks_path=chunks_path)
    if chunks <= 0:
        raise RuntimeError("No text chunks were extracted.")

    build_index(
        chunks_path=chunks_path,
        persist_dir=chroma_dir,
        collection_name=collection_name,
        source_url=start_url,
    )

    return {
        "start_url": start_url,
        "pages": pages,
        "chunks": chunks,
        "persist_dir": str(chroma_dir),
        "collection_name": collection_name,
    }

