"""
Quick validation: does Sidemantic correctly resolve the hub-and-satellite
fragmentation into a clean 'customer' entity, and can it join that entity
into 'orders' via a declared relationship?
"""

from sidemantic import SemanticLayer, Model, Dimension, Metric, Relationship
from sidemantic.db.duckdb import DuckDBAdapter

CUSTOMER_SQL = """
SELECT
    a.account_id,
    a.status_code,
    a.inception_date,
    pn.first_name,
    pn.last_name,
    pc.contact_value AS email
FROM account a
JOIN account_party ap ON ap.account_id = a.account_id AND ap.role_code = 'primary_holder'
JOIN party p ON p.party_id = ap.party_id
JOIN party_name pn ON pn.party_id = p.party_id AND pn.end_date IS NULL
LEFT JOIN party_contact pc ON pc.party_id = p.party_id AND pc.contact_type = 'email'
"""

layer = SemanticLayer(connection=DuckDBAdapter("brightcart_fragmented.duckdb"))

layer.add_model(Model(
    name="customer",
    sql=CUSTOMER_SQL,
    primary_key="account_id",
    description=("A person who holds a Brightcart account. Assembled from "
                  "account + account_party (primary_holder) + party + party_name "
                  "(current row only) + party_contact. There is no single "
                  "'customers' table in the source data."),
    dimensions=[
        Dimension(name="status_code", type="categorical", sql="status_code",
                   description="Account status: active, suspended, closed, pending."),
        Dimension(name="first_name", type="categorical", sql="first_name"),
        Dimension(name="last_name", type="categorical", sql="last_name"),
        Dimension(name="email", type="categorical", sql="email"),
    ],
    metrics=[
        Metric(name="customer_count", agg="count_distinct", sql="account_id",
               description="Number of distinct customer accounts."),
    ],
))

layer.add_model(Model(
    name="orders",
    table="orders",
    primary_key="order_id",
    relationships=[
        Relationship(name="customer", type="many_to_one", foreign_key="account_id", primary_key="account_id"),
    ],
    dimensions=[
        Dimension(name="status", type="categorical", sql="status"),
    ],
    metrics=[
        Metric(name="order_count", agg="count_distinct", sql="order_id"),
    ],
))

print("=== Compiled SQL for: order_count by customer, top 5 ===")
sql = layer.compile(
    metrics=["orders.order_count"],
    dimensions=["customer.first_name", "customer.last_name", "customer.email", "customer.status_code"],
)
print(sql)

print()
print("=== Result ===")
df = layer.query(
    metrics=["orders.order_count"],
    dimensions=["customer.first_name", "customer.last_name", "customer.email", "customer.status_code"],
).fetchdf()
df = df.sort_values("order_count", ascending=False).head(5)
print(df.to_string(index=False))
