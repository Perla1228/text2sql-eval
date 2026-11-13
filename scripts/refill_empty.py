"""补跑缓存里的空输出（API 失败导致 pred_sql 为空），可选补齐整个模型

用法：
  python scripts/refill_empty.py                 # 只补 glm/deepseek 的空输出
  python scripts/refill_empty.py --with-qwen     # 额外跑 qwen-plus 全量加强提示
"""
import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import run_eval  # noqa: E402

RESULTS = ROOT / "results"
JSONL = ROOT / "data" / "biz_zh_50.jsonl"
DB = ROOT / "data" / "biz_ecommerce.sqlite"
SCHEMA = ROOT / "data" / "schema_prompt.txt"

questions = {q["id"]: q for q in (json.loads(l) for l in open(JSONL, encoding="utf-8") if l.strip())}
schema_text = SCHEMA.read_text(encoding="utf-8")
conn = sqlite3.connect(DB)
maps = run_eval.build_id_name_maps(conn)


def cache_files(model, prompt):
    files = list(RESULTS.glob(f"{model}_*.json"))
    if prompt == "simple":
        return [f for f in files if "_simple_" in f.name]
    return [f for f in files if "_simple_" not in f.name]


def refill(model, prompt, only_empty):
    key = run_eval._auto_key_for_model(model, "")
    url = run_eval._auto_url_for_model(model, "")
    if not key:
        print(f"❌ {model}: 没找到 API key")
        return

    targets = []
    for f in cache_files(model, prompt):
        rec = json.loads(f.read_text(encoding="utf-8"))
        if only_empty and rec.get("pred_sql"):
            continue
        targets.append((f, rec))

    # 缓存完全不存在时（如 qwen），按题号整批跑
    if not targets and not only_empty:
        targets = [
            (RESULTS / f"{model}_{qid}.json", {"id": qid})
            for qid in sorted(questions)
            if not (RESULTS / f"{model}_{qid}.json").exists()
        ]

    print(f"\n{model} | {prompt}: 需要补跑 {len(targets)} 题")
    for i, (f, rec) in enumerate(targets, 1):
        q = questions[rec["id"]]
        prompt_text = run_eval.build_prompt(schema_text, q["question"], prompt == "enhanced")

        raw, pred = "", ""
        for attempt in range(1, 4):
            raw = run_eval.call_chat_api(model, url, key, prompt_text)
            pred = run_eval.extract_sql(raw)
            if pred:
                break
            print(f"  Q{q['id']} 第 {attempt} 次返回空，{20 * attempt}s 后重试")
            time.sleep(20 * attempt)

        if not pred:
            print(f"  [{i}/{len(targets)}] Q{q['id']} ⚠ 3 次均为空，保留原缓存")
            continue

        metrics = run_eval.compute_metrics(pred, q["gold_sql"], conn, maps)

        record = {
            "id": q["id"],
            "difficulty": q["difficulty"],
            "question": q["question"],
            "gold_sql": q["gold_sql"],
            "raw_output": raw,
            **metrics,
        }
        f.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  [{i}/{len(targets)}] Q{q['id']} EX={'✅' if metrics['ex_answer'] else '❌'}")
        time.sleep(2)


if "--model" in sys.argv:
    # 只补指定模型：--model glm-4.5-flash [--prompt enhanced|simple]
    _m = sys.argv[sys.argv.index("--model") + 1]
    _p = "enhanced"
    if "--prompt" in sys.argv:
        _p = sys.argv[sys.argv.index("--prompt") + 1]
    refill(_m, _p, only_empty=True)
elif "--only-qwen" not in sys.argv:
    refill("glm-4.5-flash", "simple", only_empty=True)
    refill("glm-4.5-flash", "enhanced", only_empty=True)
    refill("deepseek-flash", "simple", only_empty=True)
    refill("deepseek-flash", "enhanced", only_empty=True)

if "--with-qwen" in sys.argv:
    refill("qwen-plus", "enhanced", only_empty=False)

conn.close()
print("\n✅ 补跑完成，接着跑 scripts/rescore.py 重新打分")
