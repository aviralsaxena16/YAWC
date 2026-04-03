from __future__ import annotations

from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

from yawc_config import CHROMA_PERSIST_DIR

_chroma_client = chromadb.PersistentClient(path=str(CHROMA_PERSIST_DIR))
_embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)


def _get_collection(chat_id: str) -> chromadb.Collection:
    """Get or create a ChromaDB collection scoped to this chat session."""
    safe_id = f"yawc_{chat_id.replace('-', '_')[:40]}"
    return _chroma_client.get_or_create_collection(
        name=safe_id,
        embedding_function=_embed_fn,
        metadata={"chat_id": chat_id},
    )


def _chunk_text(text: str, chunk_size: int = 400, overlap: int = 60) -> list[str]:
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i : i + chunk_size]).strip()
        if chunk:
            chunks.append(chunk)
        i += chunk_size - overlap
    return chunks


def _ingest_posts_blocking(chat_id: str, posts: list[dict]) -> int:
    collection = _get_collection(chat_id)
    docs, ids, metas = [], [], []
    for post in posts:
        title = post.get("title", "")
        body = (
            post.get("body")
            or post.get("description")
            or post.get("alt")
            or ""
        )
        url = post.get("url", "")
        plat = post.get("platform", "web")
        combined = f"{title}\n\n{body}".strip()
        if not combined:
            continue
        for ci, chunk in enumerate(_chunk_text(combined)):
            cid = __import__("hashlib").md5(f"{url}_{ci}".encode()).hexdigest()
            docs.append(chunk)
            ids.append(cid)
            metas.append({
                "chat_id": chat_id,
                "url": url,
                "title": title[:200],
                "platform": plat,
                "source_index": post.get("index", 0),
            })
    if docs:
        collection.upsert(documents=docs, ids=ids, metadatas=metas)
    print(f"[YAWC/RAG] Ingested {len(docs)} chunks | chat={chat_id}", flush=True)
    return len(docs)


async def ingest_posts(chat_id: str, posts: list[dict]) -> int:
    from asyncio import get_event_loop
    from yawc_config import THREAD_POOL

    loop = get_event_loop()
    return await loop.run_in_executor(
        THREAD_POOL, _ingest_posts_blocking, chat_id, posts
    )


def _query_rag_blocking(chat_id: str, query: str, n_results: int = 8) -> list[dict]:
    collection = _get_collection(chat_id)
    count = collection.count()
    if count == 0:
        return []
    n = min(n_results, count)
    results = collection.query(
        query_texts=[query],
        n_results=n,
        where={"chat_id": chat_id},
    )
    chunks = []
    for i, doc in enumerate(results["documents"][0]):
        meta = results["metadatas"][0][i] if results["metadatas"] else {}
        chunks.append({
            "text": doc,
            "url": meta.get("url", ""),
            "title": meta.get("title", ""),
            "platform": meta.get("platform", ""),
        })
    return chunks


async def query_rag(chat_id: str, query: str) -> list[dict]:
    from asyncio import get_event_loop
    from yawc_config import THREAD_POOL

    loop = get_event_loop()
    return await loop.run_in_executor(
        THREAD_POOL, _query_rag_blocking, chat_id, query
    )
