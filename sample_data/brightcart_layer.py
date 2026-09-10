"""
Shared setup: the Brightcart semantic layer plus the tool contract an LLM
agent uses to query it. Imported by both the scripted test (agent_test.py)
and the Streamlit chat UI (app.py) so there's one definition of the catalog.
"""

from sidemantic import SemanticLayer, Model, Dimension, Metric, Relationship, Segment
from sidemantic.db.duckdb import DuckDBAdapter

CUSTOMER_SQL = """
SELECT
    a.account_id,
    a.status_code,
    a.inception_date,
    p.party_type_code AS customer_type,
    pn.first_name,
    pn.last_name,
    CASE
        WHEN p.party_type_code = 'organization' THEN pod.legal_name
        ELSE pn.first_name || ' ' || pn.last_name
    END AS display_name,
    pid.gender_code,
    pid.date_of_birth,
    pod.company_type_code,
    pod.industry_code,
    pod.employee_count_band,
    pc.contact_value AS email
FROM account a
JOIN account_party ap ON ap.account_id = a.account_id AND ap.role_code = 'primary_holder'
JOIN party p ON p.party_id = ap.party_id
LEFT JOIN party_name pn ON pn.party_id = p.party_id AND pn.end_date IS NULL
LEFT JOIN party_individual_detail pid ON pid.party_id = p.party_id
LEFT JOIN party_organization_detail pod ON pod.party_id = p.party_id
LEFT JOIN party_contact pc ON pc.party_id = p.party_id AND pc.contact_type = 'email'
"""

# Raw OLTP tables already accounted for in the models below -- either joined
# into a model's SQL, or an enum table whose meaning has been reviewed and
# baked into a Dimension's description. bootstrap_new_tables.py treats
# anything NOT in this set as a candidate for a fresh draft model, so update
# this whenever a table gets folded into build_layer() below.
MODELED_TABLES = frozenset({
    # customer
    "account", "account_status", "account_party", "account_party_role",
    "party", "party_type", "party_name",
    "party_individual_detail", "gender",
    "party_organization_detail", "company_type", "industry",
    "party_contact",
    # orders
    "orders",
    # product
    "item", "item_status", "item_descriptor", "item_price",
    "item_category_xref", "product_categories",
    # subscriptions
    "subscriptions", "subscription_plans", "subscription_events",
    # payments
    "payments", "refunds",
})

PRODUCT_SQL = """
SELECT
    i.item_id,
    i.status_code,
    idesc.name,
    idesc.description,
    iprice.price,
    iprice.currency_code,
    pcat.category_name
FROM item i
LEFT JOIN item_descriptor idesc ON idesc.item_id = i.item_id AND idesc.end_date IS NULL
LEFT JOIN item_price iprice ON iprice.item_id = i.item_id AND iprice.end_date IS NULL
LEFT JOIN item_category_xref icx ON icx.item_id = i.item_id
LEFT JOIN product_categories pcat ON pcat.category_id = icx.category_id
"""

SUBSCRIPTION_SQL = """
SELECT
    s.subscription_id,
    s.account_id,
    s.status,
    s.start_date,
    s.end_date,
    sp.plan_name,
    sp.billing_interval,
    -- subscription_plans.monthly_price is misleading for annual plans (it's
    -- the per-billing-period price, not a monthly one) -- normalize here so
    -- every downstream metric sums like-for-like.
    CASE WHEN sp.billing_interval = 'annual' THEN sp.monthly_price / 12 ELSE sp.monthly_price END
        AS normalized_monthly_price
FROM subscriptions s
LEFT JOIN subscription_plans sp ON sp.plan_id = s.plan_id
"""

PAYMENT_SQL = """
SELECT
    p.payment_id,
    p.order_id,
    p.payment_date,
    p.amount,
    p.payment_method,
    p.status,
    r.refund_date,
    r.amount AS refund_amount,
    r.reason AS refund_reason
FROM payments p
LEFT JOIN refunds r ON r.payment_id = p.payment_id
"""


def build_layer() -> SemanticLayer:
    layer = SemanticLayer(connection=DuckDBAdapter("brightcart_fragmented.duckdb"))

    layer.add_model(Model(
        name="customer",
        sql=CUSTOMER_SQL,
        primary_key="account_id",
        description=("The account holder -- either a person or a company. Assembled from "
                      "account + account_party (primary_holder) + party, then either "
                      "party_name + party_individual_detail (for a person) or "
                      "party_organization_detail (for a company) + party_contact. There is "
                      "no single 'customers' table in the source data, and a given customer "
                      "is never both a person and a company."),
        dimensions=[
            Dimension(name="status_code", type="categorical", sql="status_code",
                       description="Account status: active, suspended, closed, pending."),
            Dimension(name="customer_type", type="categorical", sql="customer_type",
                       description="'individual' (a person) or 'organization' (a company). "
                                    "Determines which other fields are populated: individuals "
                                    "have first_name/last_name/gender_code/date_of_birth; "
                                    "organizations have company_type_code/industry_code/"
                                    "employee_count_band. display_name works for both."),
            Dimension(name="display_name", type="categorical", sql="display_name",
                       description="Customer's name regardless of type: 'First Last' for an "
                                    "individual, the legal company name for an organization. "
                                    "Use this instead of first_name/last_name unless you "
                                    "specifically need a person's name parts."),
            Dimension(name="first_name", type="categorical", sql="first_name",
                       description="Only set for individual customers; null for organizations."),
            Dimension(name="last_name", type="categorical", sql="last_name",
                       description="Only set for individual customers; null for organizations."),
            Dimension(name="email", type="categorical", sql="email"),
            Dimension(name="inception_date", type="time", sql="inception_date", granularity="day",
                       description=("Date the account was opened -- i.e. when this customer "
                                     "became a customer. Use '__month', '__year', etc. suffixes "
                                     "(e.g. customer.inception_date__month) to group/filter by "
                                     "period, such as counting new customers in a given month.")),
            Dimension(name="gender_code", type="categorical", sql="gender_code",
                       description="Only set for individual customers: male, female, "
                                    "non_binary, or prefer_not_to_say. Null for organizations."),
            Dimension(name="date_of_birth", type="time", sql="date_of_birth", granularity="day",
                       description="Only set for individual customers. Use '__year' to group "
                                    "by birth year (e.g. for generational analysis)."),
            Dimension(name="company_type_code", type="categorical", sql="company_type_code",
                       description="Only set for organization customers: llc, corporation, "
                                    "partnership, sole_proprietorship, or nonprofit. Null for "
                                    "individuals."),
            Dimension(name="industry_code", type="categorical", sql="industry_code",
                       description="Only set for organization customers: retail, technology, "
                                    "healthcare, manufacturing, professional_services, or "
                                    "other. Null for individuals."),
            Dimension(name="employee_count_band", type="categorical", sql="employee_count_band",
                       description="Only set for organization customers: 1-9, 10-49, 50-249, "
                                    "250-999, or 1000+. Null for individuals."),
        ],
        segments=[
            Segment(name="active_customers", sql="status_code = 'active'",
                    description="The one governed definition of 'active': status_code = 'active'."),
            Segment(name="churned_customers", sql="status_code = 'closed'",
                    description="The one governed definition of 'churned': status_code = 'closed'."),
            Segment(name="individual_customers", sql="customer_type = 'individual'",
                    description="Customers who are a person rather than a company."),
            Segment(name="organization_customers", sql="customer_type = 'organization'",
                    description="Customers who are a company rather than a person."),
        ],
        metrics=[
            Metric(name="customer_count", agg="count_distinct", sql="account_id",
                   description="Number of distinct customer accounts."),
            # Kept in sync with the active_customers segment above -- same condition,
            # expressed here as a measure so it can feed the ratio metric below.
            Metric(name="active_customer_count", agg="count_distinct", sql="account_id",
                   filters=["status_code = 'active'"],
                   description="Number of distinct customers currently active."),
            Metric(name="active_customer_rate", type="ratio",
                   numerator="active_customer_count", denominator="customer_count",
                   value_format_name="percent",
                   description="Governed metric: share of all customers who are currently "
                                "active (active_customer_count / customer_count)."),
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
            Dimension(name="order_date", type="time", sql="order_date", granularity="day",
                       description=("Date/time the order was placed. Use '__month', '__year', "
                                     "etc. suffixes (e.g. orders.order_date__month) to group or "
                                     "filter by period.")),
        ],
        metrics=[
            Metric(name="order_count", agg="count_distinct", sql="order_id"),
        ],
    ))

    layer.add_model(Model(
        name="product",
        sql=PRODUCT_SQL,
        primary_key="item_id",
        description=("An item Brightcart sells. Assembled from item (hub) + item_descriptor "
                      "(current name/description) + item_price (current price) + "
                      "item_category_xref/product_categories (category). There is no single "
                      "'products' table in the source data."),
        dimensions=[
            Dimension(name="status_code", type="categorical", sql="status_code",
                       description="Product status: active, discontinued, or draft."),
            Dimension(name="name", type="categorical", sql="name"),
            Dimension(name="category_name", type="categorical", sql="category_name",
                       description="Product's subcategory (e.g. Cookware, Audio)."),
            Dimension(name="currency_code", type="categorical", sql="currency_code"),
        ],
        segments=[
            Segment(name="active_products", sql="status_code = 'active'",
                    description="The one governed definition of an active product."),
            Segment(name="discontinued_products", sql="status_code = 'discontinued'",
                    description="The one governed definition of a discontinued product."),
        ],
        metrics=[
            Metric(name="product_count", agg="count_distinct", sql="item_id",
                   description="Number of distinct products."),
            Metric(name="average_price", agg="avg", sql="price",
                   description="Average current list price across products."),
        ],
    ))

    layer.add_model(Model(
        name="subscriptions",
        sql=SUBSCRIPTION_SQL,
        primary_key="subscription_id",
        relationships=[
            Relationship(name="customer", type="many_to_one", foreign_key="account_id", primary_key="account_id"),
        ],
        description=("A customer's subscription to a plan. Assembled from subscriptions "
                      "(hub) + subscription_plans (plan name, billing interval, price). "
                      "normalized_monthly_price adjusts annual plans to a monthly-equivalent "
                      "price so revenue metrics aren't skewed by billing interval."),
        dimensions=[
            Dimension(name="status", type="categorical", sql="status",
                       description="Subscription status: active, cancelled, or trialing."),
            Dimension(name="start_date", type="time", sql="start_date", granularity="day"),
            Dimension(name="end_date", type="time", sql="end_date", granularity="day",
                       description="Null while the subscription is active."),
            Dimension(name="plan_name", type="categorical", sql="plan_name"),
            Dimension(name="billing_interval", type="categorical", sql="billing_interval",
                       description="monthly or annual."),
        ],
        segments=[
            Segment(name="active_subscriptions", sql="status = 'active'",
                    description="The one governed definition of an active subscription."),
            Segment(name="cancelled_subscriptions", sql="status = 'cancelled'",
                    description="The one governed definition of a cancelled subscription."),
            Segment(name="trialing_subscriptions", sql="status = 'trialing'",
                    description="The one governed definition of a subscription still in trial."),
        ],
        metrics=[
            Metric(name="subscription_count", agg="count_distinct", sql="subscription_id",
                   description="Number of distinct subscriptions."),
            Metric(name="cancelled_subscription_count", agg="count_distinct", sql="subscription_id",
                   filters=["status = 'cancelled'"],
                   description="Number of distinct cancelled subscriptions."),
            Metric(name="subscription_churn_rate", type="ratio",
                   numerator="cancelled_subscription_count", denominator="subscription_count",
                   value_format_name="percent",
                   description="Governed metric: share of all subscriptions ever cancelled "
                                "(cancelled_subscription_count / subscription_count)."),
            Metric(name="mrr", agg="sum", sql="normalized_monthly_price",
                   filters=["status = 'active'"], value_format_name="usd",
                   description="Governed metric: monthly recurring revenue. Active "
                                "subscriptions only, annual plans normalized to their "
                                "monthly-equivalent price -- never sum raw monthly_price "
                                "across mixed billing intervals."),
        ],
    ))

    layer.add_model(Model(
        name="subscription_events",
        table="subscription_events",
        primary_key="event_id",
        relationships=[
            Relationship(name="subscriptions", type="many_to_one",
                         foreign_key="subscription_id", primary_key="subscription_id"),
        ],
        description="A lifecycle event on a subscription: created, upgraded, downgraded, renewed, or cancelled.",
        dimensions=[
            Dimension(name="event_type", type="categorical", sql="event_type"),
            Dimension(name="event_date", type="time", sql="event_date", granularity="day"),
        ],
        metrics=[
            Metric(name="event_count", agg="count_distinct", sql="event_id",
                   description="Number of distinct subscription lifecycle events."),
        ],
    ))

    layer.add_model(Model(
        name="payments",
        sql=PAYMENT_SQL,
        primary_key="payment_id",
        relationships=[
            Relationship(name="orders", type="many_to_one", foreign_key="order_id", primary_key="order_id"),
        ],
        description=("A payment against an order. Assembled from payments (hub) + refunds "
                      "(a payment has at most one refund in this data). refund_amount/"
                      "refund_reason/refund_date are null when the payment was never "
                      "refunded."),
        dimensions=[
            Dimension(name="status", type="categorical", sql="status",
                       description="Payment status: completed or refunded."),
            Dimension(name="payment_method", type="categorical", sql="payment_method"),
            Dimension(name="payment_date", type="time", sql="payment_date", granularity="day"),
            Dimension(name="refund_reason", type="categorical", sql="refund_reason",
                       description="Null unless the payment was refunded."),
        ],
        segments=[
            Segment(name="completed_payments", sql="status = 'completed'",
                    description="The one governed definition of a completed (non-refunded) payment."),
            Segment(name="refunded_payments", sql="status = 'refunded'",
                    description="The one governed definition of a refunded payment."),
        ],
        metrics=[
            Metric(name="payment_count", agg="count_distinct", sql="payment_id",
                   description="Number of distinct payments."),
            Metric(name="gross_amount", agg="sum", sql="amount", value_format_name="usd",
                   description="Total amount collected, before refunds."),
            Metric(name="refund_amount", agg="sum", sql="refund_amount", value_format_name="usd",
                   description="Total amount refunded."),
            Metric(name="net_revenue", type="derived", sql="gross_amount - refund_amount",
                   value_format_name="usd",
                   description="Governed metric: net revenue after refunds "
                                "(gross_amount - refund_amount). Use this, not gross_amount, "
                                "when the question is about actual revenue."),
        ],
    ))

    return layer


def build_catalog(layer: SemanticLayer) -> list[dict]:
    """Flat model/dimension/metric/segment names + descriptions -- no SQL, no tables, no joins."""
    catalog = []
    for model_name, model in layer.graph.models.items():
        catalog.append({
            "model": model_name,
            "description": model.description,
            "dimensions": [{"name": d.name, "description": d.description} for d in model.dimensions],
            "metrics": [{"name": m.name, "description": m.description} for m in model.metrics],
            "segments": [{"name": s.name, "description": s.description} for s in model.segments],
        })
    return catalog


TOOL_NAME = "query_semantic_layer"

TOOL_SCHEMA = {
    "name": TOOL_NAME,
    "description": (
        "Run a query against the semantic layer. Reference dimensions/metrics "
        "as '<model>.<field>', e.g. 'customer.first_name' or 'orders.order_count'. "
        "For time dimensions, append '__<granularity>' (day/week/month/quarter/year) "
        "to group or filter by period, e.g. 'customer.inception_date__month'. "
        "order_by entries use the same '<model>.<field>' names, optionally suffixed "
        "with ' desc' or ' asc' (default asc). segments are named, governed filters "
        "-- e.g. 'customer.active_customers' -- prefer one of these over writing an "
        "equivalent ad-hoc filter whenever the catalog lists a matching segment, so "
        "terms like 'active' or 'churned' stay consistent across every answer. "
        "filters are for anything NOT covered by a segment: SQL boolean expressions "
        "over '<model>.<field>' names, e.g. \"customer.inception_date >= '2025-08-01' "
        "AND customer.inception_date < '2025-09-01'\"."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "metrics": {"type": "array", "items": {"type": "string"}},
            "dimensions": {"type": "array", "items": {"type": "string"}},
            "segments": {"type": "array", "items": {"type": "string"}},
            "filters": {"type": "array", "items": {"type": "string"}},
            "order_by": {"type": "array", "items": {"type": "string"}},
            "limit": {"type": "integer", "description": "Max rows to return."},
        },
        "required": ["metrics"],
    },
}


def compile_sql(layer: SemanticLayer, tool_input: dict) -> str:
    return layer.compile(
        metrics=tool_input.get("metrics", []),
        dimensions=tool_input.get("dimensions", []),
        segments=tool_input.get("segments") or None,
        filters=tool_input.get("filters") or None,
        order_by=tool_input.get("order_by") or None,
        limit=tool_input.get("limit"),
    )


def run_query(layer: SemanticLayer, tool_input: dict):
    """Returns a pandas DataFrame."""
    return layer.query(
        metrics=tool_input.get("metrics", []),
        dimensions=tool_input.get("dimensions", []),
        segments=tool_input.get("segments") or None,
        filters=tool_input.get("filters") or None,
        order_by=tool_input.get("order_by") or None,
        limit=tool_input.get("limit"),
    ).fetchdf()


CHART_TOOL_NAME = "visualize_semantic_layer"

CHART_TOOL_SCHEMA = {
    "name": CHART_TOOL_NAME,
    "description": (
        "Render a chart from the semantic layer for the user to see. Use this "
        "whenever the user asks to visualize, plot, chart, graph, or 'show' data, "
        "or when a trend/comparison is clearer as a picture than a table. Same "
        "field-referencing rules as query_semantic_layer (model.field, "
        "__granularity suffixes on time dimensions, SQL boolean filters). "
        "'dimensions' here means what to chart BY (x-axis, and a second one for "
        "series/color if given) -- usually 1-2 fields. mark='auto' picks a "
        "sensible chart type from the data shape (e.g. line for a time series, "
        "bar for a category breakdown); set it explicitly to override. Prefer a "
        "named segment (e.g. 'customer.active_customers') over an equivalent "
        "ad-hoc filter when the catalog lists one."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "metrics": {"type": "array", "items": {"type": "string"}},
            "dimensions": {"type": "array", "items": {"type": "string"}},
            "segments": {"type": "array", "items": {"type": "string"}},
            "filters": {"type": "array", "items": {"type": "string"}},
            "order_by": {"type": "array", "items": {"type": "string"}},
            "mark": {
                "type": "string",
                "enum": ["auto", "bar", "line", "area", "scatter", "point"],
            },
            "title": {"type": "string"},
            "limit": {"type": "integer"},
        },
        "required": ["metrics"],
    },
}


def build_chart(layer: SemanticLayer, tool_input: dict):
    """Returns (vega_lite_spec: dict, rows: list[dict], sql: str)."""
    chart = layer.chart(
        tool_input.get("metrics", []),
        by=tool_input.get("dimensions") or None,
        mark=tool_input.get("mark", "auto"),
        segments=tool_input.get("segments") or None,
        filters=tool_input.get("filters") or None,
        order_by=tool_input.get("order_by") or None,
        limit=tool_input.get("limit"),
        title=tool_input.get("title"),
    )
    data = chart.data()
    return chart.to_vegalite(), data.rows, data.sql
