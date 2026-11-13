"""
自动错误归因（初分类）
基于规则 + 关键字匹配给每条失败题打标签
用户再校准
"""
import json, re
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
jsonl_path = ROOT / "data" / "biz_zh_50.jsonl"

MODELS = ["deepseek-flash", "glm-4.5-flash", "qwen-plus"]

# 加载题
questions = {}
for line in open(jsonl_path, encoding="utf-8"):
    if line.strip():
        item = json.loads(line)
        questions[item["id"]] = item


def classify_error(question, gold_sql, pred_sql, valid_sql, pred_error):
    """
    规则匹配打标签，返回列表
    """
    tags = []
    p = (pred_sql or "").lower()
    g = (gold_sql or "").lower()
    q = question
    
    # 1. JOIN 漏了
    if "join" in g and "join" not in p:
        tags.append("JOIN 漏了")
    
    # 2. GROUP BY 漏了
    if "group by" in g and "group by" not in p:
        tags.append("GROUP BY 漏了")
    
    # 3. 状态过滤错（gold 有 status，pred 没有）
    if "status" in g and "status" not in p:
        tags.append("状态过滤错")
    
    # 4. 时间条件错
    if "julianday" in g and "julianday" not in p:
        tags.append("时间差函数错")
    if "strftime" in g and "strftime" not in p:
        tags.append("日期分组函数错")
    if "substr" in g or "strftime" in g:
        if "month" in q or "月份" in q or "每月" in q or "日期" in q or "时间" in q:
            if "strftime" not in p and "substr" not in p:
                tags.append("时间条件错")
    
    # 5. CASE WHEN 错
    if "case when" in g and "case when" not in p:
        tags.append("CASE WHEN 漏了")
    
    # 6. 聚合字段错
    if "subtotal" in g and "subtotal" not in p and "total_amount" in p:
        tags.append("聚合字段错(total→subtotal)")
    
    # 7. 语法错误（valid_sql=False）
    if not valid_sql:
        err = (pred_error or "").lower()
        if "no such column" in err:
            tags.append("语法: 字段不存在")
        elif "near" in err:
            tags.append("语法: 关键字错误")
        elif "ambiguous" in err:
            tags.append("语法: 表别名歧义")
        else:
            tags.append("语法错误")
    
    # 8. 口径歧义（gold 很精确但 question 模糊）
    # 暂时标不出来，需要人工看
    
    if not tags:
        tags.append("逻辑推断错")
    
    return tags


# 汇总
rows = []
for qid in sorted(questions.keys()):
    q = questions[qid]
    gold = q["gold_sql"]
    for m in MODELS:
        f = RESULTS / f"{m}_{qid}.json"
        if not f.exists():
            continue
        r = json.loads(f.read_text(encoding="utf-8"))
        if r["ex"]:
            continue  # 答对的不用归因
        
        pred_sql = r["pred_sql"] or ""
        tags = classify_error(q["question"], gold, pred_sql, r["valid_sql"], r.get("pred_error"))
        
        rows.append({
            "id": qid,
            "model": m,
            "difficulty": q["difficulty"],
            "question": q["question"],
            "gold_sql": gold,
            "pred_sql": pred_sql[:400],
            "valid_sql": r["valid_sql"],
            "pred_error": r.get("pred_error"),
            "auto_tags": "; ".join(tags),
        })

df = pd.DataFrame(rows)

# 统计标签分布
print("=" * 70)
print("自动初分类标签分布")
print("=" * 70)
from collections import Counter
tag_counter = Counter()
for t in df["auto_tags"]:
    for tag in t.split("; "):
        if tag:
            tag_counter[tag] += 1
for tag, cnt in tag_counter.most_common():
    print(f"  {tag:30s}: {cnt:3d}")

# 按标签分组，给用户看代表题
print("\n--- 各标签代表题（每题只看一个模型）---")
seen = set()
for tag, cnt in tag_counter.most_common():
    print(f"\n【{tag}】共 {cnt} 次")
    sub = df[df["auto_tags"].str.contains(re.escape(tag))].head(3)
    for _, r in sub.iterrows():
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        print(f"  Q{r['id']:2d} [{r['difficulty']}] {r['question'][:60]}")
        print(f"    pred: {r['pred_sql'][:80]}...")
        if r['pred_error']:
            print(f"    err:  {str(r['pred_error'])[:60]}")

# 保存
df.to_excel(ROOT / "reports" / "error_attrition_raw.xlsx", index=False)
print(f"\n✅ 初分类结果已保存到 reports/error_attrition_raw.xlsx")
