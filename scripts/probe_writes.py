"""Câu hỏi dò cho các cạnh agent đã ghi: đo lỗi bền vững (DECISIONS D15, O7).

Bước 1. Sinh câu hỏi dò (mỗi cạnh agent ghi MỚI một câu):
  .venv\\Scripts\\python scripts\\probe_writes.py gen --run data\\runs\\shared-v2 --workers 4
  → data\\runs\\shared-v2\\probes.json
  LLM viết câu hỏi từ CÂU VĂN NGUỒN (không được xem quan hệ agent đã ghi), nên đáp án lấy theo văn bản, không theo cạnh.
  Câu hỏi phải nhắc tên đầu cạnh (để agent xuất phát được, D14); đáp án phải chép nguyên từ văn bản.

Bước 2. Chạy agent trên câu hỏi dò, mỗi câu 2 lần:
  .venv\\Scripts\\python scripts\\probe_writes.py run --run data\\runs\\shared-v2 --workers 4
  before = đồ thị gốc (chưa có cạnh agent ghi), after = graph_after.json của lượt chạy.
  Mỗi lần chạy trên một BẢN SAO đồ thị (phép ghi trong lúc dò không giữ lại), không có bước cập nhật bộ nhớ.
  → data\\runs\\shared-v2\\probe_run\\ : episodes.jsonl, gates.jsonl, summary.json
"""
from __future__ import annotations

import argparse
import random
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dcg import agent as agent_mod  # noqa: E402
from dcg.common import DATA, append_jsonl, load_relations, read_json, read_jsonl, strip_paren, write_json  # noqa: E402
from dcg.gates import GATES  # noqa: E402
from dcg.graph import KG  # noqa: E402
from dcg.metrics import contains_gold, f1, normalize_answer  # noqa: E402

PROBE_VERSION = "probe-v2"
PROMPT = """PROBE QUESTION WRITING.
Entity H: {head}
Entity T: {tail}
Source text:
{text}

Write ONE question for a question-answering test such that:
- it names H exactly as written above ("{head}");
- it asks for the thing that the source text links to H, i.e. normally T itself (not a type, description,
  year or other detail of it). If the text gives a different correct value than T, ask for the text's value;
- it does not contain the answer and does not mention T;
- it uses no pronoun (he, she, it, they, his, her...) for anyone or anything not named in the question;
- it is self-contained (never say "the text", "the sentence", "the passage").
The answer is the SHORTEST span copied word for word from the source text that names that thing:
an entity name, date or number, at most 5 words, without "'s" and without descriptive words.
Set "same_as_T" to true if your answer and T name the same thing (e.g. "American" and "United States",
"Wes Unseld" and "Westley Unseld"); otherwise false.
If the source text states no fact linking H and T, set "answerable" to false.
Reply with JSON only: {{"answerable": true, "question": "...", "answer": "...", "same_as_T": true}}"""
PRONOUN = re.compile(r"\b(he|she|his|her|him|they|their|them|it|its)\b", re.I)


def collect_writes(run_dir: Path):
    """Các cạnh agent ghi MỚI trong lượt chạy, kèm bản ghi cổng Construction (để lấy câu văn bằng chứng)."""
    gates = [g for g in read_jsonl(run_dir / "gates.jsonl") if g["kind"] == "construction"]
    index = {(g["episode_id"], g["write"]["head"], g["write"]["relation"], g["write"]["tail"]): g for g in gates}
    out = []
    for ep in read_jsonl(run_dir / "episodes.jsonl"):
        for w in ep["writes"]:
            if w["status"] != "added":
                continue
            g = index[(ep["episode_id"], w["head"], w["relation"], w["tail"])]
            out.append({"edge_id": w["edge_id"], "created_by": ep["episode_id"], "phase": w["phase"],
                        "write": g["write"], "evidence": g["evidence"]})
    return out


def source_sentences(item, corpus):
    """Câu văn nguồn: câu bằng chứng agent dẫn + câu nguồn của các cạnh bằng chứng; không có thì 3 câu đầu đoạn của đầu cạnh."""
    refs = []
    for v in item["evidence"]:
        if v["type"] == "sentence" and v.get("text"):
            refs.append((v["title"], v["sid"]))
        elif v["type"] == "edge":
            refs += [(s["title"], s["sid"]) for s in v["sentences"]]
    head = item["write"]["head"]
    if not refs and head in corpus:
        refs = [(head, i) for i in range(min(3, len(corpus[head])))]
    seen, sents = set(), []
    for t, i in refs:
        if (t, i) not in seen and t in corpus and i < len(corpus[t]):
            seen.add((t, i))
            sents.append({"title": t, "sid": i, "text": corpus[t][i].strip()})
    return sents


def check(p, head, text):
    if not isinstance(p, dict) or not p.get("answerable"):
        return "not_answerable"
    q, a = str(p.get("question") or ""), str(p.get("answer") or "")
    if not q.strip() or not normalize_answer(a):
        return "empty"
    if not agent_mod.in_question(head, q):
        return "head_not_in_question"
    if f" {normalize_answer(a)} " in f" {normalize_answer(q)} ":
        return "answer_in_question"
    if len(normalize_answer(a).split()) > 6:
        return "answer_too_long"
    if a.strip().endswith(("'s", "’s")):
        return "answer_possessive"
    m = PRONOUN.search(q)
    if m and m.start() < q.lower().find(head.lower().split()[0]):
        return "pronoun_before_head"
    if normalize_answer(a) not in normalize_answer(text):
        return "answer_not_in_text"
    return None


def gen_one(item, corpus, llm):
    from dcg.llm import parse_json

    sents = source_sentences(item, corpus)
    head, tail = strip_paren(item["write"]["head"]), item["write"]["tail"]
    rec = {"probe_id": f"p_{item['edge_id']}", **{k: item[k] for k in ("edge_id", "created_by", "phase", "write")},
           "source_sentences": sents, "question": None, "answer": None, "status": None}
    if not sents:
        rec["status"] = "no_source_text"
        return rec
    text = "\n".join(f"{k}. {s['text']}" for k, s in enumerate(sents, 1))
    msgs = [{"role": "system", "content": "You write test questions. Reply with JSON only."},
            {"role": "user", "content": PROMPT.format(head=head, tail=tail, text=text)}]
    for attempt in range(2):
        r = llm.chat(msgs, json_mode=True, session_id=f"probe:{item['edge_id']}")
        try:
            p = parse_json(r["content"])
        except ValueError:
            p, reason = None, "bad_json"
        else:
            reason = check(p, head, text)
        if reason is None:
            answers = [p["answer"].strip()]
            if p.get("same_as_T") is True and normalize_answer(tail) != normalize_answer(answers[0]):
                answers.append(tail)  # cách viết khác của cùng đáp án (vd. "American" / "United States")
            rec.update(question=p["question"].strip(), answer=p["answer"].strip(), answers=answers,
                       same_as_T=p.get("same_as_T"), status="ok", attempts=attempt + 1)
            return rec
        if reason == "not_answerable":
            break
        msgs += [{"role": "assistant", "content": r["content"] or ""},
                 {"role": "user", "content": f"Rejected ({reason}). Fix it and reply with JSON only."}]
    rec["status"] = reason
    return rec


def cmd_gen(args, llm):
    run_dir = Path(args.run)
    corpus = read_json(Path(args.graph).parent / "corpus.json")
    items = collect_writes(run_dir)
    with ThreadPoolExecutor(max(1, args.workers)) as ex:
        probes = list(ex.map(lambda it: gen_one(it, corpus, llm), items))
    from collections import Counter
    stats = dict(Counter(p["status"] for p in probes))
    write_json(run_dir / "probes.json", {"probe_version": PROBE_VERSION, "llm": getattr(llm, "info", lambda: {})(),
                                         "created": datetime.now().isoformat(timespec="seconds"),
                                         "stats": stats, "probes": probes})
    print(f"{len(items)} cạnh agent ghi mới → {stats}")
    ok = [p for p in probes if p["status"] == "ok"]
    print("\n20 câu mẫu để bạn kiểm tra (cạnh agent ghi | câu hỏi dò | đáp án theo văn bản):")
    for p in random.Random(0).sample(ok, min(20, len(ok))):
        w = p["write"]
        print(f"- [{p['edge_id']}] {w['head']} —{w['relation_name']}→ {w['tail']}\n    Q: {p['question']}\n    A: {' | '.join(p['answers'])}")
    return stats


def run_probe(p, cond, graph, corpus, llm, gates, rels, run_id):
    kg = KG.from_json(graph)
    ep = agent_mod.Episode(kg, {"_id": p["probe_id"], "context": []}, p["question"], llm, gates, rels, run_id,
                           f"{p['probe_id']}:{cond}", paragraphs=corpus)
    ep.memory = False
    res = ep.run()
    followed = [s["edge_id"] for s in ep.path if s["type"] == "follow"]
    res.update({"probe_id": p["probe_id"], "condition": cond, "probe_edge": p["edge_id"], "write": p["write"],
                "gold_answer": p["answer"], "gold_answers": p["answers"],
                "correct": any(contains_gold(res["answer"], g) for g in p["answers"]),
                "f1": f1(res["answer"], p["answer"]), "used_probe_edge": p["edge_id"] in followed,
                "saw_probe_edge": any(isinstance(e.get("result"), dict) and any(
                    x.get("edge_id") == p["edge_id"] for x in e["result"].get("edges", []) if isinstance(x, dict))
                    for e in ep.events)})
    return res, ep.gate_records


def cmd_run(args, llm):
    run_dir = Path(args.run)
    out = run_dir / "probe_run"
    if (out / "episodes.jsonl").exists():
        if not args.force:
            raise SystemExit(f"{out} đã có kết quả. Dùng --force để chạy lại (phản hồi đã có lấy từ cache).")
        for f in ("episodes.jsonl", "gates.jsonl"):
            (out / f).unlink(missing_ok=True)
    probes = [p for p in read_json(run_dir / "probes.json")["probes"] if p["status"] == "ok"][: args.limit]
    gdir = Path(args.graph).parent
    corpus = read_json(gdir / "corpus.json")
    graphs = {"before": read_json(args.graph), "after": read_json(run_dir / "graph_after.json")}
    rels, gates = load_relations(), GATES[args.gates]()
    run_id = f"{run_dir.name}-probe"
    write_json(out / "run.json", {"run_id": run_id, "started": datetime.now().isoformat(timespec="seconds"),
                                  "llm": getattr(llm, "info", lambda: {})(),
                                  "agent_prompt_version": agent_mod.PROMPT_VERSION, "gates": gates.name,
                                  "n_probes": len(probes), "graph_before": args.graph,
                                  "graph_after": str(run_dir / "graph_after.json")})
    jobs = [(p, c) for p in probes for c in ("before", "after")]
    done = [0]

    def one(job):
        r = run_probe(job[0], job[1], graphs[job[1]], corpus, llm, gates, rels, run_id)
        done[0] += 1
        if done[0] % 10 == 0 or done[0] == len(jobs):
            print(f"  [{done[0]}/{len(jobs)}]")
        return r

    with ThreadPoolExecutor(max(1, args.workers)) as ex:
        results = list(ex.map(one, jobs))
    rows = []
    for res, recs in results:  # ghi theo thứ tự cố định
        append_jsonl(out / "episodes.jsonl", res)
        for g in recs:
            append_jsonl(out / "gates.jsonl", g)
        rows.append(res)

    by = {(r["probe_id"], r["condition"]): r for r in rows}
    pairs = [(by[(p["probe_id"], "before")], by[(p["probe_id"], "after")]) for p in probes]
    n = len(pairs)
    used = [a for _, a in pairs if a["used_probe_edge"]]
    summary = {
        "n_probes": n,
        "correct_before": sum(b["correct"] for b, _ in pairs), "correct_after": sum(a["correct"] for _, a in pairs),
        "after_used_probe_edge": len(used), "after_saw_probe_edge": sum(a["saw_probe_edge"] for _, a in pairs),
        "after_used_probe_edge_correct": sum(a["correct"] for a in used),
        "both_correct": sum(b["correct"] and a["correct"] for b, a in pairs),
        "only_before_correct": sum(b["correct"] and not a["correct"] for b, a in pairs),
        "only_after_correct": sum(a["correct"] and not b["correct"] for b, a in pairs),
        "both_wrong": sum(not a["correct"] and not b["correct"] for b, a in pairs),
        "mean_follows_before": round(sum(b["follows"] for b, _ in pairs) / n, 2) if n else None,
        "mean_follows_after": round(sum(a["follows"] for _, a in pairs) / n, 2) if n else None,
        "llm_stats": getattr(llm, "stats", None),
    }
    write_json(out / "summary.json", summary)
    print("\nCâu dò mà kết quả trước/sau khác nhau:")
    for b, a in pairs:
        if b["correct"] != a["correct"]:
            w = a["write"]
            print(f"- {'HẠI' if b['correct'] else 'GIÚP'} [{a['probe_edge']}] {w['head']} —{w['relation_name']}→ {w['tail']}"
                  f" | đi qua cạnh: {a['used_probe_edge']}\n    Q: {a['question']}\n    đúng: {a['gold_answer']!r}"
                  f" | trước: {b['answer'][:80]!r} | sau: {a['answer'][:80]!r}")
    print("Tổng kết:", summary)
    return summary


def main(argv=None, llm=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["gen", "run"])
    ap.add_argument("--run", default=str(DATA / "runs" / "shared-v2"))
    ap.add_argument("--graph", default=str(DATA / "interim" / "shared" / "graph.json"),
                    help="đồ thị gốc (trước lượt chạy); corpus.json lấy cùng thư mục")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--gates", default="accept_all", choices=sorted(GATES))
    ap.add_argument("--limit", type=int)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    if llm is None:
        from dcg.llm import LLM
        llm = LLM()
    return cmd_gen(args, llm) if args.cmd == "gen" else cmd_run(args, llm)


if __name__ == "__main__":
    main()
