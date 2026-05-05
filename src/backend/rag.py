from __future__ import annotations

import os
import re
from typing import List, Tuple

import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

SYSTEM_PROMPT = """You are a strict fact-grounded assistant.

You MUST answer using ONLY the provided excerpts from the indexed website.
If the excerpts do not contain enough information, respond exactly with:
Not found on the indexed website.

Rules:
- Do not use outside knowledge.
- Do not guess.
- Do not mention information that is not supported by the excerpts.
- Keep the answer concise and accurate.
"""

NOT_FOUND = "Not found on the indexed website."


def get_collection(persist_dir: str, collection_name: str):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY.")

    client = chromadb.PersistentClient(path=persist_dir)
    embed_fn = OpenAIEmbeddingFunction(
        api_key=api_key,
        model_name=os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large"),
    )

    return client.get_collection(
        name=collection_name,
        embedding_function=embed_fn,
    )


def dedupe_urls(urls: List[str]) -> List[str]:
    seen = set()
    out = []
    for url in urls:
        if url and url not in seen:
            seen.add(url)
            out.append(url)
    return out


def extract_urls(text: str) -> List[str]:
    urls = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("- http://") or line.startswith("- https://"):
            urls.append(line[2:].strip())
    return dedupe_urls(urls)


def ask_site(
    question: str,
    *,
    persist_dir: str,
    collection_name: str,
    site_url: str | None = None,
    k: int = 6,
) -> Tuple[str, List[str]]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY.")

    collection = get_collection(persist_dir=persist_dir, collection_name=collection_name)
    llm = OpenAI(api_key=api_key)

    result = collection.query(
        query_texts=[question],
        n_results=k,
    )

    docs = result["documents"][0] if result.get("documents") else []
    metas = result["metadatas"][0] if result.get("metadatas") else []

    if not docs or not metas:
        return NOT_FOUND, []

    excerpts = []
    urls = []

    for doc, meta in zip(docs, metas):
        url = meta.get("url", "")
        title = meta.get("title", "")
        urls.append(url)
        excerpts.append(
            f"URL: {url}\nTITLE: {title}\nEXCERPT:\n{doc}"
        )

    citation_urls = dedupe_urls(urls)
    context = "\n\n---\n\n".join(excerpts)

    src_line = f"Excerpts from: {site_url}" if site_url else "Excerpts:"

    user_prompt = f"""Question: {question}

{src_line}
{context}

Answer the question using only the excerpts.
If the excerpts do not support an answer, output exactly:
{NOT_FOUND}

After your answer, add:

Citations:
- <url>
- <url>

Use only the URLs you actually relied on.
"""

    response = llm.chat.completions.create(
        model=os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"),
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )

    content = response.choices[0].message.content.strip()

    if content == NOT_FOUND:
        return NOT_FOUND, []

    if "Citations:" in content:
        answer_part = content.split("Citations:", 1)[0].strip()
        cited_urls = extract_urls(content.split("Citations:", 1)[1])
        return answer_part, cited_urls

    return content, citation_urls
