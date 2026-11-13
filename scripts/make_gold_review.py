"""生成 gold_sql 修复复核表：每条修复的原因、原 SQL、新 SQL、执行结果预览"""
import json
import sqlite3
from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from gold_fixes import FIXES, REASONS

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "biz_ecommerce.sqlite"
REPORTS = ROOT / "reports"
JSONL = ROOT / "data" / "biz_zh_50.jsonl"

questions = {q["id"]: q for q in (json.loads(l) for l in open(JSONL, encoding="utf-8") if l.strip())}
old_gold = pd.read_excel(REPORTS / "error_attrition_summary.xlsx").set_index("id")["gold_sql"].to_dict()

conn = sqlite3.connect(DB)
cur = conn.cursor()

rows = []
for qid in sorted(FIXES):
    q = questions[qid]
    cur.execute(FIXES[qid])
    res = cur.fetchall()
    preview = "\n".join(str(r) for r in res[:3])
    rows.append({
        "题号": qid,
        "难度": q["difficulty"],
        "问题": q["question"],
        "修改类型": REASONS[qid][0],
        "修改原因": REASONS[qid][1],
        "原 SQL（有问题）": str(old_gold.get(qid, "")),
        "新 SQL": FIXES[qid],
        "结果行数": len(res),
        "结果预览（前 3 行）": preview,
        "复核结论（对/错）": "",
        "备注": "",
    })
conn.close()

df = pd.DataFrame(rows)
out = REPORTS / "gold_sql_review.xlsx"

with pd.ExcelWriter(out, engine="openpyxl") as writer:
    df.to_excel(writer, index=False, sheet_name="gold修复复核")
    ws = writer.sheets["gold修复复核"]

    widths = {"A": 7, "B": 9, "C": 30, "D": 20, "E": 50, "F": 55, "G": 55, "H": 9, "I": 30, "J": 12, "K": 18}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w

    for c in range(1, len(df.columns) + 1):
        cell = ws.cell(row=1, column=c)
        cell.font = Font(bold=True, color="FFFFFF", size=11)
        cell.fill = PatternFill("solid", fgColor="1F2937")
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for i in range(2, len(df) + 2):
        for c in range(1, len(df.columns) + 1):
            cell = ws.cell(row=i, column=c)
            cell.alignment = Alignment(vertical="top", horizontal="left", wrap_text=True)
            cell.fill = PatternFill("solid", fgColor="FFFFFF" if i % 2 else "F5F7FB")
        ws.row_dimensions[i].height = 92

    ws.freeze_panes = "C2"

print(f"共 {len(df)} 条修复，复核表已生成：{out}")
