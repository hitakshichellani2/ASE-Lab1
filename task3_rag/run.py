"""Command line runner for Task 3. Run everything from the repository root (lab1/).

Retrieval for one configuration (writes results/retrieval_<name>.jsonl, metrics, timing):
    uv run python task3_rag/run.py retrieve --config r1
    uv run python task3_rag/run.py retrieve --config r2
    uv run python task3_rag/run.py retrieve --config r3 --size 100
    uv run python task3_rag/run.py retrieve --config r4 --w 0.5
    uv run python task3_rag/run.py retrieve --config r5 --w 0.5

Experiments:
    uv run python task3_rag/run.py sweep --what size --sizes 50 100 200    # chunk size for R3
    uv run python task3_rag/run.py sweep --what weight                     # hybrid weight w for R4

Answers (RAG generation) for the judge, and test predictions:
    uv run python task3_rag/run.py answer --config r4 --split dev --sample 50
    uv run python task3_rag/run.py answer --config r4 --split test           # -> predictions_test.jsonl
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import retrieval as R  # noqa: E402
from common.llm_client import LLMClient, count_tokens  # noqa: E402
from evaluate import evaluate, format_table  # noqa: E402
from judge import ABSTENTION, stratified_sample  # noqa: E402

RESULTS = HERE / "results"
N_DOCS_FOR_GENERATOR = 5  # the generator sees the top-5 distinct documents (best chunk of each)

SYSTEM_PROMPT = f"""You answer questions about PaderQueue, a message queue, using ONLY the numbered context passages.

Rules:
1. If the passages do not contain the answer, reply with exactly this sentence and nothing else: {ABSTENTION}
2. Versions matter. If the question names a version (for example 2.x or 4.x), answer from the passage for that version. If several versions appear and the question names none, say which version your answer refers to.
3. Official reference pages (config, error, cli, changelog, runbook, incident) are more reliable than forum posts. Forum answers can be wrong or outdated.
4. Answer in one or two sentences and include the exact value, error code or command."""


# ------------------------------------------------------------------------------------------ context

class Context:
    """Holds the shared objects, so chunking and embedding are done once per run."""

    def __init__(self, llm=None) -> None:
        (HERE / "logs").mkdir(exist_ok=True)
        self.llm = llm or LLMClient(log_path=HERE / "logs" / "task3_llm.jsonl")
        self.corpus = R.load_corpus()
        self.queries = R.QueryCache(self.llm)
        self.hyde = R.HydeCache(self.llm)
        self._chunks: dict = {}
        self._dense: dict = {}
        self._bm25: dict = {}

    def chunks(self, kind: str, size: int, overlap: int) -> list[R.Chunk]:
        key = (kind, size, overlap)
        if key not in self._chunks:
            chunker = R.chunk_fixed if kind == "fixed" else R.chunk_recursive
            self._chunks[key] = chunker(self.corpus, size, overlap)
        return self._chunks[key]

    def dense(self, kind: str, size: int, overlap: int) -> R.DenseRetriever:
        key = (kind, size, overlap)
        if key not in self._dense:
            self._dense[key] = R.DenseRetriever(
                self.llm, self.chunks(*key), self.queries, name=f"{kind}_{size}_{overlap}"
            )
        return self._dense[key]

    def bm25(self, size: int, overlap: int) -> R.BM25Retriever:
        key = (size, overlap)
        if key not in self._bm25:
            self._bm25[key] = R.BM25Retriever(self.chunks("rec", size, overlap))
        return self._bm25[key]

    def build(self, config: str, size: int, overlap: int, fixed_size: int | None, w: float) -> R.Retriever:
        if config == "r1":
            retriever = self.bm25(size, overlap)           # BM25 on the SAME chunks as R3
            retriever.name = "r1_bm25"
        elif config == "r2":
            retriever = self.dense("fixed", fixed_size or size, overlap)
            retriever.name = "r2_fixed_dense"
        elif config == "r3":
            retriever = self.dense("rec", size, overlap)
            retriever.name = "r3_recursive_dense"
        elif config == "r4":
            retriever = R.HybridRetriever(self.bm25(size, overlap), self.dense("rec", size, overlap), w)
        elif config == "r5":
            retriever = R.HydeRetriever(self.bm25(size, overlap), self.dense("rec", size, overlap), self.hyde, w)
        else:
            raise ValueError(config)
        return retriever

    def save_caches(self) -> None:
        self.queries.save()
        self.hyde.save()


def load_questions(split: str) -> list[dict]:
    return R.load_jsonl(R.DATA / f"questions_{split}.jsonl")


def default_name(args) -> str:
    if args.name:
        return args.name
    parts = [args.config]
    if args.config == "r2":
        parts.append(f"s{args.fixed_size or args.size}")
    else:
        parts.append(f"s{args.size}")
    if args.config in ("r4", "r5"):
        parts.append(f"w{args.w}")
    return "_".join(parts)


def query_tokens(retriever: R.Retriever, question: str) -> int:
    """Approximate tokens sent to a model for retrieval of ONE query (not counting generation)."""
    if isinstance(retriever, R.BM25Retriever):
        return 0
    if isinstance(retriever, R.HydeRetriever):
        passage, _ = retriever.hyde.get(question)
        return (count_tokens(R.HYDE_PROMPT.format(question=question)) + count_tokens(passage)
                + count_tokens(question + "\n" + passage))
    if isinstance(retriever, R.HybridRetriever):
        return count_tokens(question)
    return count_tokens(question)


# ------------------------------------------------------------------------------------------ retrieve

def cmd_retrieve(args, ctx: Context) -> None:
    questions = load_questions(args.split)
    if args.config == "r5":
        print("Generating HyDE passages (parallel) ...")
        ctx.hyde.prefetch([q["question"] for q in questions])
    retriever = ctx.build(args.config, args.size, args.overlap, args.fixed_size, args.w)
    name = default_name(args)
    RESULTS.mkdir(exist_ok=True)

    results, api_latency = [], []
    for q in questions:
        hits = retriever.retrieve(q["question"], args.k)
        results.append({"id": q["id"], "retrieved_doc_ids": [h.doc_id for h in hits]})
        api_latency.append(retriever.last_timing["embed_s"] + retriever.last_timing["llm_s"])
    ctx.save_caches()

    # second pass: everything is cached in memory, so this measures the local search time only
    local = []
    for q in questions:
        start = time.perf_counter()
        retriever.retrieve(q["question"], args.k)
        local.append(time.perf_counter() - start)

    out = RESULTS / f"retrieval_{name}_{args.split}.jsonl"
    out.write_text("\n".join(json.dumps(r) for r in results) + "\n", encoding="utf-8")

    n = len(questions)
    timing = {
        "name": name, "split": args.split, "n_chunks": len(retriever.chunks),
        "index_seconds": round(retriever.index_seconds, 2),
        "api_latency_s_per_query": round(sum(api_latency) / n, 4),
        "local_search_s_per_query": round(sum(local) / n, 5),
        "latency_s_per_query": round(sum(api_latency) / n + sum(local) / n, 4),
        "approx_tokens_per_query": round(sum(query_tokens(retriever, q["question"]) for q in questions) / n, 1),
    }
    (RESULTS / f"timing_{name}_{args.split}.json").write_text(json.dumps(timing, indent=2), encoding="utf-8")
    print(f"wrote {out}")
    print(json.dumps(timing))

    if args.split == "dev":
        for k in (5, 10):
            report = evaluate(results, questions, k)
            print(format_table(report["summary"], name))
            (RESULTS / f"metrics_{name}_k{k}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


# ------------------------------------------------------------------------------------------ sweep

def _score(retriever: R.Retriever, dev: list[dict], label: str) -> dict:
    results = [{"id": q["id"], "retrieved_doc_ids": [h.doc_id for h in retriever.retrieve(q["question"], 10)]}
               for q in dev]
    half_a = [q for i, q in enumerate(dev) if i % 2 == 0]
    half_b = [q for i, q in enumerate(dev) if i % 2 == 1]
    full = evaluate(results, dev, 5)["summary"]
    row = {
        "label": label, "n_chunks": len(retriever.chunks),
        "recall@5": round(full["overall"]["context_recall"], 3),
        "precision@5": round(full["overall"]["context_precision"], 3),
        "recall_tune_half": round(evaluate(results, half_a, 5)["summary"]["overall"]["context_recall"], 3),
        "recall_holdout_half": round(evaluate(results, half_b, 5)["summary"]["overall"]["context_recall"], 3),
    }
    for category, s in full["per_category"].items():
        row[f"recall_{category}"] = round(s["context_recall"], 3)
    return row


def cmd_sweep(args, ctx: Context) -> None:
    dev = load_questions("dev")
    rows = []
    if args.what == "size":
        for size in args.sizes:
            retriever = ctx.build("r3", size, args.overlap, None, args.w)
            print(f"R3 size={size}: {len(retriever.chunks)} chunks, indexing {retriever.index_seconds:.1f}s")
            rows.append(_score(retriever, dev, f"r3 size={size} overlap={args.overlap}"))
            ctx.save_caches()
    else:
        for i in range(11):
            w = i / 10
            retriever = ctx.build("r4", args.size, args.overlap, None, w)
            rows.append(_score(retriever, dev, f"r4 w={w}"))
            ctx.save_caches()
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"sweep_{args.what}.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    for row in rows:
        print(row)
    print(f"wrote {out}")
    if args.what == "weight":
        best = max(rows, key=lambda r: r["recall_tune_half"])
        print(f"\nbest on the TUNE half: {best['label']}  ->  its HOLDOUT-half recall is {best['recall_holdout_half']}")
        print("Pick w with the tune half, and report the holdout half as the honest number.")


# ------------------------------------------------------------------------------------------ answer

def build_prompt(question: str, contexts: list[str]) -> str:
    numbered = "\n\n".join(f"[{i}] {text}" for i, text in enumerate(contexts, 1))
    return f"Context passages:\n\n{numbered}\n\nQuestion: {question}"


def cmd_answer(args, ctx: Context) -> None:
    questions = load_questions(args.split)
    if args.sample:
        questions = stratified_sample(questions, args.sample)  # the same sample judge.py uses
    if args.config == "r5":
        ctx.hyde.prefetch([q["question"] for q in questions])
    retriever = ctx.build(args.config, args.size, args.overlap, args.fixed_size, args.w)
    name = default_name(args)

    retrieved = []
    for q in questions:  # retrieval is sequential: it uses the disk caches
        hits = retriever.retrieve(q["question"], N_DOCS_FOR_GENERATOR)
        retrieved.append(([h.doc_id for h in hits], [h.chunk.text for h in hits]))
    ctx.save_caches()

    def generate(item):
        q, (doc_ids, contexts) = item
        messages = [{"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_prompt(q["question"], contexts)}]
        start = time.perf_counter()
        answer = (ctx.llm.chat(messages) or "").strip() or ABSTENTION
        return {
            "id": q["id"], "answer": answer, "doc_ids": doc_ids, "contexts": contexts,
            "seconds": time.perf_counter() - start,
            "prompt_tokens": sum(count_tokens(m["content"]) for m in messages),
            "answer_tokens": count_tokens(answer),
        }

    print(f"Generating {len(questions)} answers with {ctx.llm.model} ...")
    with ThreadPoolExecutor(6) as pool:
        generated = list(pool.map(generate, zip(questions, retrieved)))

    RESULTS.mkdir(exist_ok=True)
    if args.split == "test":
        out = args.out or HERE / "predictions_test.jsonl"
        lines = [{"id": g["id"], "answer": g["answer"], "retrieved_doc_ids": g["doc_ids"]} for g in generated]
    else:
        out = args.out or RESULTS / f"answers_{name}.jsonl"
        lines = [{"id": g["id"], "answer": g["answer"], "contexts": g["contexts"],
                  "retrieved_doc_ids": g["doc_ids"]} for g in generated]
    Path(out).write_text("\n".join(json.dumps(line, ensure_ascii=False) for line in lines) + "\n", encoding="utf-8")

    n = len(generated)
    stats = {
        "name": name, "split": args.split, "n": n,
        "generation_s_per_question": round(sum(g["seconds"] for g in generated) / n, 2),
        "prompt_tokens_per_question": round(sum(g["prompt_tokens"] for g in generated) / n, 1),
        "answer_tokens_per_question": round(sum(g["answer_tokens"] for g in generated) / n, 1),
        "abstentions": sum(g["answer"].strip().strip('."`').lower() == ABSTENTION.rstrip(".").lower() for g in generated),
    }
    (RESULTS / f"gen_stats_{name}_{args.split}.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(f"wrote {out}")
    print(json.dumps(stats))
    print(ctx.llm.usage_summary())
    if args.split == "dev":
        print(f"\nNext: uv run python task3_rag/judge.py {out} --sample 50 --out results/judge_{name}.jsonl")


# ------------------------------------------------------------------------------------------ main

def main(llm=None) -> None:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", choices=["r1", "r2", "r3", "r4", "r5"], default="r4")
    common.add_argument("--size", type=int, default=100, help="chunk size in words (R1, R3, R4, R5)")
    common.add_argument("--overlap", type=int, default=10, help="chunk overlap in words")
    common.add_argument("--fixed-size", type=int, default=None, help="R2 chunk size in words (default: --size)")
    common.add_argument("--w", type=float, default=0.5, help="hybrid weight of the dense score (R4, R5)")
    common.add_argument("--name", default=None, help="name used in the result file names")

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("retrieve", parents=[common])
    p.add_argument("--split", choices=["dev", "test"], default="dev")
    p.add_argument("--k", type=int, default=10, help="documents written per question")

    p = sub.add_parser("sweep", parents=[common])
    p.add_argument("--what", choices=["size", "weight"], required=True)
    p.add_argument("--sizes", type=int, nargs="+", default=[50, 100, 200])

    p = sub.add_parser("answer", parents=[common])
    p.add_argument("--split", choices=["dev", "test"], default="dev")
    p.add_argument("--sample", type=int, default=None, help="stratified sample size (dev), same as judge.py --sample")
    p.add_argument("--out", type=Path, default=None)

    args = parser.parse_args()
    ctx = Context(llm)
    {"retrieve": cmd_retrieve, "sweep": cmd_sweep, "answer": cmd_answer}[args.cmd](args, ctx)
    ctx.save_caches()


if __name__ == "__main__":
    main()
