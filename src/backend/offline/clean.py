from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from typing import Iterable

import trafilatura
from bs4 import BeautifulSoup
from tqdm import tqdm

@dataclass
class Chunk:
    url: str
    title: str
    text: str
    chunk_id: str


def get_title(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    t = soup.title.string.strip() if soup.title and soup.title.string else ""
    return t

#uses hashing to assign IDs
def stable_id(url: str, text: str) -> str:
    h = hashlib.sha256((url + "\n" + text).encode("utf-8")).hexdigest()[:16]
    return h

#splits texts into smaller chunks if its too big.
def split_text(text: str, max_chars: int = 2400) -> list[str]:
    # simple paragraph-based splitter (good enough for V1)
    paras = [p.strip() for p in text.split("\n") if p.strip()]
    chunks = []
    cur = []
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

def iter_pages(raw_path: str) -> Iterable[dict]:
    with open(raw_path, "r", encoding="utf-8") as f:
        for line in f:
            yield json.loads(line)

def html_to_main_text(html: str) -> str | None:
    # trafilatura extracts main content (helps remove nav/footer boilerplate)
    extracted = trafilatura.extract(html, include_comments=False, include_tables=True)
    if not extracted:
        return None
    cleaned = "\n".join([ln.strip() for ln in extracted.splitlines() if ln.strip()])
    return cleaned if len(cleaned) > 200 else None  # ignore near-empty pages


#this is the main pipeline function, it reads raw pages and writes clean chuncks
def build_chunks(
    raw_pages_path: str = "data/raw_pages.jsonl",
    out_chunks_path: str = "data/chunks.jsonl",
) -> None:
    written = 0
    seen = set()

    with open(out_chunks_path, "w", encoding="utf-8") as out:
        for page in tqdm(iter_pages(raw_pages_path), desc="Cleaning"):
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
                out.write(json.dumps({
                    "chunk_id": cid,
                    "url": url,
                    "title": title,
                    "text": part,
                }, ensure_ascii=False) + "\n")
                written += 1

    print(f"Saved {written} chunks to {out_chunks_path}")

if __name__ == "__main__":
    build_chunks()