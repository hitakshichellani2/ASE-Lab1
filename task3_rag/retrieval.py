"""Retrieval library for Task 3 (PaderQueue). No RAG frameworks, only numpy + rank_bm25.

Configurations (see run.py):
  R1  BM25 on recursive chunks (the same chunks as R3)
  R2  fixed-size chunks + dense embeddings
  R3  recursive chunks (headings -> paragraphs -> lines -> sentences) + dense embeddings
  R4  hybrid: min-max normalized BM25 and dense scores, combined with weight w
  R5  R4 + HyDE (the dense query is the question plus a hypothetical answer passage written by the LLM)

Chunk sizes are measured in words (about 1.3 tokens per word). Every chunk starts with a header line
"<title> [<type>, <version>]", so even a small fragment of a long document knows where it comes from.
"""

from __future__ import annotations

import hashlib
import json
import pickle
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
CACHE = HERE / ".cache"   # do NOT submit this folder (embeddings are large)


# ------------------------------------------------------------------------------------------ data

def load_jsonl(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_corpus() -> list[dict]:
    return load_jsonl(DATA / "corpus.jsonl")


@dataclass
class Chunk:
    doc_id: str
    text: str  # includes the header line


def _header(doc: dict) -> str:
    return f"{doc['title']} [{doc['type']}, {doc.get('version') or 'n/a'}]"


def _n_words(text: str) -> int:
    return len(text.split())


# ------------------------------------------------------------------------------------------ chunkers

def chunk_fixed(corpus: list[dict], size: int, overlap: int) -> list[Chunk]:
    """R2: sliding window of `size` words, `overlap` words shared with the previous window.
    Deliberately blind to structure (headings, paragraphs)."""
    assert 0 <= overlap < size
    chunks: list[Chunk] = []
    for doc in corpus:
        words = doc["text"].split()
        start = 0
        while True:
            piece = " ".join(words[start : start + size])
            chunks.append(Chunk(doc["doc_id"], f"{_header(doc)}\n{piece}"))
            if start + size >= len(words):
                break
            start += size - overlap
    return chunks


_SPLITTERS = [
    re.compile(r"(?m)^(?=#{1,6} )"),   # markdown headings (keeps the heading with its text)
    re.compile(r"\n\s*\n"),            # paragraphs
    re.compile(r"\n"),                 # lines (table rows, list items)
    re.compile(r"(?<=[.!?])\s+"),      # sentences
]


def _split_recursive(text: str, size: int, level: int = 0) -> list[str]:
    """Split text into pieces of at most `size` words: try the coarsest separator first,
    and only go to a finer one for pieces that are still too big."""
    text = text.strip()
    if not text:
        return []
    if _n_words(text) <= size:
        return [text]
    if level >= len(_SPLITTERS):  # no separator left: cut hard by words
        words = text.split()
        return [" ".join(words[i : i + size]) for i in range(0, len(words), size)]
    parts = [p for p in _SPLITTERS[level].split(text) if p.strip()]
    if len(parts) == 1:
        return _split_recursive(text, size, level + 1)
    pieces: list[str] = []
    for part in parts:
        pieces.extend(_split_recursive(part, size, level + 1))
    return pieces


def _merge_pieces(pieces: list[str], size: int) -> list[str]:
    """Greedily merge neighbouring small pieces so chunks come close to `size` words."""
    merged: list[str] = []
    current = ""
    for piece in pieces:
        candidate = f"{current}\n{piece}" if current else piece
        if current and _n_words(candidate) > size:
            merged.append(current)
            current = piece
        else:
            current = candidate
    if current:
        merged.append(current)
    return merged


def chunk_recursive(corpus: list[dict], size: int, overlap: int) -> list[Chunk]:
    """R3: structure-aware chunks. Each chunk after the first starts with the last `overlap`
    words of the previous chunk."""
    assert 0 <= overlap < size
    chunks: list[Chunk] = []
    for doc in corpus:
        merged = _merge_pieces(_split_recursive(doc["text"], size), size)
        previous_tail = ""
        for piece in merged:
            body = f"{previous_tail}\n{piece}".strip() if previous_tail else piece
            chunks.append(Chunk(doc["doc_id"], f"{_header(doc)}\n{body}"))
            previous_tail = " ".join(piece.split()[-overlap:]) if overlap else ""
    return chunks


# ------------------------------------------------------------------------------------------ BM25

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:[._\-/][A-Za-z0-9]+)*")
_PART_RE = re.compile(r"[._\-/]")


def tokenize(text: str) -> list[str]:
    """Lowercase tokens. Identifiers like `PQ-E4663` or `spool.buffer_bytes` are kept whole AND
    split into their parts, so both the exact identifier and a partial mention can match."""
    tokens: list[str] = []
    for match in _TOKEN_RE.findall(text.lower()):
        tokens.append(match)
        parts = [p for p in _PART_RE.split(match) if p]
        if len(parts) > 1:
            tokens.extend(parts)
    return tokens


class BM25Index:
    def __init__(self, chunks: list[Chunk]) -> None:
        start = time.perf_counter()
        self.bm25 = BM25Okapi([tokenize(c.text) for c in chunks])
        self.index_seconds = time.perf_counter() - start

    def scores(self, query: str) -> np.ndarray:
        return np.asarray(self.bm25.get_scores(tokenize(query)), dtype=np.float32)


# ------------------------------------------------------------------------------------------ dense

def _normalize(v: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(norms, 1e-12)


class QueryCache:
    """Disk cache {text: (normalized vector, seconds the first call took)}.
    Keeps experiments fast and lets us report the FIRST-call latency, not the cache-hit latency."""

    def __init__(self, llm, name: str = "queries") -> None:
        self.llm = llm
        model = str(getattr(llm, "embedding_model", "emb")).replace("/", "_")
        self.path = CACHE / f"{name}_{model}.pkl"
        self.data: dict[str, tuple[np.ndarray, float]] = {}
        if self.path.exists():
            self.data = pickle.loads(self.path.read_bytes())

    def get(self, text: str) -> tuple[np.ndarray, float]:
        if text not in self.data:
            start = time.perf_counter()
            vec = _normalize(self.llm.embed([text]))[0]
            self.data[text] = (vec, time.perf_counter() - start)
        return self.data[text]

    def save(self) -> None:
        CACHE.mkdir(exist_ok=True)
        self.path.write_bytes(pickle.dumps(self.data))


class DenseIndex:
    def __init__(self, llm, chunks: list[Chunk], name: str) -> None:
        CACHE.mkdir(exist_ok=True)
        model = str(getattr(llm, "embedding_model", "emb")).replace("/", "_")
        digest = hashlib.sha256((model + "\x00".join(c.text for c in chunks)).encode()).hexdigest()[:12]
        cache_file = CACHE / f"dense_{name}_{digest}.npz"
        if cache_file.exists():
            saved = np.load(cache_file)
            self.matrix, self.index_seconds = saved["matrix"], float(saved["seconds"])
        else:
            start = time.perf_counter()
            self.matrix = _normalize(llm.embed([c.text for c in chunks]))
            self.index_seconds = time.perf_counter() - start
            np.savez(cache_file, matrix=self.matrix, seconds=self.index_seconds)

    def scores(self, query_vec: np.ndarray) -> np.ndarray:
        return self.matrix @ query_vec


# ------------------------------------------------------------------------------------------ HyDE

HYDE_PROMPT = (
    "Write a short passage (60-100 words) in the style of technical reference documentation for a "
    "message queue called PaderQueue. The passage should answer the question below. Use the "
    "terminology a documentation page would use (option names, error names, command names), and keep "
    "identifiers that appear in the question. Never say that you do not know.\n\nQuestion: {question}"
)


class HydeCache:
    """Disk cache {question: (hypothetical passage, seconds)}; generation runs in parallel."""

    def __init__(self, llm) -> None:
        self.llm = llm
        self.path = CACHE / "hyde.pkl"
        self.data: dict[str, tuple[str, float]] = {}
        if self.path.exists():
            self.data = pickle.loads(self.path.read_bytes())

    def _generate(self, question: str) -> None:
        start = time.perf_counter()
        passage = self.llm.chat([{"role": "user", "content": HYDE_PROMPT.format(question=question)}])
        self.data[question] = (passage.strip(), time.perf_counter() - start)

    def prefetch(self, questions: list[str], workers: int = 6) -> None:
        missing = [q for q in questions if q not in self.data]
        if missing:
            with ThreadPoolExecutor(workers) as pool:
                list(pool.map(self._generate, missing))
            self.save()

    def get(self, question: str) -> tuple[str, float]:
        if question not in self.data:
            self._generate(question)
        return self.data[question]

    def save(self) -> None:
        CACHE.mkdir(exist_ok=True)
        self.path.write_bytes(pickle.dumps(self.data))


# ------------------------------------------------------------------------------------------ retrievers

def minmax(x: np.ndarray) -> np.ndarray:
    lo, hi = float(x.min()), float(x.max())
    return (x - lo) / (hi - lo) if hi > lo else np.zeros_like(x)


@dataclass
class Hit:
    doc_id: str
    chunk: Chunk
    score: float


class Retriever:
    """Base class. `rank_chunks` returns chunk indices best-first; `retrieve` collapses them to
    distinct documents (best chunk per document), which is what evaluate.py and the generator use."""

    name = "base"
    chunks: list[Chunk]
    index_seconds = 0.0

    def __init__(self) -> None:
        self.last_timing: dict[str, float] = {}

    def score_chunks(self, question: str) -> np.ndarray:
        raise NotImplementedError

    def retrieve(self, question: str, n_docs: int = 10) -> list[Hit]:
        start = time.perf_counter()
        scores = self.score_chunks(question)
        order = np.argsort(-scores)
        hits: list[Hit] = []
        seen: set[str] = set()
        for i in order:
            chunk = self.chunks[i]
            if chunk.doc_id in seen:
                continue
            seen.add(chunk.doc_id)
            hits.append(Hit(chunk.doc_id, chunk, float(scores[i])))
            if len(hits) == n_docs:
                break
        self.last_timing["total_wall_s"] = time.perf_counter() - start
        return hits


class BM25Retriever(Retriever):
    def __init__(self, chunks: list[Chunk], name: str = "r1_bm25") -> None:
        super().__init__()
        self.name, self.chunks = name, chunks
        self.bm25 = BM25Index(chunks)
        self.index_seconds = self.bm25.index_seconds

    def score_chunks(self, question: str) -> np.ndarray:
        self.last_timing = {"embed_s": 0.0, "llm_s": 0.0}
        return self.bm25.scores(question)


class DenseRetriever(Retriever):
    def __init__(self, llm, chunks: list[Chunk], queries: QueryCache, name: str) -> None:
        super().__init__()
        self.name, self.chunks, self.queries = name, chunks, queries
        self.dense = DenseIndex(llm, chunks, name)
        self.index_seconds = self.dense.index_seconds

    def score_chunks(self, question: str) -> np.ndarray:
        vec, embed_s = self.queries.get(question)
        self.last_timing = {"embed_s": embed_s, "llm_s": 0.0}
        return self.dense.scores(vec)


class HybridRetriever(Retriever):
    """R4. score = w * minmax(dense) + (1 - w) * minmax(bm25). Both are normalized over all chunks."""

    def __init__(self, bm25: BM25Retriever, dense: DenseRetriever, w: float, name: str = "r4_hybrid") -> None:
        super().__init__()
        assert bm25.chunks is dense.chunks or len(bm25.chunks) == len(dense.chunks)
        self.name, self.chunks, self.bm25, self.dense, self.w = name, dense.chunks, bm25, dense, w
        self.index_seconds = bm25.index_seconds + dense.index_seconds

    def score_chunks(self, question: str) -> np.ndarray:
        bm25_scores = self.bm25.score_chunks(question)
        dense_scores = self.dense.score_chunks(question)
        self.last_timing = dict(self.dense.last_timing)
        return self.w * minmax(dense_scores) + (1 - self.w) * minmax(bm25_scores)


class HydeRetriever(Retriever):
    """R5. Dense side uses the question + a hypothetical answer passage. BM25 keeps the ORIGINAL
    question, because the LLM does not know PaderQueue and invents identifiers (which would hurt keyword search)."""

    def __init__(self, bm25: BM25Retriever, dense: DenseRetriever, hyde: HydeCache, w: float,
                 name: str = "r5_hyde") -> None:
        super().__init__()
        self.name, self.chunks, self.bm25, self.dense, self.hyde, self.w = name, dense.chunks, bm25, dense, hyde, w
        self.index_seconds = bm25.index_seconds + dense.index_seconds

    def score_chunks(self, question: str) -> np.ndarray:
        passage, llm_s = self.hyde.get(question)
        vec, embed_s = self.dense.queries.get(question + "\n" + passage)
        self.last_timing = {"embed_s": embed_s, "llm_s": llm_s}
        dense_scores = self.dense.dense.scores(vec)
        bm25_scores = self.bm25.score_chunks(question)
        return self.w * minmax(dense_scores) + (1 - self.w) * minmax(bm25_scores)
