"""Failure analysis + manual judge check for Task 3 (no API calls, works offline).

For every judged question where the judge gave correctness < 1 it decides:
  * RETRIEVAL failure:  at least one piece of information the answer needs is NOT in the documents
                        that were given to the generator (relevant_doc_ids groups, see README)
  * GENERATION failure: all needed documents WERE in the context, but the answer is still wrong
                        (or the system answered an unanswerable question instead of abstaining)

It also writes a sheet with 10 judge decisions for you to check by hand.

Usage (from lab1/):
    uv run python task3_rag/analyze.py --answers task3_rag/results/answers_r4_s200_w0.5.jsonl \
        --judge task3_rag/results/judge_r4_s200_w0.5.jsonl --name r4
Writes task3_rag/results/failure_analysis_<name>.md and judge_manual_check_<name>.md
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from evaluate import dedupe, load_jsonl  # noqa: E402

CATEGORIES = ["identifier", "paraphrase", "multi-hop", "version", "unanswerable"]


def classify(question: dict, answer_row: dict, judge_row: dict) -> tuple[str, str, list[list[str]]]:
    """Return (verdict, explanation, missing_groups). verdict: ok | retrieval | generation."""
    if judge_row["correctness"] >= 1:
        return "ok", "", []
    groups = question["relevant_doc_ids"]
    retrieved = dedupe(answer_row.get("retrieved_doc_ids", []))
    if not groups:
        return "generation", "no answer exists in the documentation, but the system did not abstain", []
    missing = [g for g in groups if not any(d in retrieved for d in g)]
    if missing:
        return ("retrieval",
                f"{len(missing)} of {len(groups)} needed pieces of information not in the top-{len(retrieved)} documents",
                missing)
    return "generation", "all needed documents were in the context, but the answer is wrong", []


def describe(doc_ids: list[str], corpus: dict[str, dict]) -> str:
    return ", ".join(f"{d} ({corpus[d]['type']}: {corpus[d]['title']})" if d in corpus else d for d in doc_ids)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--judge", type=Path, required=True, help="the --out file of judge.py")
    parser.add_argument("--name", default="best")
    parser.add_argument("--check", type=int, default=10, help="judge decisions to put in the manual check sheet")
    args = parser.parse_args()

    corpus = {d["doc_id"]: d for d in load_jsonl(HERE / "data" / "corpus.jsonl")}
    questions = {q["id"]: q for q in load_jsonl(HERE / "data" / "questions_dev.jsonl")}
    answers = {a["id"]: a for a in load_jsonl(args.answers)}
    judged = load_jsonl(args.judge)

    verdicts = {}
    table = defaultdict(lambda: {"ok": 0, "retrieval": 0, "generation": 0})
    for row in judged:
        q, a = questions[row["id"]], answers[row["id"]]
        verdict, why, missing = classify(q, a, row)
        verdicts[row["id"]] = (verdict, why, missing)
        table[row["category"]][verdict] += 1

    print(f"{'category':<14}{'n':>3}{'ok':>5}{'retrieval fail':>16}{'generation fail':>17}")
    total = {"ok": 0, "retrieval": 0, "generation": 0}
    for category in CATEGORIES:
        if category not in table:
            continue
        t = table[category]
        n = sum(t.values())
        print(f"{category:<14}{n:>3}{t['ok']:>5}{t['retrieval']:>16}{t['generation']:>17}")
        for key in total:
            total[key] += t[key]
    print(f"{'TOTAL':<14}{sum(total.values()):>3}{total['ok']:>5}{total['retrieval']:>16}{total['generation']:>17}")

    # ---- failure analysis file: every failure with all the evidence
    failures = [r for r in judged if verdicts[r["id"]][0] != "ok"]
    lines = [f"# Failure analysis ({args.name})", "",
             f"{len(failures)} of {len(judged)} judged answers are not fully correct "
             f"({total['retrieval']} retrieval failures, {total['generation']} generation failures).", "",
             "Pick 5 for the report/video, ideally from different categories, and write down WHY for each.", ""]
    for row in sorted(failures, key=lambda r: (r["category"], r["id"])):
        q, a = questions[row["id"]], answers[row["id"]]
        verdict, why, missing = verdicts[row["id"]]
        retrieved = dedupe(a.get("retrieved_doc_ids", []))
        needed = " AND ".join("(" + " or ".join(g) + ")" for g in q["relevant_doc_ids"]) or "(nothing: unanswerable)"
        lines += [
            f"## {row['id']}  [{row['category']}]  -> {verdict.upper()} failure", "",
            f"- **Question:** {q['question']}",
            f"- **Ground truth:** {q['answer']}",
            f"- **System answer:** {a['answer']}",
            f"- **Judge:** correctness {row['correctness']} - {row.get('correctness_reason', '')}",
            f"- **Needed documents:** {needed}",
            f"- **Given to the generator (rank order):** {describe(retrieved, corpus)}",
            f"- **Missing pieces:** {missing if missing else 'none'}",
            f"- **Classification:** {why}",
            "- **Your explanation (why did it fail?):** ", "",
        ]
    out1 = HERE / "results" / f"failure_analysis_{args.name}.md"
    out1.write_text("\n".join(lines), encoding="utf-8")

    # ---- manual check sheet: half judged-correct, half judged-wrong (as far as available)
    rng = random.Random(0)
    good = [r for r in judged if r["correctness"] >= 1]
    bad = [r for r in judged if r["correctness"] < 1]
    half = args.check // 2
    pick = rng.sample(bad, min(half, len(bad))) + rng.sample(good, min(args.check - min(half, len(bad)), len(good)))
    lines = [f"# Manual check of {len(pick)} judge decisions ({args.name})", "",
             "For each item read the question, the ground truth and the system answer, decide yourself whether the "
             "answer is correct, then compare with the judge. Fill in the last line.", ""]
    for i, row in enumerate(sorted(pick, key=lambda r: r["id"]), 1):
        q, a = questions[row["id"]], answers[row["id"]]
        lines += [
            f"## {i}. {row['id']}  [{row['category']}]", "",
            f"- **Question:** {q['question']}",
            f"- **Ground truth:** {q['answer']}",
            f"- **System answer:** {a['answer']}",
            f"- **Judge correctness:** {row['correctness']}  ({row.get('correctness_reason', '')})",
            f"- **Judge faithfulness:** {row['faithfulness']}   **abstained:** {row['abstained']}",
            "- **My verdict:** correct / partly / wrong     **Agree with judge?** yes / no     **Note:** ", "",
        ]
    out2 = HERE / "results" / f"judge_manual_check_{args.name}.md"
    out2.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nwrote {out1}\nwrote {out2}")


if __name__ == "__main__":
    main()
