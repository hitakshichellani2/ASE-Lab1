"""For chosen dev questions: at which rank does each NEEDED document appear in R1 / R3 / R4 (top 10)?

Usage (from lab1/):
    uv run python task3_rag/rank_check.py dev025 dev042 dev004 dev087 dev079

Needs the retrieval files written by `run.py retrieve` (size 200). Missing files are skipped.
Runs offline, no API calls.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
FILES = {
    "R1 BM25": RESULTS / "retrieval_r1_s200_dev.jsonl",
    "R3 dense": RESULTS / "retrieval_r3_s200_dev.jsonl",
    "R4 hybrid": RESULTS / "retrieval_r4_s200_w0.5_dev.jsonl",
}


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ids", nargs="+")
    args = parser.parse_args()

    corpus = {d["doc_id"]: d for d in load(HERE / "data" / "corpus.jsonl")}
    questions = {q["id"]: q for q in load(HERE / "data" / "questions_dev.jsonl")}
    runs: dict[str, dict[str, list[str]]] = {}
    for name, path in FILES.items():
        if path.exists():
            runs[name] = {r["id"]: r["retrieved_doc_ids"] for r in load(path)}
        else:
            print(f"(skipping {name}: {path.name} not found, run: run.py retrieve --config ... --size 200)")

    for qid in args.ids:
        q = questions[qid]
        print(f"\n=== {qid} [{q['category']}]\nQ:  {q['question']}\nGT: {q['answer'][:140]}")
        for group in q["relevant_doc_ids"]:
            label = " or ".join(f"{d} ({corpus[d]['type']}: {corpus[d]['title']})" for d in group)
            ranks = []
            for name, run in runs.items():
                top = run[qid]
                found = [top.index(d) + 1 for d in group if d in top]
                ranks.append(f"{name}: {'rank ' + str(min(found)) if found else 'NOT in top 10'}")
            print(f"  needed {label}\n     " + "   |   ".join(ranks))
        if "R4 hybrid" in runs:
            print("  R4 top 5:")
            for i, d in enumerate(runs["R4 hybrid"][qid][:5], 1):
                print(f"     {i}. {d} {corpus[d]['type']}: {corpus[d]['title']}")


if __name__ == "__main__":
    main()
