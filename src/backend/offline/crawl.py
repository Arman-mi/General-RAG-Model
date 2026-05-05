from __future__ import annotations

import json
import time
import re
from dataclasses import dataclass
from collections import deque
from urllib.parse import urljoin, urlparse, urldefrag

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; twodots-rag-bot/1.0; +https://www.twodots.net/)"
}

SKIP_EXTENSIONS = re.compile(r".*\.(png|jpg|jpeg|gif|webp|svg|pdf|zip|mp4|mov|avi|css|js)$", re.IGNORECASE)

@dataclass
class Page:
    url: str
    status: int
    content_type: str
    html: str

#makes sure we only crawl pages from the same site, and avoid wandering off into the net.
def is_same_site(url: str, allowed_netloc: str) -> bool:
    try:
        return urlparse(url).netloc == allowed_netloc
    except Exception:
        return False
    
#normalizes raw links from html into absolute URLs    

def normalize_url(base: str, href: str) -> str | None:
    if not href:
        return None
    href = href.strip()
    if href.startswith("mailto:") or href.startswith("tel:") or href.startswith("#"):
        return None
    full = urljoin(base, href)
    full, _frag = urldefrag(full)
    return full

#checks if a URL should be skipped or not
def should_skip(url: str) -> bool:
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        return True
    if SKIP_EXTENSIONS.match(p.path):
        return True
    # skip app / auth subdomain
    if p.netloc == "app.twodots.net":
        return True
    return False


#in this function we download 1 page with a GET request that we send
def fetch(session: requests.Session, url: str, timeout: int = 20) -> Page | None:
    r = session.get(url, headers=DEFAULT_HEADERS, timeout=timeout, allow_redirects=True)
    ct = r.headers.get("content-type", "")
    if "text/html" not in ct:
        return None
    return Page(url=r.url, status=r.status_code, content_type=ct, html=r.text)

#this function extracts all links from the HTML content of a page
def extract_links(base_url: str, html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    links = []
    for a in soup.find_all("a", href=True):
        u = normalize_url(base_url, a["href"])
        if u:
            links.append(u)
    return links



#the main crawler

def crawl_site(
    start_url: str,
    out_path: str = "data/raw_pages.jsonl",
    max_pages: int = 5000,
    delay_s: float = 0.35,
) -> None:
    parsed = urlparse(start_url)
    allowed_netloc = parsed.netloc

    seen: set[str] = set()
    q: deque[str] = deque([start_url])

    session = requests.Session()

    written = 0
    with open(out_path, "w", encoding="utf-8") as f:
        pbar = tqdm(total=max_pages, desc="Crawling")
        while q and written < max_pages:
            url = q.popleft()
            if url in seen:
                continue
            seen.add(url)

            if should_skip(url):
                continue
            if not is_same_site(url, allowed_netloc):
                continue

            try:
                page = fetch(session, url)
            except Exception:
                continue

            if not page or page.status >= 400:
                continue

            # write page
            f.write(json.dumps({
                "url": page.url,
                "status": page.status,
                "content_type": page.content_type,
                "html": page.html,
            }, ensure_ascii=False) + "\n")
            written += 1
            pbar.update(1)

            # enqueue links
            for link in extract_links(page.url, page.html):
                if link not in seen and not should_skip(link) and is_same_site(link, allowed_netloc):
                    q.append(link)

            time.sleep(delay_s)

        pbar.close()

    print(f"Saved {written} pages to {out_path}")

if __name__ == "__main__":
    crawl_site("https://www.twodots.net/")