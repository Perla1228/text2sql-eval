"""重新打分：把旧缓存按「修正后的 gold_sql + 答案等价口径」重算，不调用 API

产出：
  results/*.json            每道题补上 ex_answer 字段（严格 EX 保留为 ex）
  reports/model_scores.xlsx 统一的逐题评分表（三模型 × 提示档）
"""
import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import run_eval  # noqa: E402

RESULTS = ROOT / "results"
REPORTS = ROOT / "reports"
DB = ROOT / "data" / "biz_ecommerce.sqlite"
JSONL = ROOT / "data" / "biz_zh_50.jsonl"

questions = {q["id"]: q for q in (json.loads(l) for l in open(JSONL, encoding="utf-8") if l.strip())}
conn = sqlite3.connect(DB)
maps = run_eval.build_id_name_maps(conn)

rows = []


def score_from_cache(model):
    """读该模型缓存逐题重算，并把 ex_answer 写回缓存文件"""
    for f in sorted(RESULTS.glob(f"{model}_*.json")):
        rec = json.loads(f.read_text(encoding="utf-8"))
        q = questions[rec["id"]]
        m = run_eval.compute_metrics(rec["pred_sql"], q["gold_sql"], conn, maps)

        rec.update({k: m[k] for k in ("valid_sql", "em", "ex", "ex_answer")})
        f.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")

        rows.append({
            "model": model,
            "prompt": "simple" if "_simple_" in f.name else "enhanced",
            "id": rec["id"],
            "difficulty": q["difficulty"],
            "question": q["question"],
            "gold_sql": q["gold_sql"],
            "pred_sql": rec["pred_sql"],
            "valid_sql": m["valid_sql"],
            "ex": m["ex"],
            "ex_answer": m["ex_answer"],
            "pred_error": m["pred_error"],
            # 空输出是接口超时/限流导致的缺失数据，不计入分母
            "missing": not rec["pred_sql"],
        })


for model in ["glm-4.5-flash", "deepseek-flash", "qwen-plus"]:
    score_from_cache(model)

# 兼容：qwen 若仍无缓存，则从历史明细表反推（仅供参考，报告会标注）
if not any(r["model"] == "qwen-plus" for r in rows):
    raw = pd.read_excel(REPORTS / "error_attrition_raw.xlsx")
    pred_by_id = {int(r["id"]): r["pred_sql"] for _, r in raw[raw["model"] == "qwen-plus"].iterrows()}
    summary = pd.read_excel(REPORTS / "error_attrition_summary.xlsx").set_index("id")

    for qid, q in sorted(questions.items()):
        pred = pred_by_id.get(qid)
        if pred:
            m = run_eval.compute_metrics(pred, q["gold_sql"], conn, maps)
            valid, ex, exa, err = m["valid_sql"], m["ex"], m["ex_answer"], m["pred_error"]
        else:
            valid = bool(summary.loc[qid, "qwen-plus_valid"])
            ex = exa = bool(summary.loc[qid, "qwen-plus_ex"])
            err = None
        rows.append({
            "model": "qwen-plus", "prompt": "enhanced", "id": qid,
            "difficulty": q["difficulty"], "question": q["question"],
            "gold_sql": q["gold_sql"], "pred_sql": pred or "",
            "valid_sql": valid, "ex": ex, "ex_answer": exa, "pred_error": err,
            "missing": False,
        })

conn.close()

df = pd.DataFrame(rows)
df.to_excel(REPORTS / "model_scores.xlsx", index=False)

print("=" * 68)
print("重新打分结果（加强提示，已排除接口失败的空输出）")
print("=" * 68)
print(f"{'模型':<20}{'有效题数':>8}{'Valid':>8}{'严格EX':>10}{'答案等价EX':>12}")
for model in ["glm-4.5-flash", "deepseek-flash", "qwen-plus"]:
    sub = df[(df.model == model) & (df.prompt == "enhanced") & (~df.missing)]
    n = len(sub)
    print(f"{model:<20}{n:>8}{sub.valid_sql.sum()/n*100:>7.1f}%{sub.ex.sum()/n*100:>9.1f}%{sub.ex_answer.sum()/n*100:>11.1f}%")

print("\n分难度（答案等价 EX）：")
for model in ["glm-4.5-flash", "deepseek-flash", "qwen-plus"]:
    sub = df[(df.model == model) & (df.prompt == "enhanced") & (~df.missing)]
    parts = [f"{d} {sub[sub.difficulty==d].ex_answer.sum()}/{len(sub[sub.difficulty==d])}"
             f"={sub[sub.difficulty==d].ex_answer.mean()*100:.0f}%" for d in ["easy", "medium", "hard"]]
    print(f"  {model:<20} " + "  ".join(parts))

print("\n消融（答案等价 EX）：")
for model in ["glm-4.5-flash", "deepseek-flash"]:
    parts = []
    for p in ["simple", "enhanced"]:
        s = df[(df.model == model) & (df.prompt == p) & (~df.missing)]
        parts.append(f"{p}={s.ex_answer.mean()*100:.0f}%(n={len(s)})" if len(s) else f"{p}=—")
    print(f"  {model:<20} " + "  ".join(parts))

print(f"\n✅ 已保存 {REPORTS / 'model_scores.xlsx'}")
