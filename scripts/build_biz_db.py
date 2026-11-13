"""Day 2：自建电商业务数据库。

建 8 张表 + 造测试数据（固定随机种子，可复现）。
用法：python scripts/build_biz_db.py
产出：data/biz_ecommerce.sqlite + data/schema.sql
"""
from __future__ import annotations

import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "biz_ecommerce.sqlite"
SCHEMA_PATH = PROJECT_ROOT / "data" / "schema.sql"

random.seed(42)  # 固定种子，保证每次造的数据一样

# ---------- 基础数据字典 ----------
CATEGORIES = ["数码电子", "服饰鞋包", "美妆护肤", "食品生鲜", "家居百货", "运动户外"]
CHANNELS = ["APP", "小程序", "H5", "PC官网"]
REGIONS = ["华东", "华南", "华北", "华中", "西南", "西北", "东北"]
PAY_TYPES = ["微信支付", "支付宝", "银行卡"]
ORDER_STATUS = ["已完成", "已取消", "退款中", "已退款"]
REFUND_REASONS = ["质量问题", "七天无理由", "发错货", "不想要了", "描述不符"]


def build_schema(cur: sqlite3.Cursor) -> None:
    cur.executescript(
        """
        DROP TABLE IF EXISTS order_items;
        DROP TABLE IF EXISTS refunds;
        DROP TABLE IF EXISTS orders;
        DROP TABLE IF EXISTS products;
        DROP TABLE IF EXISTS categories;
        DROP TABLE IF EXISTS users;
        DROP TABLE IF EXISTS channels;
        DROP TABLE IF EXISTS regions;

        CREATE TABLE regions (
            region_id   INTEGER PRIMARY KEY,
            region_name TEXT NOT NULL
        );

        CREATE TABLE channels (
            channel_id   INTEGER PRIMARY KEY,
            channel_name TEXT NOT NULL
        );

        CREATE TABLE categories (
            category_id   INTEGER PRIMARY KEY,
            category_name TEXT NOT NULL
        );

        CREATE TABLE users (
            user_id     INTEGER PRIMARY KEY,
            user_name   TEXT NOT NULL,
            gender      TEXT,
            age         INTEGER,
            region_id   INTEGER,
            register_date TEXT,
            FOREIGN KEY (region_id) REFERENCES regions(region_id)
        );

        CREATE TABLE products (
            product_id   INTEGER PRIMARY KEY,
            product_name TEXT NOT NULL,
            category_id  INTEGER,
            price        REAL NOT NULL,
            stock        INTEGER DEFAULT 0,
            FOREIGN KEY (category_id) REFERENCES categories(category_id)
        );

        CREATE TABLE orders (
            order_id     INTEGER PRIMARY KEY,
            user_id      INTEGER,
            channel_id   INTEGER,
            order_time   TEXT NOT NULL,
            total_amount REAL NOT NULL,
            pay_type     TEXT,
            status       TEXT DEFAULT '已完成',
            FOREIGN KEY (user_id)    REFERENCES users(user_id),
            FOREIGN KEY (channel_id) REFERENCES channels(channel_id)
        );

        CREATE TABLE order_items (
            item_id     INTEGER PRIMARY KEY,
            order_id    INTEGER,
            product_id  INTEGER,
            quantity    INTEGER NOT NULL,
            unit_price  REAL NOT NULL,
            subtotal    REAL NOT NULL,
            FOREIGN KEY (order_id)   REFERENCES orders(order_id),
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        );

        CREATE TABLE refunds (
            refund_id    INTEGER PRIMARY KEY,
            order_id     INTEGER,
            refund_time  TEXT NOT NULL,
            refund_amount REAL NOT NULL,
            reason       TEXT,
            status       TEXT DEFAULT '已退款',
            FOREIGN KEY (order_id) REFERENCES orders(order_id)
        );
        """
    )


def seed_dicts(cur: sqlite3.Cursor) -> None:
    cur.executemany("INSERT INTO regions (region_name) VALUES (?)", [(r,) for r in REGIONS])
    cur.executemany("INSERT INTO channels (channel_name) VALUES (?)", [(c,) for c in CHANNELS])
    cur.executemany("INSERT INTO categories (category_name) VALUES (?)", [(c,) for c in CATEGORIES])


def rand_date(start: datetime, days: int) -> str:
    return (start + timedelta(days=random.randint(0, days))).strftime("%Y-%m-%d %H:%M:%S")


def seed_users(cur: sqlite3.Cursor, n: int = 500) -> None:
    start = datetime(2024, 1, 1)
    rows = []
    for uid in range(1, n + 1):
        rows.append((
            f"用户{uid:04d}",
            random.choice(["男", "女"]),
            random.randint(18, 65),
            random.randint(1, len(REGIONS)),
            rand_date(start, 600),
        ))
    cur.executemany(
        "INSERT INTO users (user_name, gender, age, region_id, register_date) VALUES (?,?,?,?,?)",
        rows,
    )


def seed_products(cur: sqlite3.Cursor) -> None:
    product_pool = [
        ("智能手机 Pro", 1, 4999), ("无线耳机", 1, 599), ("平板电脑", 1, 3299),
        ("智能手表", 1, 1299), ("蓝牙音箱", 1, 399),
        ("纯棉T恤", 2, 89), ("牛仔裤", 2, 199), ("运动鞋", 2, 359), ("羽绒服", 2, 599),
        ("口红", 3, 129), ("面霜", 3, 259), ("面膜", 3, 79),
        ("牛奶", 4, 59), ("坚果礼盒", 4, 99), ("生鲜水果", 4, 49),
        ("四件套", 5, 199), ("收纳箱", 5, 49), ("台灯", 5, 129),
        ("瑜伽垫", 6, 89), ("跑步鞋", 6, 399), ("哑铃", 6, 159),
    ]
    rows = [(name, cat, price, random.randint(50, 500)) for name, cat, price in product_pool]
    cur.executemany(
        "INSERT INTO products (product_name, category_id, price, stock) VALUES (?,?,?,?)",
        rows,
    )


def seed_orders(cur: sqlite3.Cursor, n: int = 800) -> None:
    """造订单 + 订单明细，部分订单生成退款。"""
    start = datetime(2024, 6, 1)
    for oid in range(1, n + 1):
        user_id = random.randint(1, 500)
        channel_id = random.randint(1, len(CHANNELS))
        order_time = rand_date(start, 450)
        status = random.choices(ORDER_STATUS, weights=[70, 10, 5, 15])[0]

        # 每单 1-3 个商品（从已有商品中随机选）
        num_items = random.randint(1, 3)
        product_ids = random.sample(range(1, 22), num_items)
        total = 0.0
        cur.execute(
            "INSERT INTO orders (user_id, channel_id, order_time, total_amount, pay_type, status) VALUES (?,?,?,?,?,?)",
            (user_id, channel_id, order_time, 0, random.choice(PAY_TYPES), status),
        )
        order_id = cur.lastrowid
        for pid in product_ids:
            cur.execute("SELECT price FROM products WHERE product_id=?", (pid,))
            price = cur.fetchone()[0]
            qty = random.randint(1, 3)
            subtotal = round(price * qty, 2)
            total += subtotal
            cur.execute(
                "INSERT INTO order_items (order_id, product_id, quantity, unit_price, subtotal) VALUES (?,?,?,?,?)",
                (order_id, pid, qty, price, subtotal),
            )
        cur.execute("UPDATE orders SET total_amount=? WHERE order_id=?", (round(total, 2), order_id))

        # 已退款的订单生成退款记录
        if status == "已退款":
            refund_time = rand_date(datetime.strptime(order_time, "%Y-%m-%d %H:%M:%S"), 30)
            cur.execute(
                "INSERT INTO refunds (order_id, refund_time, refund_amount, reason, status) VALUES (?,?,?,?,?)",
                (order_id, refund_time, round(total * random.uniform(0.5, 1.0), 2),
                 random.choice(REFUND_REASONS), "已退款"),
            )


def export_schema(cur: sqlite3.Cursor) -> None:
    """把建表语句导出到 schema.sql，方便给模型做 prompt。"""
    cur.execute("SELECT sql FROM sqlite_master WHERE type='table' ORDER BY name")
    stmts = [row[0] for row in cur.fetchall() if row[0]]
    SCHEMA_PATH.write_text("\n\n".join(stmts) + "\n", encoding="utf-8")


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    build_schema(cur)
    seed_dicts(cur)
    seed_users(cur, n=500)
    seed_products(cur)
    seed_orders(cur, n=800)
    conn.commit()
    export_schema(cur)

    # 统计
    for table in ("regions", "channels", "categories", "users", "products", "orders", "order_items", "refunds"):
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        print(f"{table:12s}: {cur.fetchone()[0]:>5d} 行")
    conn.close()
    print(f"\n数据库已生成: {DB_PATH}")
    print(f"Schema 已导出: {SCHEMA_PATH}")


if __name__ == "__main__":
    main()
