CREATE TABLE categories (
            category_id   INTEGER PRIMARY KEY,
            category_name TEXT NOT NULL
        )

CREATE TABLE channels (
            channel_id   INTEGER PRIMARY KEY,
            channel_name TEXT NOT NULL
        )

CREATE TABLE order_items (
            item_id     INTEGER PRIMARY KEY,
            order_id    INTEGER,
            product_id  INTEGER,
            quantity    INTEGER NOT NULL,
            unit_price  REAL NOT NULL,
            subtotal    REAL NOT NULL,
            FOREIGN KEY (order_id)   REFERENCES orders(order_id),
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        )

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
        )

CREATE TABLE products (
            product_id   INTEGER PRIMARY KEY,
            product_name TEXT NOT NULL,
            category_id  INTEGER,
            price        REAL NOT NULL,
            stock        INTEGER DEFAULT 0,
            FOREIGN KEY (category_id) REFERENCES categories(category_id)
        )

CREATE TABLE refunds (
            refund_id    INTEGER PRIMARY KEY,
            order_id     INTEGER,
            refund_time  TEXT NOT NULL,
            refund_amount REAL NOT NULL,
            reason       TEXT,
            status       TEXT DEFAULT '已退款',
            FOREIGN KEY (order_id) REFERENCES orders(order_id)
        )

CREATE TABLE regions (
            region_id   INTEGER PRIMARY KEY,
            region_name TEXT NOT NULL
        )

CREATE TABLE users (
            user_id     INTEGER PRIMARY KEY,
            user_name   TEXT NOT NULL,
            gender      TEXT,
            age         INTEGER,
            region_id   INTEGER,
            register_date TEXT,
            FOREIGN KEY (region_id) REFERENCES regions(region_id)
        )
