"""把 gold_fixes.py 里的修复清单写回 Excel 与 JSONL

用法：
  python scripts/fix_gold_sql.py            # 只验证，不写文件
  python scripts/fix_gold_sql.py --write    # 验证通过后写回
"""
import json
import sqlite3
import sys
from pathlib import Path

from gold_fixes import FIXES

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "biz_ecommerce.sqlite"
JSONL = ROOT / "data" / "biz_zh_50.jsonl"
XLSX = ROOT / "data" / "biz_zh_50.xlsx"

WRITE = "--write" in sys.argv

conn = sqlite3.connect(DB)
cur = conn.cursor()

questions = [json.loads(l) for l in open(JSONL, encoding="utf-8") if l.strip()]

ok = True
print("=" * 72)
print(f"共 {len(FIXES)} 处修复，逐条执行验证")
print("=" * 72)
for qid, sql in sorted(FIXES.items()):
    q = next(x for x in questions if x["id"] == qid)
    try:
        cur.execute(sql)
        rows = cur.fetchall()
        print(f"\nQ{qid} {q['question']}\n  → {len(rows)} 行，首行: {rows[0] if rows else None}")
    except Exception as e:
        ok = False
        print(f"\nQ{qid} ❌ 执行失败: {e}")

conn.close()

if not ok:
    print("\n存在执行失败的修复，已中止，未写文件。")
    sys.exit(1)

if not WRITE:
    print("\n验证通过。加 --write 才会写回 Excel 和 JSONL。")
    sys.exit(0)

for q in questions:
    if q["id"] in FIXES:
        q["gold_sql"] = FIXES[q["id"]]
with open(JSONL, "w", encoding="utf-8") as f:
    for q in questions:
        f.write(json.dumps(q, ensure_ascii=False) + "\n")

from openpyxl import load_workbook

wb = load_workbook(XLSX)
ws = wb["Sheet1"]
headers = [c.value for c in ws[1]]
col_id = headers.index("id") + 1
col_gold = headers.index("gold_sql") + 1
for row in range(2, ws.max_row + 1):
    qid = ws.cell(row=row, column=col_id).value
    if qid in FIXES:
        ws.cell(row=row, column=col_gold).value = FIXES[qid]
wb.save(XLSX)

print(f"\n✅ 已写回：{XLSX} 与 {JSONL}")
