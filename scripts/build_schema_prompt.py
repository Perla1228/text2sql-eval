"""
从 SQLite 数据库自动生成给模型看的 schema 提示词

输出格式：
------------------------------------------------------
Database Schema:

CREATE TABLE regions (
    region_id INTEGER PRIMARY KEY,
    region_name TEXT NOT NULL
);

Sample rows from regions:
region_id | region_name
----------|----------
1 | 华东
2 | 华南
...

（每张表都有 DDL + 3 行样例行）
------------------------------------------------------

为什么要自动生成？
- 手写字段容易错
- 样例行必须真实，模型才能理解"表里存了什么"
"""

import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "biz_ecommerce.sqlite"
OUT = Path(__file__).resolve().parent.parent / "data" / "schema_prompt.txt"

conn = sqlite3.connect(DB)
cur = conn.cursor()

# 1. 获取所有表名
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [r[0] for r in cur.fetchall()]

parts = ["Database Schema for a Chinese e-commerce system:\n"]

for table in tables:
    # 2. 获取 CREATE TABLE DDL
    cur.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table}'")
    ddl = cur.fetchone()[0]
    parts.append(f"\n-- {table}\n{ddl};\n")

    # 3. 获取前 3 行样例行（表头 + 数据）
    cur.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in cur.fetchall()]
    col_line = " | ".join(cols)

    cur.execute(f"SELECT * FROM {table} LIMIT 3")
    rows = cur.fetchall()
    sample_lines = [col_line, "-" * len(col_line)]
    for row in rows:
        # 把 None 处理成 NULL，把长字符串截断
        vals = []
        for v in row:
            if v is None:
                vals.append("NULL")
            elif isinstance(v, str) and len(v) > 30:
                vals.append(v[:27] + "...")
            else:
                vals.append(str(v))
        sample_lines.append(" | ".join(vals))

    parts.append(f"\nSample rows from {table} (3 rows):\n" + "\n".join(sample_lines))

parts.append("\n\nIMPORTANT RULES:\n")
parts.append("- Use single quotes for string literals: WHERE gender = '女'\n")
parts.append("- Use strftime('%Y-%m', col) for month-level grouping\n")
parts.append("- Use julianday(col1) - julianday(col2) to compute date difference in days\n")
parts.append("- Total sales = SUM(total_amount) FROM orders WHERE status = '已完成'\n")
parts.append("- Only return SQL, no explanation, no markdown code fences\n")
parts.append("\nNow answer the user's question with a single SQL query.\n")

prompt_text = "\n".join(parts)
OUT.write_text(prompt_text, encoding="utf-8")

print(f"✅ Schema prompt 已生成：{OUT}")
print(f"   大小：{len(prompt_text)} 字符，覆盖 {len(tables)} 张表")
print(f"\n前 500 字预览：\n{prompt_text[:500]}...")

conn.close()
