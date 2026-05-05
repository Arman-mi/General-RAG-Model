from __future__ import annotations

import json
import os
from dotenv import load_dotenv

import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
from tqdm import tqdm

load_dotenv()

def iter_chunks(path: str):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            yield json.loads(line)


#builds vector index from the cleaned chunks
def build_index(
    chunks_path: str = "data/chunks.jsonl",
    persist_dir: str = "data/chroma",
    collection_name: str = "twodots_net",
):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY in environment.")

    client = chromadb.PersistentClient(path=persist_dir)

    embed_fn = OpenAIEmbeddingFunction(
        api_key=api_key,
        model_name="text-embedding-3-large",
    )

    col = client.get_or_create_collection(
        name=collection_name,
        embedding_function=embed_fn,
        metadata={"source": "https://www.twodots.net/"},
    )

    ids, docs, metas = [], [], []

    for c in tqdm(iter_chunks(chunks_path), desc="Indexing"):
        ids.append(c["chunk_id"])
        docs.append(c["text"])
        metas.append({"url": c["url"], "title": c.get("title", "")})

        # batch insert
        if len(ids) >= 100:
            col.upsert(ids=ids, documents=docs, metadatas=metas)
            ids, docs, metas = [], [], []

    if ids:
        col.upsert(ids=ids, documents=docs, metadatas=metas)

    print("Index built.")

if __name__ == "__main__":
    build_index()