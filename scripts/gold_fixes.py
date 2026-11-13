"""gold_sql 修复清单：集中维护，供修复脚本与复核表共用"""

# id -> 新 gold_sql
FIXES = {
    4: "select c.category_name, sum(p.stock) from products p join categories c on p.category_id = c.category_id group by c.category_name",
    15: "select sum(total_amount) / count(distinct order_id) from orders where status = '已完成'",
    25: "select p.product_name, sum(oi.quantity) from order_items oi join products p on oi.product_id = p.product_id join orders o on oi.order_id = o.order_id join channels c on o.channel_id = c.channel_id where c.channel_name = 'APP' group by p.product_name order by sum(oi.quantity) desc limit 1",
    26: "select p.product_name, sum(oi.quantity) from order_items oi join products p on oi.product_id = p.product_id join orders o on oi.order_id = o.order_id join users u on o.user_id = u.user_id where u.gender = '男' group by p.product_name order by sum(oi.quantity) desc limit 1",
    27: "select u.gender, count(distinct u.user_id) from users u join regions r on u.region_id = r.region_id where r.region_name = '华北' group by u.gender",
    28: "SELECT o.pay_type, SUM(r.refund_amount) * 1.0 / (SELECT SUM(o2.total_amount) FROM orders o2 WHERE o2.pay_type = o.pay_type AND substr(o2.order_time, 1, 7) = '2025-08') AS refund_ratio FROM orders o JOIN refunds r ON r.order_id = o.order_id WHERE substr(r.refund_time, 1, 7) = '2025-08' AND r.status = '已退款' GROUP BY o.pay_type",
    29: "select substr(o.order_time, 1, 7) as month, p.product_name, sum(oi.subtotal) from orders o join order_items oi on o.order_id = oi.order_id join products p on oi.product_id = p.product_id group by 1, 2",
    30: "select p.product_name, sum(r.refund_amount) from refunds r join order_items oi on r.order_id = oi.order_id join products p on oi.product_id = p.product_id group by p.product_name order by sum(r.refund_amount) desc limit 1",
    31: "select r.region_name, sum(oi.quantity) from order_items oi join orders o on oi.order_id = o.order_id join users u on o.user_id = u.user_id join regions r on u.region_id = r.region_id group by r.region_name order by sum(oi.quantity) desc limit 1",
    34: "select p.product_name, sum(r.refund_amount) from refunds r join order_items oi on r.order_id = oi.order_id join products p on oi.product_id = p.product_id where r.reason = '质量问题' group by p.product_name order by sum(r.refund_amount) desc limit 1",
    35: "select p.product_name, sum(oi.quantity) from order_items oi join products p on oi.product_id = p.product_id join categories c on p.category_id = c.category_id where c.category_name = '食品生鲜' group by p.product_name order by sum(oi.quantity) desc limit 1",
    36: "select case when u.age <= 18 then '未成年' when u.age <= 25 then '青年' when u.age <= 35 then '壮年' when u.age <= 45 then '中年' else '其他' end as ages, sum(o.total_amount) from orders o left join users u on o.user_id = u.user_id where o.status = '已完成' group by ages",
    38: "select case when u.age <= 18 then '未成年' when u.age <= 25 then '青年' when u.age <= 35 then '壮年' when u.age <= 45 then '中年' else '其他' end as ages, sum(o.total_amount) / count(distinct o.order_id) from orders o left join users u on o.user_id = u.user_id group by ages",
    42: "select avg(cnt) from (select o.user_id, count(distinct c.category_id) as cnt from orders o join order_items oi on o.order_id = oi.order_id join products p on oi.product_id = p.product_id join categories c on p.category_id = c.category_id group by o.user_id)",
    44: "select c.category_name, sum(r.refund_amount) from refunds r join order_items oi on r.order_id = oi.order_id join products p on oi.product_id = p.product_id join categories c on p.category_id = c.category_id where r.reason = '质量问题' group by c.category_name order by sum(r.refund_amount) desc limit 1",
    45: "select r.region_name, sum(oi.quantity) from order_items oi join products p on oi.product_id = p.product_id join categories c on p.category_id = c.category_id join orders o on o.order_id = oi.order_id join users u on o.user_id = u.user_id join regions r on u.region_id = r.region_id where c.category_name = '食品生鲜' group by r.region_name order by sum(oi.quantity) desc limit 1",
    46: "select o.pay_type, count(distinct re.refund_id) * 1.0 / count(distinct o.order_id) from orders o join users u on o.user_id = u.user_id join regions r on u.region_id = r.region_id left join refunds re on o.order_id = re.order_id and re.refund_time >= '2024-12-31' and re.refund_time < '2025-01-01' where r.region_name = '华东' group by o.pay_type",
    47: "SELECT c.channel_name, SUM(oi.quantity) FROM order_items oi join products p on oi.product_id = p.product_id left join orders o on oi.order_id = o.order_id left join channels c on o.channel_id = c.channel_id where p.category_id = 1 group by c.channel_name order by SUM(oi.quantity) desc limit 1",
    48: "select substr(o.order_time, 1, 7) as month, c.category_name, sum(oi.subtotal) from orders o join order_items oi on o.order_id = oi.order_id join products p on oi.product_id = p.product_id join categories c on p.category_id = c.category_id group by 1, 2",
}

# id -> (修改类型, 原因)
REASONS = {
    4: ("返回字段口径", "原来返回 category_id，问题问的是「品类」，改为返回 category_name（ID 和名称的等价性也让新指标能兼容）"),
    15: ("分母口径", "客单价 = 销售额 / 订单数，原来除以用户数，口径错误"),
    25: ("过滤失效 / 排序错误", "channel_name='APP' 写在 LEFT JOIN 的 ON 里，等于没过滤；ORDER BY oi.quantity 是明细列而非聚合值"),
    26: ("过滤失效 / 排序错误", "u.gender='男' 写在 JOIN ON 里，等于没过滤；排序用了明细列"),
    27: ("过滤失效", "region_name='华北' 写在 LEFT JOIN 的 ON 里，等于没过滤"),
    28: ("分母口径", "占比分母被退款 JOIN 收窄成「有退款的订单销售额」，改为该支付方式 8 月总销售额"),
    29: ("重复累加", "JOIN order_items 后 sum(total_amount) 被按明细行重复累加，改用 oi.subtotal"),
    30: ("排序错误", "ORDER BY p.product_id 应为按退款额排序"),
    31: ("排序错误", "ORDER BY oi.quantity 是明细列，应为 SUM(oi.quantity)"),
    34: ("过滤失效 / 排序错误", "质量问题的过滤写在 JOIN ON 里，等于没过滤"),
    35: ("过滤失效 / 排序错误", "品类过滤写在 JOIN ON 里，等于没过滤"),
    36: ("缺少聚合", "问题问销售额，原 SQL 没有 SUM 也没有 GROUP BY；已按业务口径只统计 status='已完成' 的订单"),
    38: ("缺少 GROUP BY / 分母口径", "原 SQL 缺 GROUP BY ages；客单价分母应为订单数"),
    42: ("去重口径", "品宽应为「用户购买的不同品类数」，原 SQL count(category_id) 未去重"),
    44: ("过滤失效 / 排序错误", "质量问题过滤写在 JOIN ON 里，等于没过滤"),
    45: ("过滤失效 / 排序错误", "品类过滤写在 JOIN ON 里，等于没过滤"),
    46: ("过滤失效 / 日期写法", "华东与日期过滤写在 JOIN ON 里；between 同一天匹配不到带时分秒的时间"),
    47: ("过滤失效 / 排序错误", "category_id 写在 channels 的 ON 里，没有过滤作用；排序用了明细列"),
    48: ("重复累加", "同 Q29，total_amount 被明细行重复累加，改用 subtotal"),
}
