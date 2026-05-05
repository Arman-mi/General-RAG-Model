from __future__ import annotations

import os
from dotenv import load_dotenv
from openai import OpenAI
import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

load_dotenv()

SYSTEM = """You are a strict fact-grounded assistant.
You MUST answer using ONLY the provided excerpts from twodots.net.
If the excerpts do not contain enough information, say:
"Not found on twodots.net."
Do not use outside knowledge. Do not guess.
Always include citations as a bullet list of URLs you used.
"""

def answer(question: str, k: int = 6) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY.")

    # vector db
    client = chromadb.PersistentClient(path="data/chroma")
    embed_fn = OpenAIEmbeddingFunction(api_key=api_key, model_name="text-embedding-3-large")
    col = client.get_collection(name="twodots_net", embedding_function=embed_fn)

    res = col.query(query_texts=[question], n_results=k)

    docs = res["documents"][0]
    metas = res["metadatas"][0]

    excerpts = []
    urls = []
    for d, m in zip(docs, metas):
        url = m.get("url", "")
        title = m.get("title", "")
        excerpts.append(f"URL: {url}\nTITLE: {title}\nEXCERPT:\n{d}")
        urls.append(url)

    # de-dupe urls, preserve order
    seen = set()
    cite_urls = []
    for u in urls:
        if u and u not in seen:
            cite_urls.append(u)
            seen.add(u)

    context = "\n\n---\n\n".join(excerpts)

    user_prompt = f"""Question: {question}

Excerpts from twodots.net:
{context}

Write the answer. If not supported, output exactly: Not found on twodots.net.
Then add:
Citations:
- <url>
- <url>
(using only URLs from the excerpts you relied on).
"""

    llm = OpenAI(api_key=api_key)

    resp = llm.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
    )
    return resp.choices[0].message.content

if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]).strip()
    if not q:
        print("Usage: python -m twodots_rag.qa \"your question\"")
        raise SystemExit(2)
    print(answer(q))