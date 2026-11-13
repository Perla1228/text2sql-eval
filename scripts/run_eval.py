"""
Text2SQL 评测脚本 v1

流程：
1. 读取 50 题 JSONL
2. 构建 prompt（schema + 问题）
3. 调用模型 API，拿到生成的 SQL
4. 执行模型 SQL，对比 gold_sql 的执行结果
5. 算 3 个指标：Valid SQL / EM / EX
6. 输出汇总表 + 每条详细结果

运行：
  # 先加载 .env（PowerShell）
  Get-Content .env | ForEach-Object { if ($_ -match '^[A-Z_]+=') { $n,$v = $_ -split '=',2; Set-Item "env:$n" $v } }
  
  # 跑评测（默认只跑前 3 题冒烟测试）
  python scripts/run_eval.py --limit 3
  
  # 全量跑 50 题
  python scripts/run_eval.py
  
  # 指定模型
  python scripts/run_eval.py --model glm-4.5-flash --api-url https://open.bigmodel.cn/api/paas/v4 --api-key $env:ZHIPU_API_KEY
"""

import argparse
import itertools
import json
import os
import re
import sqlite3
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

ROOT = Path(__file__).resolve().parent.parent
JSONL = ROOT / "data" / "biz_zh_50.jsonl"
DB = ROOT / "data" / "biz_ecommerce.sqlite"
SCHEMA = ROOT / "data" / "schema_prompt.txt"
RESULTS_DIR = ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)

SYSTEM_PROMPT = "You are an expert at converting natural language questions into SQL queries for SQLite. Only output the SQL query, no explanation, no markdown code fences."

# 简单提示词模板
SIMPLE_TEMPLATE = """{schema}

Question: {question}
SQL:"""

# 加强提示词模板（加了 SQLite 语法指令 + 业务口径约定）
ENHANCED_TEMPLATE = """{schema}

Instructions:
- Write a single SQL query to answer the question
- Use JOINs, GROUP BY, HAVING, CASE WHEN as needed
- For date differences in SQLite, use julianday(date_col1) - julianday(date_col2)
- For monthly grouping, use strftime('%Y-%m', date_col)  or  substr(date_col, 1, 7)
- Only return the SQL query, nothing else

Business conventions (IMPORTANT):
- 提问中涉及"交易、下单、销量、售卖、订单、销售额、成交额"等概念时，需在 orders 表上加 `WHERE orders.status = '已完成'` 过滤，排除已取消/退款订单
- 金额字段单位统一为人民币元：orders.total_amount（整元）、order_items.subtotal（整元）、refunds.refund_amount（含两位小数），计算占比/退款率时直接相除即可，无需单位换算
- "用户喜欢 / 偏好 / 最爱"的排序口径：优先按销量（quantity 或 subtotal）降序，再考虑销售额或订单数
- 年龄分段（CASE WHEN 按以下 5 段划分，边界含端点）：
    18-25岁: age BETWEEN 18 AND 25
    26-35岁: age BETWEEN 26 AND 35
    36-45岁: age BETWEEN 36 AND 45
    46-60岁: age BETWEEN 46 AND 60
    60岁以上: age >= 61

Reference examples (follow these patterns closely):

Example 1 - 退款率（退款金额/销售额，分子取已退款的 refund_amount，分母取已完成+已退款订单的 total_amount）:
  Question: 退款金额占销售额的比例如何
  SQL: SELECT SUM(r.refund_amount) * 1.0 /
           (SELECT SUM(total_amount) FROM orders WHERE status IN ('已完成', '已退款'))
       FROM refunds r WHERE r.status = '已退款'

Example 2 - 品宽（用户人均购买的品类个数，先按用户分组算品类数，再取平均）:
  Question: 已完成订单用户的购买品宽如何
  SQL: SELECT AVG(cnt) FROM (
           SELECT o.user_id, COUNT(DISTINCT c.category_id) AS cnt
           FROM orders o
           JOIN order_items oi ON o.order_id = oi.order_id
           JOIN products p ON oi.product_id = p.product_id
           JOIN categories c ON p.category_id = c.category_id
           WHERE o.status = '已完成'
           GROUP BY o.user_id
       )

Question: {question}
SQL:"""


# ============== 工具函数 ==============

def load_jsonl(path: Path):
    return [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]


def build_prompt(schema_text: str, question: str, enhanced: bool = False) -> str:
    template = ENHANCED_TEMPLATE if enhanced else SIMPLE_TEMPLATE
    return template.format(schema=schema_text, question=question)


def call_chat_api(model: str, api_url: str, api_key: str, prompt: str,
                  system: str = SYSTEM_PROMPT, max_retries: int = 3) -> str:
    """调用 chat completion API，返回模型输出的纯文本"""
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": 1024,
    }
    # glm-4.5+ 默认开启深度思考，reasoning_content 会耗尽 max_tokens
    # 导致 content 字段为空（SQL 输出被挤掉）。关闭思维链让模型直接输出。
    if "glm-4.5" in model or "glm-4.7" in model or "glm-5" in model:
        payload["thinking"] = {"type": "disabled"}

    for attempt in range(max_retries):
        try:
            # 超时可通过环境变量 API_TIMEOUT 覆盖（秒），默认 240
            timeout = int(os.environ.get("API_TIMEOUT", "240"))
            resp = requests.post(f"{api_url.rstrip('/')}/chat/completions",
                                 headers=headers, json=payload, timeout=timeout)
            if resp.status_code == 429:
                wait = 2 ** attempt
                print(f"   [rate limited, retry in {wait}s]")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except requests.RequestException as e:
            if attempt == max_retries - 1:
                print(f"   [API error after {max_retries} retries: {e}]")
                return ""
            time.sleep(1)
    return ""


def extract_sql(text: str) -> str:
    """从模型输出里提取 SQL（处理 markdown code fence、多余解释等）"""
    if not text:
        return ""
    # 去掉 ```sql ... ``` 包裹
    m = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if m:
        text = m.group(1)
    # 去掉前后空白行
    text = text.strip()
    # 如果有"SQL:"前缀，去掉
    text = re.sub(r"^SQL:\s*", "", text, flags=re.IGNORECASE)
    return text


def execute_sql(conn: sqlite3.Connection, sql: str):
    """执行 SQL，返回 (是否合法, 结果集或错误信息)"""
    # conn 是已经打开的数据库连接（相当于"已经连上数据库的网线"）
    if not sql:
        # 模型啥也没返回，直接判为不合法，错误原因记为 "empty_sql"
        return False, "empty_sql"

    # 下面的 try/except 是"试试看，出事就兜住"：
    # SQL 写错（比如少括号、表名拼错）时，Python 会抛出异常直接崩，
    # 这里把异常抓住，转成 (False, 错误信息)，让评测流程能继续跑下一题。
    try:
        # cursor 是"操作数据库的手"，用它在数据库上执行这条 SQL
        cur = conn.cursor()
        cur.execute(sql)
        # fetchall() 把查询结果一次性全部取出来，形如 [(第1行), (第2行), ...]
        rows = cur.fetchall()
        return True, rows          # 语法合法，返回结果集
    except Exception as e:
        # 这里能走到，说明 SQL 语法/语义有问题，把报错文字原样带回去
        return False, str(e)


def rows_equal(r1, r2) -> bool:
    """比较两个结果集是否相等（忽略顺序、忽略类型差异）"""
    # r1 = 模型生成的 SQL 的执行结果，r2 = 标准答案 gold_sql 的执行结果
    if r1 is None or r2 is None:
        return False  # 有一边没结果（通常是执行失败），直接判不相等
    if len(r1) != len(r2):
        return False  # 行数不一样，内容再像也算错（比如答案应是 7 行，模型给了 6 行）

    def norm(v):
        """把单个格子里的值"拉平"，让长得不一样但意思相同的值能比得上"""
        if isinstance(v, float):
            return round(v, 2)   # 浮点数只保留 2 位：3.14159 和 3.14 视为同一个
        if v is None:
            return None          # 空值单独保留（下面和 str 转换区分开，避免 "None" 和 None 混淆）
        return str(v)            # 其余一律转成字符串：数字 100 和字符串 "100" 视为同一个

    # 逐行把每个格子 norm 一遍，再把"行"转成 tuple
    # tuple 才能参与排序和比较（list 不行）
    s1 = sorted([tuple(norm(c) for c in row) for row in r1])
    s2 = sorted([tuple(norm(c) for c in row) for row in r2])

    # 排序后再比，等于"忽略行的顺序"：
    # 模型先返回华南、后返回华东，和标准答案反着来，也算对。
    # 注意是 sorted 列表而不是 set，所以行数重复的情况仍然会被区分。
    return s1 == s2


def _norm_cell(v):
    """单元格值的统一表示：浮点留 2 位、整数和浮点视为同类、其余转字符串"""
    if v is None:
        return ("none",)
    if isinstance(v, bool):
        return ("str", str(v).lower())
    if isinstance(v, (int, float)):
        return ("num", round(float(v), 2))
    return ("str", str(v).strip())


def build_id_name_maps(conn):
    """把各维表的 id → 名称建成映射，用于判断「按 ID 分组」和「按名称分组」是否等价"""
    dims = [
        ("regions", "region_id", "region_name"),
        ("channels", "channel_id", "channel_name"),
        ("categories", "category_id", "category_name"),
        ("products", "product_id", "product_name"),
        ("users", "user_id", "user_name"),
    ]
    maps = []
    for table, id_col, name_col in dims:
        try:
            rows = conn.execute(f"SELECT {id_col}, {name_col} FROM {table}").fetchall()
            maps.append({int(k): str(v) for k, v in rows if k is not None and v is not None})
        except Exception:
            continue
    return maps


_NO_MATCH = object()


def _match_column(gvals, pvals, maps):
    """判断两列的值是否等价；等价则返回所用的映射（None 表示不需要映射）"""
    raw_g = sorted(_norm_cell(v) for v in gvals)
    raw_p = sorted(_norm_cell(v) for v in pvals)
    if raw_g == raw_p:
        return None
    for m in maps:
        def conv(v):
            c = _norm_cell(v)
            if c[0] == "num" and int(c[1]) in m:
                return ("str", m[int(c[1])])
            return c
        if sorted(conv(v) for v in gvals) == sorted(conv(v) for v in pvals):
            return m
    return _NO_MATCH


def answer_equal(pred_res, gold_res, maps):
    """答案等价口径（宽松 EX）：

    - 行数必须一致
    - gold 的每一列都要能在 pred 的某一列里找到（允许 pred 多出辅助列，
      如模型顺带返回了销量/销售额）
    - 列顺序不重要，ID 与名称视为同一个值（1 与「数码电子」等价）
    """
    if pred_res is None or gold_res is None:
        return False
    if len(pred_res) != len(gold_res):
        return False
    if not gold_res:
        return True

    gcols, pcols = len(gold_res[0]), len(pred_res[0])
    if pcols < gcols:
        return False

    for perm in itertools.permutations(range(pcols), gcols):
        chosen = []
        for gi, pj in enumerate(perm):
            m = _match_column([r[gi] for r in gold_res], [r[pj] for r in pred_res], maps)
            if m is _NO_MATCH:
                break
            chosen.append(m)
        else:
            def canon(v, m):
                c = _norm_cell(v)
                if m is not None and c[0] == "num" and int(c[1]) in m:
                    return ("str", m[int(c[1])])
                return c

            g_norm = sorted(tuple(canon(r[gi], chosen[gi]) for gi in range(gcols)) for r in gold_res)
            p_norm = sorted(tuple(canon(r[perm[gi]], chosen[gi]) for gi in range(gcols)) for r in pred_res)
            if g_norm == p_norm:
                return True
    return False


def compute_metrics(pred_sql: str, gold_sql: str, conn: sqlite3.Connection, maps=None):
    """算三个指标：Valid SQL / EM / EX。

    EX 拆成两档，便于看清评测口径的影响：
      ex       严格 EX：结果集行列必须完全一致（列数多一列也算错）
      ex_answer 答案等价 EX：gold 的每一列都能在 pred 里找到，允许 pred 多出辅助列、
                允许 ID/名称互换（本项目报告采用这一档）
    """
    if maps is None:
        maps = build_id_name_maps(conn)

    # 分别执行两条 SQL，拿到 (是否成功, 结果集或报错)
    pred_ok, pred_res = execute_sql(conn, pred_sql)
    gold_ok, gold_res = execute_sql(conn, gold_sql)

    # Valid SQL：只看模型的 SQL 能不能跑通，不关心答案对不对
    valid_sql = pred_ok

    # EM：SQL 文本完全相同（去空格 + 忽略大小写），太严格，仅作对照
    em = pred_ok and gold_ok and pred_sql.strip().lower() == gold_sql.strip().lower()

    # EX 严格档：行列完全一致
    ex = pred_ok and gold_ok and rows_equal(pred_res, gold_res)

    # EX 答案等价档：容器答案一致即算对
    ex_answer = pred_ok and gold_ok and answer_equal(pred_res, gold_res, maps)

    return {
        "valid_sql": valid_sql,
        "em": em,
        "ex": ex,
        "ex_answer": ex_answer,
        "pred_sql": pred_sql,
        "pred_error": pred_res if not pred_ok else None,
    }


# ============== 主流程 ==============

def _auto_key_for_model(model_name: str, explicit_key: str) -> str:
    """根据模型名自动匹配 API key（显式 key 优先）"""
    if explicit_key:
        return explicit_key
    name = model_name.lower()
    if "deepseek" in name:
        return os.environ.get("DEEPSEEK_API_KEY", "")
    if "glm" in name or "zhipu" in name or "bigmodel" in name:
        return os.environ.get("ZHIPU_API_KEY", "")
    if "qwen" in name or "dashscope" in name or "aliyun" in name:
        return os.environ.get("DASHSCOPE_API_KEY", "")
    return os.environ.get("ZHIPU_API_KEY", "")


def _auto_url_for_model(model_name: str, explicit_url: str) -> str:
    """根据模型名自动匹配 API URL（显式 URL 优先）"""
    if explicit_url:
        return explicit_url
    name = model_name.lower()
    if "deepseek" in name:
        return "https://api.deepseek.com/v1"
    if "glm" in name or "zhipu" in name or "bigmodel" in name:
        return "https://open.bigmodel.cn/api/paas/v4"
    if "qwen" in name or "dashscope" in name or "aliyun" in name:
        return "https://dashscope.aliyuncs.com/compatible-mode/v1"
    return "https://open.bigmodel.cn/api/paas/v4"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=os.environ.get("MODEL", "glm-4.5-flash"))
    parser.add_argument("--api-url", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 题（冒烟测试用）")
    parser.add_argument("--enhanced", action="store_true", help="用加强版提示词")
    parser.add_argument("--cache", action="store_true", help="使用本地缓存")
    args = parser.parse_args()

    # 自动匹配 key 和 url
    args.api_url = _auto_url_for_model(args.model, args.api_url)
    args.api_key = _auto_key_for_model(args.model, args.api_key)
    print(f"  [auto] model={args.model} url={args.api_url} key={'*'*8 if args.api_key else 'MISSING'}")

    if not args.api_key:
        print("❌ 请设置 API Key（加载 .env 或 --api-key）")
        return

    schema_text = SCHEMA.read_text(encoding="utf-8")
    items = load_jsonl(JSONL)
    if args.limit:
        items = items[:args.limit]

    conn = sqlite3.connect(DB)
    maps = build_id_name_maps(conn)
    results = []

    print(f"\n{'='*70}")
    print(f"Text2SQL Eval | model={args.model} | n={len(items)} | enhanced={args.enhanced}")
    print(f"{'='*70}")

    for i, item in enumerate(items, 1):
        qid = item["id"]
        question = item["question"]
        gold = item["gold_sql"]
        diff = item["difficulty"]

        # 缓存路径（带 prompt 标识，避免 simple / enhanced 互相覆盖）
        prompt_tag = "enhanced" if args.enhanced else "simple"
        cache_path = RESULTS_DIR / f"{args.model}_{prompt_tag}_{qid}.json"

        if args.cache and cache_path.exists():
            with open(cache_path, encoding="utf-8") as f:
                cached = json.load(f)
            if "ex_answer" not in cached:
                cached.update(compute_metrics(cached["pred_sql"], gold, conn, maps))
            results.append(cached)
            print(f"[{i}/{len(items)}] Q{qid} [cache] EX={'✅' if cached['ex'] else '❌'}")
            continue

        prompt = build_prompt(schema_text, question, args.enhanced)
        raw_output = call_chat_api(args.model, args.api_url, args.api_key, prompt)
        pred_sql = extract_sql(raw_output)

        metrics = compute_metrics(pred_sql, gold, conn, maps)

        record = {
            "id": qid,
            "difficulty": diff,
            "question": question,
            "gold_sql": gold,
            "raw_output": raw_output,
            **metrics,
        }
        results.append(record)

        # 存缓存
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)

        mark = "✅" if metrics["ex"] else "❌"
        print(f"[{i}/{len(items)}] Q{qid} [{diff}] EX={mark}")

    conn.close()

    # ========== 汇总 ==========
    total = len(results)
    valid_cnt = sum(1 for r in results if r["valid_sql"])
    em_cnt = sum(1 for r in results if r["em"])
    ex_cnt = sum(1 for r in results if r["ex"])

    print(f"\n{'='*70}")
    print(f"汇总（{total} 题）：")
    print(f"  Valid SQL（语法合法）: {valid_cnt}/{total} = {valid_cnt/total*100:.1f}%")
    print(f"  EM（完全匹配）:         {em_cnt}/{total} = {em_cnt/total*100:.1f}%")
    print(f"  EX（执行准确率）:       {ex_cnt}/{total} = {ex_cnt/total*100:.1f}%  ← 核心指标")

    # 按难度分组
    for d in ["easy", "medium", "hard"]:
        sub = [r for r in results if r["difficulty"] == d]
        if sub:
            ex = sum(1 for r in sub if r["ex"])
            print(f"  {d:7s}: {ex}/{len(sub)} = {ex/len(sub)*100:.1f}%")

    print(f"\n结果已保存到 {RESULTS_DIR}/")


if __name__ == "__main__":
    main()
