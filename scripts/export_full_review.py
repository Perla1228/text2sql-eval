"""导出完整「全题 × 全模型」对照表，方便人工逐条核对 SQL

输出：reports/full_sql_review.xlsx
  Sheet1 全题对照（加强提示，150 行 = 50题 × 3模型）
  Sheet2 仅失败（65 行，方便聚焦）
  Sheet3 仅通过（85 行，作对照）
"""
from pathlib import Path
import sqlite3
import sys

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"
sys.path.insert(0, str(ROOT / "scripts"))
import run_eval

# ---------- 数据 ----------
scores = pd.read_excel(REPORTS / "model_scores.xlsx")
attr = pd.read_excel(REPORTS / "error_attrition_final.xlsx")

# 只用加强版 + 未缺失
enh = scores[(scores["prompt"] == "enhanced") & (~scores["missing"])].copy()

conn = sqlite3.connect(ROOT / "data" / "biz_ecommerce.sqlite")
def fmt_result(sql):
    if pd.isna(sql) or not str(sql).strip():
        return "(空)"
    ok, res = run_eval.execute_sql(conn, str(sql))
    if ok and res:
        return f"{len(res)}行/{len(res[0])}列"
    return "(执行失败)"

# 直接用 model_scores 里的 gold_sql / pred_sql（gold 已修正 19 条）
out = enh[["id", "difficulty", "question", "gold_sql", "model", "pred_sql",
           "valid_sql", "ex", "ex_answer", "pred_error"]].copy()
out["gold 结果"] = out["gold_sql"].apply(fmt_result)
out["pred 结果"] = out["pred_sql"].apply(fmt_result)
conn.close()

# 补标签（通过题标签空着）
out = out.merge(
    attr[["id", "model", "tags"]].rename(columns={"tags": "标签"}),
    on=["id", "model"], how="left",
)

MODEL_ORDER = ["glm-4.5-flash", "deepseek-flash", "qwen-plus"]
out["model"] = pd.Categorical(out["model"], categories=MODEL_ORDER, ordered=True)
out = out.sort_values(["id", "model"])

# 重命名列（SQL 列保持原名方便 grep）
out = out.rename(columns={
    "id": "题号",
    "difficulty": "难度",
    "question": "问题",
    "model": "模型",
    "valid_sql": "SQL可执行",
    "ex": "严格EX",
    "ex_answer": "等价EX",
    "pred_error": "执行报错",
})
# 调整列顺序
out = out[["题号", "难度", "问题",
           "gold_sql", "gold 结果",
           "模型", "pred_sql", "pred 结果",
           "SQL可执行", "严格EX", "等价EX", "标签", "执行报错"]]

fail = out[out["等价EX"] != True].copy()
pass_ = out[out["等价EX"] == True].copy()

# ---------- 写 Excel ----------
xlsx = REPORTS / "full_sql_review.xlsx"
with pd.ExcelWriter(xlsx, engine="openpyxl") as w:
    out.to_excel(w, sheet_name="全题对照", index=False)
    fail.to_excel(w, sheet_name="仅失败", index=False)
    pass_.to_excel(w, sheet_name="仅通过", index=False)

    head_fill = PatternFill("solid", fgColor="DCE6F5")
    fail_fill = PatternFill("solid", fgColor="FADBD8")
    pass_fill = PatternFill("solid", fgColor="D5F5E3")
    bold = Font(bold=True)

    widths = {"题号": 6, "难度": 7, "问题": 36,
              "gold_sql": 72, "gold 结果": 14,
              "模型": 16, "pred_sql": 72, "pred 结果": 14,
              "SQL可执行": 10, "严格EX": 8, "等价EX": 8,
              "标签": 48, "执行报错": 30}

    for sheet_name, df_sheet, row_fill in [
        ("全题对照", out, None),
        ("仅失败", fail, fail_fill),
        ("仅通过", pass_, pass_fill),
    ]:
        ws = w.sheets[sheet_name]
        # 表头
        for c in ws[1]:
            c.fill = head_fill
            c.font = bold
            c.alignment = Alignment(horizontal="center", vertical="center")
        # 列宽
        for col, wd in widths.items():
            if col in df_sheet.columns:
                ws.column_dimensions[get_column_letter(list(df_sheet.columns).index(col) + 1)].width = wd
        # 数据行底色
        ex_col_idx = list(df_sheet.columns).index("等价EX") + 1
        for row in ws.iter_rows(min_row=2):
            if row_fill is not None:
                for c in row:
                    c.fill = row_fill
            else:
                is_pass = row[ex_col_idx - 1].value is True
                for c in row:
                    c.fill = pass_fill if is_pass else fail_fill
            for c in row:
                c.alignment = Alignment(vertical="top", wrap_text=True)
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        ws.row_dimensions[1].height = 26

print(f"✅ 已生成 {xlsx}")
print(f"  全题对照: {len(out)} 行（50题 × 3模型）")
print(f"  仅失败:   {len(fail)} 行")
print(f"  仅通过:   {len(pass_)} 行")
print()
print("前3行预览（截断 SQL）：")
preview = out[["题号", "难度", "问题", "gold 结果", "模型", "pred 结果",
               "SQL可执行", "严格EX", "等价EX"]].head(3)
print(preview.to_string(index=False))
