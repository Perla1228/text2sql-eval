"""
把 data/biz_zh_50.xlsx 转成 data/biz_zh_50.jsonl（EvalScope 能用的格式）

每行一个 JSON 对象，字段：
{
  "id": 1,
  "db_id": "biz_ecommerce",
  "question": "30岁以下的女性用户有多少",
  "gold_sql": "SELECT ...",
  "difficulty": "easy",
  "tags": ["过滤"],
  "notes": "",
  "db_path": "data/biz_ecommerce.sqlite"   # ← 新增，adapter 用这个找库
}
"""

import json
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
XLSX = ROOT / "data" / "biz_zh_50.xlsx"
JSONL = ROOT / "data" / "biz_zh_50.jsonl"

df = pd.read_excel(XLSX)

count = 0
with open(JSONL, "w", encoding="utf-8") as f:
    for _, row in df.iterrows():
        # tags 从字符串转成数组（Excel 里是逗号分隔的字符串）
        tags_str = str(row.get("tags", "")).strip()
        tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []

        notes = str(row.get("notes", "")).strip()
        if notes in ("nan", "None", ""):
            notes = ""

        obj = {
            "id": int(row["id"]),
            "db_id": str(row.get("db_id", "biz_ecommerce")),
            "question": str(row["question"]).strip(),
            "gold_sql": str(row["gold_sql"]).strip(),
            "difficulty": str(row["difficulty"]).strip(),
            "tags": tags,
            "notes": notes,
            "db_path": "data/biz_ecommerce.sqlite",
        }
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        count += 1

print(f"✅ 转换完成：{count} 题 → {JSONL}")
print(f"   难度分布：easy={len(df[df.difficulty=='easy'])}, "
      f"medium={len(df[df.difficulty=='medium'])}, "
      f"hard={len(df[df.difficulty=='hard'])}")
