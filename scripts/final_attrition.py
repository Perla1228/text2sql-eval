"""
完整错误归因 v2：用实际执行结果判标签，不数 SQL 逗号

- pred_cols > gold_cols → 多列（等价 EX 会过，严格 EX 才错）
- pred_cols < gold_cols → 缺列（真错误）
- 行数不同 → 过滤 / 分组 / JOIN 问题
- 列数相同、行数相同但值不同 → 逻辑推断差
"""
import json
import re
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
DB = ROOT / "data" / "biz_ecommerce.sqlite"
JSONL = ROOT / "data" / "biz_zh_50.jsonl"
import sys
sys.path.insert(0, str(ROOT / "scripts"))
import run_eval  # noqa: E402

MODELS = ["deepseek-flash", "glm-4.5-flash", "qwen-plus"]

conn = sqlite3.connect(DB)
maps = run_eval.build_id_name_maps(conn)

questions = {q["id"]: q for q in (json.loads(l) for l in open(JSONL, encoding="utf-8") if l.strip())}


def get_used_tables(sql):
    sql_u = (sql or "").upper()
    tables = set()
    for t in ["USERS", "REGIONS", "CHANNELS", "CATEGORIES", "PRODUCTS", "ORDERS", "ORDER_ITEMS", "REFUNDS"]:
        if re.search(rf'\b(?:FROM|JOIN)\s+{t}\b', sql_u):
            tables.add(t.lower())
    return tables


def classify(qid, question, gold_sql, pred_sql, valid_sql, pred_error):
    """基于实际执行结果 + SQL 结构双重判标签"""
    tags = []
    p = (pred_sql or "").lower()
    g = (gold_sql or "").lower()
    p_tables = get_used_tables(pred_sql)
    g_tables = get_used_tables(gold_sql)

    # 1) Valid SQL=False：语法类直接归
    if not valid_sql:
        err = str(pred_error or "").lower()
        if "no such column" in err:
            return ["语法: 字段不存在"]
        if "near" in err:
            return ["语法: 关键字错误"]
        if "ambiguous" in err:
            return ["语法: 表别名歧义"]
        if "empty_sql" in err or not pred_sql:
            return ["空输出"]
        return [f"语法错误: {str(pred_error)[:40]}"]

    # 2) Valid SQL=True 但 ex_answer=False：拿到实际执行结果
    pred_ok, pred_res = run_eval.execute_sql(conn, pred_sql)
    gold_ok, gold_res = run_eval.execute_sql(conn, gold_sql)
    if not pred_ok or not gold_ok:
        return ["执行异常(但 valid_sql=True)"]

    p_cols = len(pred_res[0]) if pred_res else 0
    g_cols = len(gold_res[0]) if gold_res else 0
    p_rows = len(pred_res)
    g_rows = len(gold_res)

    # 3) 多列：模型多返回了辅助列（严格 EX 判错、等价 EX 应判对）
    if p_cols > g_cols:
        tags.append("多列（辅助列 / 口径等价，严格 EX 误判）")

    # 4) 缺列：真错误
    if p_cols < g_cols:
        tags.append("缺列（模型未返回完整答案）")

    # 5) 行数不同：分组粒度 / 过滤条件 / JOIN 问题
    if p_rows != g_rows:
        missing_tables = g_tables - p_tables
        if missing_tables:
            tags.append(f"JOIN 漏了: {','.join(sorted(missing_tables))}")
        if "group by" in g and "group by" not in p:
            tags.append("GROUP BY 漏了")
        if "having" in g and "having" not in p:
            tags.append("HAVING 漏了")
        if "status" in g and "status" not in p:
            tags.append("状态过滤漏了")
        if not any("JOIN 漏了" in t or "GROUP BY 漏了" in t or "状态过滤漏了" in t or "HAVING 漏了" in t for t in tags):
            tags.append(f"行数不同({g_rows}→{p_rows})，聚合粒度或过滤条件问题")

    # 6) 行数相同但值不同：聚合口径 / DISTINCT / CASE
    if p_rows == g_rows and (not tags or all("多列" in t or "缺列" in t for t in tags)):
        if "subtotal" in g and "subtotal" not in p and "total_amount" in p:
            tags.append("聚合字段: total_amount→subtotal")
        if "total_amount" in g and "total_amount" not in p and "subtotal" in p:
            tags.append("聚合字段: subtotal→total_amount")
        if "distinct" in g and "distinct" not in p:
            tags.append("口径: 漏了 DISTINCT")
        if "case" in g and "case" not in p:
            tags.append("CASE WHEN 漏了")
        if "julianday" in g and "julianday" not in p:
            tags.append("时间差: 没用 julianday")
        if "strftime" in g and "strftime" not in p:
            tags.append("日期分组: 没用 strftime")

    # 7) 兜底
    if not tags:
        tags = ["逻辑推断差(同表同字段但值对不上)"]

    return tags


# === 读评分表 ===
scores = pd.read_excel(ROOT / "reports" / "model_scores.xlsx")
scores = scores[scores["prompt"] == "enhanced"]
scores = scores[~scores["missing"]]

all_rows = []
for _, r in scores.iterrows():
    if bool(r["ex_answer"]):
        continue
    tags = classify(
        int(r["id"]), r["question"], r["gold_sql"], r["pred_sql"] or "",
        bool(r["valid_sql"]),
        r["pred_error"] if isinstance(r["pred_error"], str) else "",
    )
    pred_ok, pred_res = run_eval.execute_sql(conn, r["pred_sql"] or "")
    gold_ok, gold_res = run_eval.execute_sql(conn, r["gold_sql"])
    all_rows.append({
        "id": int(r["id"]),
        "model": r["model"],
        "difficulty": r["difficulty"],
        "question": r["question"],
        "tags": "; ".join(tags),
        "gold_sql": r["gold_sql"],
        "pred_sql": r["pred_sql"],
        "gold 结果": f"{len(gold_res) if gold_ok else '?'}行/{len(gold_res[0]) if gold_ok and gold_res else 0}列",
        "pred 结果": f"{len(pred_res) if pred_ok else '?'}行/{len(pred_res[0]) if pred_ok and pred_res else 0}列",
        "valid_sql": bool(r["valid_sql"]),
        "pred_error": r["pred_error"] if isinstance(r["pred_error"], str) else "",
        "ex": bool(r["ex"]),
        "ex_answer": bool(r["ex_answer"]),
    })

conn.close()
df = pd.DataFrame(all_rows)

# === 汇总 ===
from collections import Counter
print("=" * 72)
print(f"三模型失败题标签分布（答案等价 EX，总失败 {len(df)}）")
print("=" * 72)
tag_counter = Counter()
for t in df["tags"]:
    for tag in t.split("; "):
        tag_counter[tag] += 1
total_fail = len(df)
for tag, cnt in tag_counter.most_common():
    pct = cnt / total_fail * 100
    bar = "█" * int(pct / 2)
    print(f"  {tag:36s} {cnt:3d}次  ({pct:4.0f}%)  {bar}")

df.to_excel(ROOT / "reports" / "error_attrition_final.xlsx", index=False)
print(f"\n✅ 已保存 reports/error_attrition_final.xlsx")
