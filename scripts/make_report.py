"""生成 Text2SQL 评测 HTML 报告（单文件、无外部依赖）

数据来源：
  reports/model_scores.xlsx            三模型逐题评分（答案等价口径）
  reports/error_attrition_final.xlsx   失败归因标签
  reports/ablation_results.xlsx        消融实验
  reports/gold_sql_review.xlsx         gold 修复清单
"""
import html
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"

MODELS = ["glm-4.5-flash", "deepseek-flash", "qwen-plus"]
LABELS = {"glm-4.5-flash": "智谱 glm-4.5-flash", "deepseek-flash": "DeepSeek flash", "qwen-plus": "通义千问 qwen-plus"}
COLORS = {"glm-4.5-flash": "#4C6FFF", "deepseek-flash": "#00A870", "qwen-plus": "#F5A623"}


def fmt(v):
    return "—" if v is None else f"{v:.1f}%"


scores = pd.read_excel(REPORTS / "model_scores.xlsx")
enh = scores[(scores["prompt"] == "enhanced") & (~scores["missing"])]

leaderboard = []
for m in MODELS:
    sub = enh[enh["model"] == m]
    n = len(sub)
    leaderboard.append({
        "model": m, "n": n,
        "valid": sub["valid_sql"].mean() * 100,
        "ex_strict": sub["ex"].mean() * 100,
        "ex": sub["ex_answer"].mean() * 100,
        "easy": sub[sub.difficulty == "easy"]["ex_answer"].mean() * 100,
        "medium": sub[sub.difficulty == "medium"]["ex_answer"].mean() * 100,
        "hard": sub[sub.difficulty == "hard"]["ex_answer"].mean() * 100,
    })

attr = pd.read_excel(REPORTS / "error_attrition_final.xlsx")
tag_counter = Counter()
for t in attr["tags"]:
    for tag in str(t).split("; "):
        tag_counter[tag] += 1
fail_total = len(attr)
tags = [(t, c, c / fail_total * 100) for t, c in tag_counter.most_common()]

# 口径类问题：仅统计「直接由业务口径 / 语义推断导致」的标签
# - 「多列（辅助列 / 口径等价）」是严格 EX 假阳性（等价 EX 已判对），不计入
# - 「语法错误」属实现问题，不计入
# - 「缺列 / 行数不同 / JOIN 缺失」属答案完整性，单列统计，不计入本口径
koujing = (sum(c for t, c, p in tags if t.startswith("口径") or "逻辑推断差" in t) / fail_total * 100
           if fail_total else 0)

ablation = pd.read_excel(REPORTS / "ablation_results.xlsx")
gold_n = len(pd.read_excel(REPORTS / "gold_sql_review.xlsx"))
# 累计修订条数：各 gold 补丁脚本改过的题号并集（gold_fixes 19 ∪ _golds_v2 20 ∪ Q8/Q37/Q28 迭代）
gold_revised = 31

# 消融提升（简单 → 加强），来自同一份 ablation 表，避免正文硬编码旧数字
ab_map = {(r["model"], r["prompt"]): r for _, r in ablation.iterrows()}


def ab_val(model, prompt, col):
    row = ab_map.get((model, prompt))
    return float(row[col]) if row is not None else float("nan")

cases = []
for m in MODELS[:2]:
    sub = enh[(enh.model == m)]
    ok = sub[sub.ex_answer & (sub.difficulty == "hard")]
    if ok.empty:
        ok = sub[sub.ex_answer & (sub.difficulty == "medium")]
    bad = attr[(attr.model == m) & (attr.difficulty.isin(["medium", "hard"]))]
    # final_attrition 的标签已细分为「多列 / 缺列」，这里优先取真正的漏列失败
    bad = bad[bad.tags.str.contains("缺列", na=False)] if not bad.empty else bad
    if bad.empty:
        bad = attr[attr.model == m]
    for kind, item in (("正确", ok.iloc[0] if not ok.empty else None),
                       ("失败", bad.iloc[0] if not bad.empty else None)):
        if item is None:
            continue
        cases.append({
            "model": LABELS[m], "kind": kind, "qid": int(item["id"]),
            "difficulty": item["difficulty"], "question": item["question"],
            "gold_sql": item["gold_sql"], "pred_sql": item["pred_sql"] or "(空输出)",
            "tag": item.get("tags", ""), "error": item.get("pred_error", "") if isinstance(item.get("pred_error", ""), str) else "",
        })


def esc(s):
    return html.escape(str(s if s is not None else ""))


def bar(label, value, color, maxv=100):
    w = 0 if value is None else max(min(value / maxv * 100, 100), 0)
    return (f'<div class="bar-row"><div class="bar-label">{esc(label)}</div>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{w:.1f}%;background:{color}"></div></div>'
            f'<div class="bar-value">{fmt(value)}</div></div>')


lb_rows = "".join(
    f"<tr><td class='strong'>{esc(LABELS[r['model']])}</td>"
    f"<td>{r['n']}</td><td>{fmt(r['valid'])}</td><td>{fmt(r['ex_strict'])}</td>"
    f"<td class='hl'>{fmt(r['ex'])}</td>"
    f"<td>{fmt(r['easy'])}</td><td>{fmt(r['medium'])}</td><td>{fmt(r['hard'])}</td></tr>"
    for r in leaderboard)

lb_bars = "".join(
    f"<div class='group-title'>{esc(LABELS[r['model']])}</div>"
    + bar("Valid SQL", r["valid"], "#9AA4B8")
    + bar("答案等价 EX", r["ex"], COLORS[r["model"]])
    for r in leaderboard)

tag_bars = "".join(bar(t, p, "#E5484D", maxv=tags[0][2] if tags else 100) for t, c, p in tags)

ab_rows = "".join(
    f"<tr><td class='strong'>{esc(LABELS[r['model']])}</td>"
    f"<td>{'简单提示' if r['prompt'] == 'simple' else '加强提示'}</td>"
    f"<td>{int(r['n'])}</td>"
    f"<td>{fmt(r['valid_pct'])}</td><td class='hl'>{fmt(r['ex_pct'])}</td>"
    f"<td>{fmt(r['easy_pct'])}</td><td>{fmt(r['medium_pct'])}</td><td>{fmt(r['hard_pct'])}</td></tr>"
    for _, r in ablation.iterrows())

delta_rows = ""
for m in MODELS[:2]:
    s = ablation[(ablation.model == m) & (ablation.prompt == "simple")]
    e = ablation[(ablation.model == m) & (ablation.prompt == "enhanced")]
    if s.empty or e.empty:
        continue
    s, e = s.iloc[0], e.iloc[0]
    d = e["ex_pct"] - s["ex_pct"]
    dh = e["hard_pct"] - s["hard_pct"]
    cls = "neg" if d < 0 else "pos"
    delta_rows += (f"<tr><td class='strong'>{esc(LABELS[m])}</td><td>{fmt(s['ex_pct'])}</td>"
                   f"<td>{fmt(e['ex_pct'])}</td><td class='{cls}'>{d:+.1f} pt</td>"
                   f"<td class='{cls}'>{dh:+.1f} pt</td></tr>")

case_html = ""
for c in cases:
    badge = "ok" if c["kind"] == "正确" else "bad"
    case_html += f"""
    <div class="case">
      <div class="case-head"><span class="badge {badge}">{esc(c['kind'])}</span>
        <span class="case-model">{esc(c['model'])}</span>
        <span class="case-meta">Q{c['qid']} · {esc(c['difficulty'])}</span></div>
      <div class="case-q">{esc(c['question'])}</div>
      <div class="sql-label">gold_sql</div><pre>{esc(c['gold_sql'])}</pre>
      <div class="sql-label">模型生成 SQL</div><pre>{esc(c['pred_sql'])}</pre>
      {f"<div class='case-tag'>归因标签：{esc(c['tag'])}</div>" if c['tag'] else ""}
      {f"<div class='case-err'>报错：{esc(c['error'])}</div>" if c['error'] else ""}
    </div>"""

top_tag = tags[0] if tags else ("", 0, 0)
best = max(leaderboard, key=lambda r: r["ex"])
worst = min(leaderboard, key=lambda r: r["ex"])
gap_min = min(r["ex"] - r["ex_strict"] for r in leaderboard)
gap_max = max(r["ex"] - r["ex_strict"] for r in leaderboard)

glm_gain = ab_val("glm-4.5-flash", "enhanced", "ex_pct") - ab_val("glm-4.5-flash", "simple", "ex_pct")
ds_gain = ab_val("deepseek-flash", "enhanced", "ex_pct") - ab_val("deepseek-flash", "simple", "ex_pct")
glm_hard = ab_val("glm-4.5-flash", "enhanced", "hard_pct") - ab_val("glm-4.5-flash", "simple", "hard_pct")
ds_hard = ab_val("deepseek-flash", "enhanced", "hard_pct") - ab_val("deepseek-flash", "simple", "hard_pct")
ds_simple_n = int(ab_val("deepseek-flash", "simple", "n"))
ds_enh_n = int(ab_val("deepseek-flash", "enhanced", "n"))

html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Text2SQL 中文电商评测报告</title>
<style>
* {{ box-sizing:border-box; }}
body {{ margin:0; background:#F6F7FB; color:#1B2130; line-height:1.7;
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; }}
.page {{ max-width:1000px; margin:0 auto; padding:48px 28px 80px; }}
h1 {{ font-size:30px; margin:0 0 8px; letter-spacing:-.5px; }}
.sub {{ color:#6B7280; font-size:14px; margin-bottom:26px; }}
h2 {{ font-size:20px; margin:44px 0 6px; padding-left:12px; border-left:4px solid #4C6FFF; }}
.desc {{ color:#6B7280; font-size:13px; margin:0 0 16px; padding-left:16px; }}
.card {{ background:#fff; border:1px solid #E5E8F0; border-radius:12px; padding:20px 22px; margin-bottom:16px; }}
.kpis {{ display:flex; gap:14px; flex-wrap:wrap; margin-bottom:8px; }}
.kpi {{ flex:1; min-width:170px; background:#fff; border:1px solid #E5E8F0; border-radius:12px; padding:16px 18px; }}
.kpi .num {{ font-size:26px; font-weight:700; color:#4C6FFF; }}
.kpi .lab {{ font-size:12px; color:#6B7280; margin-top:2px; }}
table {{ width:100%; border-collapse:collapse; font-size:14px; }}
th,td {{ padding:10px 8px; text-align:center; border-bottom:1px solid #EEF0F6; }}
th {{ color:#6B7280; font-weight:600; font-size:12px; }}
td.strong {{ font-weight:600; text-align:left; }}
td.hl {{ font-weight:700; color:#4C6FFF; }}
.bar-row {{ display:flex; align-items:center; gap:10px; margin:7px 0; font-size:13px; }}
.bar-label {{ width:120px; color:#4B5563; flex:none; }}
.bar-track {{ flex:1; height:16px; background:#EEF0F6; border-radius:8px; overflow:hidden; }}
.bar-fill {{ height:100%; border-radius:8px; }}
.bar-value {{ width:58px; text-align:right; color:#374151; }}
.group-title {{ font-size:13px; font-weight:600; margin:16px 0 4px; }}
.note {{ border-left:4px solid #F5A623; background:#FFFBF0; border-radius:8px; padding:14px 18px;
font-size:13.5px; color:#5A4B2A; margin:16px 0; }}
.note b {{ color:#8A6A14; }}
.case {{ background:#fff; border:1px solid #E5E8F0; border-radius:12px; padding:18px 20px; margin-bottom:14px; }}
.case-head {{ display:flex; align-items:center; gap:10px; margin-bottom:8px; }}
.badge {{ font-size:11px; padding:2px 9px; border-radius:999px; font-weight:600; }}
.badge.ok {{ background:#E6F7EF; color:#007A52; }}
.badge.bad {{ background:#FDECEC; color:#C0272D; }}
.case-model {{ font-weight:600; font-size:13px; }}
.case-meta {{ font-size:12px; color:#9AA4B8; }}
.case-q {{ font-size:14px; margin-bottom:10px; }}
.sql-label {{ font-size:11px; color:#9AA4B8; letter-spacing:.5px; margin-top:8px; }}
pre {{ background:#F4F6FB; border:1px solid #E5E8F0; border-radius:8px; padding:12px 14px;
font-size:12.5px; overflow-x:auto; white-space:pre-wrap; word-break:break-word; margin:4px 0 0;
font-family:"SFMono-Regular",Consolas,monospace; }}
.case-tag {{ font-size:12px; color:#C0272D; margin-top:8px; }}
.case-err {{ font-size:12px; color:#9A3412; margin-top:4px; }}
.pos {{ color:#007A52; font-weight:600; }} .neg {{ color:#C0272D; font-weight:600; }}
ul {{ margin:6px 0 0 20px; padding:0; font-size:14px; }} li {{ margin:6px 0; }}
.foot {{ margin-top:44px; padding-top:16px; border-top:1px solid #E5E8F0; color:#9AA4B8; font-size:12px; }}
</style></head><body><div class="page">
<h1>Text2SQL 中文电商评测报告</h1>
<div class="sub">自建 50 题评测集 · 3 模型横向对比 · 2 档提示词消融 · {fail_total} 条失败样本归因</div>

<div class="kpis">
<div class="kpi"><div class="num">50</div><div class="lab">评测题（15 easy / 20 medium / 15 hard）</div></div>
<div class="kpi"><div class="num">{gold_n}</div><div class="lab">留档复核的 gold_sql 修订条数（累计修订 {gold_revised} 条）</div></div>
<div class="kpi"><div class="num">{fail_total}</div><div class="lab">失败样本（三模型合计）</div></div>
<div class="kpi"><div class="num">{koujing:.0f}%</div><div class="lab">失败中业务口径类占比（漏 DISTINCT / 逻辑推断差）</div></div>
</div>

<h2>一、实验设置与统计口径</h2>
<p class="desc">先把指标和范围讲清楚，结论才可信。</p>
<div class="card">
<ul>
<li><b>数据与题目</b>：自建中文电商库（8 表、800 订单、2024-06 ~ 2025-08），50 题分 easy / medium / hard，覆盖单表、2 表 JOIN、3 表 JOIN + HAVING + 子查询。</li>
<li><b>指标</b>：Valid SQL（能否执行）、严格 EX（结果行列完全一致）、<b>答案等价 EX（本报告主指标）</b>。</li>
<li><b>答案等价 EX 定义</b>：行数一致，且 gold 的每一列都能在模型结果里找到；允许模型多返回辅助列（如顺带带上销量/销售额），允许 ID 与名称等价（1 与「数码电子」视为同一个值），忽略列顺序。</li>
<li><b>口径复核</b>：逐题对照业务语义，<b>累计修订 {gold_revised} 条</b>题目本身的逻辑错误，其中 <b>{gold_n} 条留档复核</b>（附修改前后 SQL 对照，明细见 <code>reports/gold_sql_review.xlsx</code>），其余为同题多轮迭代修订。典型问题：过滤条件写在 JOIN ON 里失效、ORDER BY 用明细列、缺聚合/GROUP BY、分母口径错、明细重复累加。</li>
<li><b>缺失处理</b>：接口异常产生的空输出按「缺失」处理，不计入分母（表中「有效题数」已扣除），避免把调用失败算成模型能力问题。本次加强提示下三模型均为 50/50 有效；消融组的 simple 档 deepseek-flash 为 {ds_simple_n}/50。</li>
<li><b>消融实验</b>：<b>仅取 glm-4.5-flash 与 deepseek-flash</b>，各跑「简单提示 / 加强提示」两档，共 4 组 × 50 题；qwen-plus 只参与横向对比。</li>
</ul>
<div class="note"><b>为什么消融没有 qwen-plus？</b> 消融需要成对运行（模型 × 2 档提示），加千问意味着多 2 组全量调用；其响应延迟高、成本不合算，且它在横向对比中 hard 段（{next(r['hard'] for r in leaderboard if r['model'] == 'qwen-plus'):.0f}%）明显低于 deepseek（{next(r['hard'] for r in leaderboard if r['model'] == 'deepseek-flash'):.0f}%），不改变消融结论方向。因此<b>消融结论仅代表 glm 与 deepseek 两个模型，不外推到 qwen-plus</b>。</div>
</div>

<h2>二、三模型横向对比（加强提示）</h2>
<p class="desc">严格 EX 与答案等价 EX 并列，用来量化「评测口径」带来的差异。</p>
<div class="card"><table>
<tr><th>模型</th><th>有效题数</th><th>Valid SQL</th><th>严格 EX</th><th>答案等价 EX</th><th>easy</th><th>medium</th><th>hard</th></tr>
{lb_rows}</table></div>
<div class="card">{lb_bars}</div>
<div class="note">三个模型 Valid SQL 在 {min(r['valid'] for r in leaderboard):.0f}%~{max(r['valid'] for r in leaderboard):.0f}%，但答案等价 EX 只有 {worst['ex']:.0f}%~{best['ex']:.0f}%：<b>SQL 能跑通不等于答对</b>。严格 EX 与等价 EX 相差 {gap_min:.0f}~{gap_max:.0f} 个百分点（qwen {next(r['ex']-r['ex_strict'] for r in leaderboard if r['model']=='qwen-plus'):.0f} pt / deepseek {next(r['ex']-r['ex_strict'] for r in leaderboard if r['model']=='deepseek-flash'):.0f} pt / glm {next(r['ex']-r['ex_strict'] for r in leaderboard if r['model']=='glm-4.5-flash'):.0f} pt），说明原口径把「多返回一列」「按 ID 而非名称分组」这类等价答案误判成错误，修正后才是模型的真实水平。</div>

<h2>三、失败归因分布</h2>
<p class="desc">共 {fail_total} 条失败样本；一条样本可能有多个标签，占比之和大于 100%。</p>
<div class="card">{tag_bars}</div>
<div class="note"><b>核心发现：{koujing:.0f}% 的失败直接由业务口径/语义推断导致（漏 DISTINCT、同表同字段但值对不上），语法错误仅 {next((c/fail_total*100 for t,c,p in tags if t.startswith('语法错误')), 0):.0f}%。</b> 其中「{esc(top_tag[0])}」出现 {top_tag[1]} 次（{top_tag[2]:.0f}%），属答案完整性而非口径问题。这说明改善方向不是换更大的模型，而是把评测题的口径写清楚、并把 SQL 语义对齐纳入评测体系。</div>

<h2>四、典型案例</h2>
<p class="desc">每个模型各取 1 条正确、1 条失败，对比 gold_sql 与模型生成 SQL。</p>
{case_html}

<h2>五、消融实验：简单 vs 加强提示</h2>
<p class="desc">仅 glm-4.5-flash 与 deepseek-flash；指标为答案等价 EX。</p>
<div class="card"><table>
<tr><th>模型</th><th>提示词</th><th>有效题数</th><th>Valid SQL</th><th>EX</th><th>easy</th><th>medium</th><th>hard</th></tr>
{ab_rows}</table></div>
<div class="card"><table>
<tr><th>模型</th><th>简单 EX</th><th>加强 EX</th><th>总 EX 变化</th><th>hard 变化</th></tr>
{delta_rows}</table></div>
<div class="note"><b>加强提示带来正向收益：glm {glm_gain:+.1f} pt、deepseek {ds_gain:+.1f} pt；收益几乎全部来自复杂题。</b> easy 段 deepseek 持平、glm 仅 {ab_val('glm-4.5-flash','enhanced','easy_pct') - ab_val('glm-4.5-flash','simple','easy_pct'):+.1f} pt；而 hard 段分别提升 {glm_hard:+.1f} / {ds_hard:+.1f} pt。原因是业务口径约定（状态过滤、金额单位）与 few-shot 示例（退款率、品宽）主要作用于多表 JOIN 与嵌套聚合题，简单题靠 schema 本身即可写对。注：deepseek 的 simple 档为 {ds_simple_n} 题、加强档为 {ds_enh_n} 题，跨分母比较存在 1 题差异。</div>

<h2>六、结论与局限</h2>
<div class="card"><ul>
<li><b>瓶颈在语义口径，不在语法。</b> Valid SQL 在 {min(r['valid'] for r in leaderboard):.0f}%~{max(r['valid'] for r in leaderboard):.0f}%，答案等价 EX 只有 {worst['ex']:.0f}%~{best['ex']:.0f}%，失败集中在缺列、聚合口径、JOIN/过滤条件。</li>
<li><b>评测口径本身是最大的误差源。</b> 严格 EX 会低估模型 {gap_min:.0f}~{gap_max:.0f} 个百分点（qwen {next(r['ex']-r['ex_strict'] for r in leaderboard if r['model']=='qwen-plus'):.0f} / deepseek {next(r['ex']-r['ex_strict'] for r in leaderboard if r['model']=='deepseek-flash'):.0f} / glm {next(r['ex']-r['ex_strict'] for r in leaderboard if r['model']=='glm-4.5-flash'):.0f} pt）；评测集 gold 累计修订 {gold_revised} 条（{gold_n} 条留档）。做 Text2SQL 评测，先把 gold 和口径打磨干净，比换模型更重要。</li>
<li><b>提示词收益集中在复杂题。</b> 两模型 × 两档提示的消融显示加强提示总体 {glm_gain:+.1f} / {ds_gain:+.1f} pt，但 easy 段几乎不动，hard 段达 {glm_hard:+.1f} / {ds_hard:+.1f} pt——提示词应按难度与题型定向注入，而不是全局堆指令。</li>
<li><b>局限</b>：hard 仅 15 题，1 题 = 6.7 pt，波动大；消融只覆盖 2 个模型。<b>横向对比三模型均为 50/50 有效题；消融中 deepseek 的 simple 档有 1 题（Q43）接口空输出，按缺失剔除后 n={ds_simple_n}</b>，故其 simple→加强的 {ds_gain:+.1f} pt 跨了 1 题分母差异，不改变方向。</li>
</ul></div>

<div class="foot">数据来源：reports/model_scores.xlsx、error_attrition_final.xlsx、ablation_results.xlsx、gold_sql_review.xlsx。temperature=0，结果可复现。</div>
</div></body></html>"""

out = REPORTS / "text2sql_eval_report.html"
out.write_text(html_doc, encoding="utf-8")

print("模型 | Valid | 严格EX | 等价EX")
for r in leaderboard:
    print(f"{LABELS[r['model']]:20s} {fmt(r['valid']):>7s} {fmt(r['ex_strict']):>7s} {fmt(r['ex']):>7s}")
print(f"\n失败 {fail_total} 条；口径类占比 {koujing:.0f}%")
print(f"✅ 报告已生成：{out}")
