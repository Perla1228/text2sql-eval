"""
错误归因汇总脚本
把三个模型 50 题的结果合并成一张 Excel，方便标注
"""
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"

MODELS = ["deepseek-flash", "glm-4.5-flash", "qwen-plus"]

# 加载每道题的 gold_sql
jsonl_path = ROOT / "data" / "biz_zh_50.jsonl"
questions = {}
for line in open(jsonl_path, encoding="utf-8"):
    if line.strip():
        item = json.loads(line)
        questions[item["id"]] = item

# 汇总：每道题 × 每个模型
rows = []
for qid in sorted(questions.keys()):
    q = questions[qid]
    row = {
        "id": qid,
        "difficulty": q["difficulty"],
        "question": q["question"],
        "gold_sql": q["gold_sql"],
    }
    for m in MODELS:
        f = RESULTS / f"{m}_{qid}.json"
        if f.exists():
            r = json.loads(f.read_text(encoding="utf-8"))
            row[f"{m}_valid"] = r["valid_sql"]
            row[f"{m}_ex"] = r["ex"]
            row[f"{m}_pred_sql"] = r["pred_sql"][:300] if r["pred_sql"] else ""
            row[f"{m}_error"] = r["pred_error"] if not r["valid_sql"] else None
        else:
            row[f"{m}_valid"] = None
            row[f"{m}_ex"] = None
            row[f"{m}_pred_sql"] = ""
            row[f"{m}_error"] = None
    rows.append(row)

df = pd.DataFrame(rows)

# 统计概览
print("=" * 70)
print("三模型汇总概览")
print("=" * 70)
for m in MODELS:
    total = len(df)
    valid = df[f"{m}_valid"].sum()
    ex = df[f"{m}_ex"].sum()
    print(f"{m:20s}: Valid={valid}/{total}={valid/total*100:.0f}%  EX={ex}/{total}={ex/total*100:.0f}%")

print("\n--- 三模型全挂的题（最难）---")
all_fail = df[(df["deepseek-flash_ex"] == False) & 
              (df["glm-4.5-flash_ex"] == False) & 
              (df["qwen-plus_ex"] == False)]
print(f"共 {len(all_fail)} 题")
for _, r in all_fail.iterrows():
    print(f"  Q{r['id']:2d} [{r['difficulty']}] {r['question'][:50]}")

print("\n--- 至少两个模型答对的题（较易）---")
two_pass = df[(df["deepseek-flash_ex"] == True).astype(int) + 
              (df["glm-4.5-flash_ex"] == True).astype(int) + 
              (df["qwen-plus_ex"] == True).astype(int) >= 2]
print(f"共 {len(two_pass)} 题")

# 保存 Excel（去掉 pred_sql 太长的列）
df_out = df.drop(columns=[f"{m}_pred_sql" for m in MODELS])
df_out.to_excel(ROOT / "reports" / "error_attrition_summary.xlsx", index=False)
print(f"\n✅ 汇总表已保存到 reports/error_attrition_summary.xlsx")
