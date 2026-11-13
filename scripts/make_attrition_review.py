"""生成人工复核用的失败样本明细表

输出 reports/error_attrition_review.xlsx，每行一条「模型 × 失败题」，
带 gold_sql / pred_sql / 实际执行结果行列数，方便逐条核对自动归因标签是否正确。
"""
import json
import sqlite3
from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"
DB = ROOT / "data" / "biz_ecommerce.sqlite"

# 自动标签的展示顺序（从多到少，按业务含义排）
TAG_ORDER = [
    "空输出",
    "口径: 返回列数不同",
    "口径: 漏了 DISTINCT",
    "逻辑推断差(同表同字段但口径对不上)",
    "聚合字段: subtotal→total_amount",
    "聚合字段: total_amount→subtotal",
    "状态过滤漏了",
    "JOIN 漏了",
    "GROUP BY 漏了",
]


def tag_bucket(tags: str) -> str:
    """把明细标签归到上面的大类，用于排序分组"""
    for i, t in enumerate(TAG_ORDER):
        if t in tags:
            return f"{i}_{t}"
    return f"99_其他"


def run_sql(conn, sql):
    """执行一条 SQL，返回 (列数, 行数, 报错)"""
    if not sql:
        return None, None, "empty_sql"
    try:
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        return len(rows[0]) if rows else len(cur.description or []), len(rows), ""
    except Exception as e:
        return None, None, str(e)[:120]


raw = pd.read_excel(REPORTS / "error_attrition_raw.xlsx")
final = pd.read_excel(REPORTS / "error_attrition_final.xlsx")

# raw 与 final 行序一致（同一批 96 条），合并 gold_sql/pred_sql 与最终标签
df = raw[["id", "model", "difficulty", "question", "gold_sql", "pred_sql", "valid_sql", "pred_error"]].copy()
df["自动标签"] = final["tags"].values
df["标签大类"] = df["自动标签"].map(tag_bucket)

conn = sqlite3.connect(DB)
gold_info, pred_info = [], []
for _, r in df.iterrows():
    g_cols, g_rows, g_err = run_sql(conn, r["gold_sql"])
    p_cols, p_rows, p_err = run_sql(conn, r["pred_sql"])
    gold_info.append(f"{g_cols}列/{g_rows}行")
    pred_info.append(f"{p_cols}列/{p_rows}行" if not p_err else "执行失败")
conn.close()

df["gold 结果"] = gold_info
df["pred 结果"] = pred_info
df["人工判定是否合理"] = ""   # 留空，供人工填「对 / 错」
df["正确标签(如需改)"] = ""
df["备注"] = ""

df = df.sort_values(["标签大类", "id", "model"]).reset_index(drop=True)
buckets = df["标签大类"].tolist()   # 保留分组信息用于上色（后面会从 df 里删掉这一列）
df = df[["id", "model", "difficulty", "question", "自动标签", "gold 结果", "pred 结果",
         "gold_sql", "pred_sql", "pred_error", "人工判定是否合理", "正确标签(如需改)", "备注"]]

out = REPORTS / "error_attrition_review.xlsx"
with pd.ExcelWriter(out, engine="openpyxl") as writer:
    df.to_excel(writer, index=False, sheet_name="失败样本复核")
    ws = writer.sheets["失败样本复核"]

    widths = {"A": 6, "B": 16, "C": 10, "D": 42, "E": 30, "F": 11, "G": 11,
              "H": 55, "I": 55, "J": 22, "K": 14, "L": 20, "M": 18}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w

    header_fill = PatternFill("solid", fgColor="1F2937")
    for c in range(1, len(df.columns) + 1):
        cell = ws.cell(row=1, column=c)
        cell.font = Font(bold=True, color="FFFFFF", size=11)
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")

    # 同标签分组之间加分隔底色，方便连续检查
    group_colors = ["FFF4F4", "F4F8FF", "F3FBF6"]
    prev = None
    color_idx = 0
    for i in range(2, len(df) + 2):
        bucket = buckets[i - 2]
        if bucket != prev:
            color_idx = (color_idx + 1) % len(group_colors)
            prev = bucket
        fill = PatternFill("solid", fgColor=group_colors[color_idx])
        for c in range(1, len(df.columns) + 1):
            ws.cell(row=i, column=c).fill = fill
            ws.cell(row=i, column=c).alignment = Alignment(
                vertical="top", horizontal="left", wrap_text=True)

    for row in range(2, len(df) + 2):
        ws.row_dimensions[row].height = 64

    ws.freeze_panes = "A2"

print("=" * 60)
print(f"失败样本 {len(df)} 条，按标签分组：")
for b in sorted(set(buckets)):
    print(f"  {b[2:] if b[:2].isdigit() else b:34s} {buckets.count(b)} 条")
print(f"\n✅ 已生成 {out}")
