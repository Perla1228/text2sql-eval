"""生成「模型 × 错误类型」交叉表 + 逐条明细的 Excel，供人工复核

输出：reports/error_attrition_by_model.xlsx
  Sheet1 模型×错误类型   ：每个标签在每个模型上出现多少次（按主标签统计，合计=失败题数）
  Sheet2 失败明细        ：一条失败一行，含主标签 / 全部标签 / 结果行列数 / SQL
  Sheet3 标签汇总        ：全局标签分布与占比
"""
from collections import Counter, OrderedDict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"

df = pd.read_excel(REPORTS / "error_attrition_final.xlsx")
scores = pd.read_excel(REPORTS / "model_scores.xlsx")

MODEL_ORDER = ["glm-4.5-flash", "deepseek-flash", "qwen-plus"]

# 主标签 = 第一个标签（决定归类），全部标签保留在明细里
df["主标签"] = df["tags"].astype(str).str.split("; ").str[0]

# ---------- Sheet1：模型 × 错误类型 ----------
tags_order = list(OrderedDict.fromkeys(df["主标签"]))
cross = pd.DataFrame(0, index=tags_order, columns=MODEL_ORDER)
for _, r in df.iterrows():
    if r["model"] in cross.columns:
        cross.loc[r["主标签"], r["model"]] += 1
cross["合计"] = cross.sum(axis=1)
cross = cross.sort_values("合计", ascending=False)
cross.loc["合计"] = cross.sum()

# 失败率：失败题数 / 加强提示下的有效题数（归因只统计加强提示）
valid = (
    scores[(scores["prompt"] == "enhanced") & (~scores["missing"])]
    .groupby("model").size().to_dict()
)
fail_cnt = df.groupby("model").size().to_dict()
rate_row = pd.DataFrame(
    [[f"{fail_cnt.get(m, 0)}/{valid.get(m, 0)}"
      + (f" ({fail_cnt.get(m, 0) / valid.get(m, 0) * 100:.0f}%)" if valid.get(m) else "")
      for m in MODEL_ORDER]
     + [f"{len(df)}/{sum(valid.values())}"]],
    index=["失败数/有效题数"],
    columns=MODEL_ORDER + ["合计"],
)
cross_out = pd.concat([cross, rate_row])

# ---------- Sheet2：失败明细 ----------
detail = df.copy()
detail["题号"] = detail["id"]
detail = detail.rename(columns={
    "model": "模型",
    "difficulty": "难度",
    "question": "问题",
    "tags": "全部标签",
    "gold 结果": "gold 结果(行/列)",
    "pred 结果": "pred 结果(行/列)",
    "valid_sql": "SQL可执行",
    "pred_error": "执行报错",
    "ex_answer": "答案等价EX",
})
col_order = ["模型", "题号", "难度", "主标签", "全部标签", "问题",
             "gold 结果(行/列)", "pred 结果(行/列)", "SQL可执行", "执行报错",
             "gold_sql", "pred_sql", "答案等价EX"]
detail = detail[[c for c in col_order if c in detail.columns]]
detail["模型"] = pd.Categorical(detail["模型"], categories=MODEL_ORDER, ordered=True)
detail = detail.sort_values(["模型", "主标签", "题号"])

# ---------- Sheet3：标签汇总 ----------
cnt = Counter()
for t in df["tags"].astype(str):
    for tag in t.split("; "):
        cnt[tag] += 1
total = len(df)
summary = pd.DataFrame(
    [{"标签": k, "次数": v, "占失败题比例": f"{v / total * 100:.1f}%"} for k, v in cnt.most_common()]
)

# ---------- 写文件 ----------
out = REPORTS / "error_attrition_by_model.xlsx"
with pd.ExcelWriter(out, engine="openpyxl") as w:
    cross_out.to_excel(w, sheet_name="模型×错误类型")
    detail.to_excel(w, sheet_name="失败明细", index=False)
    summary.to_excel(w, sheet_name="标签汇总", index=False)

    # 格式化
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    head_fill = PatternFill("solid", fgColor="DCE6F5")
    bold = Font(bold=True)

    ws = w.sheets["模型×错误类型"]
    for c in ws[1]:
        c.fill = head_fill
        c.font = bold
        c.alignment = Alignment(horizontal="center")
    ws.column_dimensions["A"].width = 34
    for i in range(2, 6):
        ws.column_dimensions[get_column_letter(i)].width = 17
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(horizontal="center")
    for c in ws[ws.max_row]:
        c.font = bold

    ws2 = w.sheets["失败明细"]
    widths = {"模型": 16, "题号": 7, "难度": 8, "主标签": 30, "全部标签": 46, "问题": 34,
              "gold 结果(行/列)": 15, "pred 结果(行/列)": 15, "SQL可执行": 10,
              "执行报错": 26, "gold_sql": 60, "pred_sql": 60, "答案等价EX": 11}
    for col, wd in widths.items():
        if col in detail.columns:
            ws2.column_dimensions[get_column_letter(list(detail.columns).index(col) + 1)].width = wd
    for c in ws2[1]:
        c.fill = head_fill
        c.font = bold
        c.alignment = Alignment(horizontal="center", vertical="center")
    ws2.freeze_panes = "A2"
    for row in ws2.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(vertical="top", wrap_text=True)
    ws2.auto_filter.ref = ws2.dimensions

    ws3 = w.sheets["标签汇总"]
    for c in ws3[1]:
        c.fill = head_fill
        c.font = bold
        c.alignment = Alignment(horizontal="center")
    ws3.column_dimensions["A"].width = 42
    ws3.column_dimensions["B"].width = 10
    ws3.column_dimensions["C"].width = 16
    for row in ws3.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(horizontal="center")

print(f"✅ 已生成 {out}")
print(f"\n失败 {len(df)} 条，涉及 {df['model'].nunique()} 个模型、{len(tags_order)} 类主错误")
print("\n模型 × 主错误类型：")
print(cross_out.to_string())
