"""
The actual point of the exercise: can an LLM agent answer a business question
against the fragmented Brightcart schema *without ever seeing the fragmentation*?

Step 1 prints exactly what the agent is given as context: a flat catalog of
models/dimensions/metrics, no SQL, no table names, no join logic.

Step 2 hands that catalog to Claude as a tool ("query_semantic_layer") and lets
it answer a real natural-language question by calling the tool itself.
"""

import json
import os

from anthropic import Anthropic
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

# ---------------------------------------------------------------------------
# Step 1: build the catalog the agent is allowed to see. Deliberately excludes
# sql/table/relationships internals -- just names + descriptions, the same
# thing a person would get from a data dictionary.
# ---------------------------------------------------------------------------
catalog = []
for model_name, model in layer.graph.models.items():
    catalog.append({
        "model": model_name,
        "description": model.description,
        "dimensions": [
            {"name": d.name, "description": d.description} for d in model.dimensions
        ],
        "metrics": [
            {"name": m.name, "description": m.description} for m in model.metrics
        ],
    })

print("=== Catalog exposed to the agent (no SQL, no tables, no joins) ===")
print(json.dumps(catalog, indent=2))

# ---------------------------------------------------------------------------
# Step 2: let Claude answer a real question by calling the semantic layer
# as a tool. Claude only ever sees model/dimension/metric names.
# ---------------------------------------------------------------------------
TOOL_NAME = "query_semantic_layer"

tool_schema = {
    "name": TOOL_NAME,
    "description": (
        "Run a query against the semantic layer. Reference dimensions/metrics "
        "as '<model>.<field>', e.g. 'customer.first_name' or 'orders.order_count'."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "metrics": {"type": "array", "items": {"type": "string"}},
            "dimensions": {"type": "array", "items": {"type": "string"}},
            "limit": {"type": "integer", "description": "Max rows to return."},
        },
        "required": ["metrics"],
    },
}


def run_tool(tool_input: dict) -> str:
    df = layer.query(
        metrics=tool_input.get("metrics", []),
        dimensions=tool_input.get("dimensions", []),
    ).fetchdf()
    limit = tool_input.get("limit")
    if limit:
        df = df.head(limit)
    return df.to_csv(index=False)


client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

system_prompt = (
    "You are a data analyst. You can only see the following catalog of "
    "models, dimensions, and metrics -- you have no knowledge of the "
    "underlying database schema, tables, or joins:\n\n"
    + json.dumps(catalog, indent=2)
    + "\n\nUse the query_semantic_layer tool to answer questions. Always "
    "reference fields as '<model>.<field>'."
)

question = "Which 5 customers have placed the most orders? Show their name, email, and account status."

print()
print("=== Question ===")
print(question)

messages = [{"role": "user", "content": question}]

while True:
    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=1024,
        system=system_prompt,
        tools=[tool_schema],
        messages=messages,
    )

    messages.append({"role": "assistant", "content": response.content})

    if response.stop_reason != "tool_use":
        print()
        print("=== Claude's answer ===")
        for block in response.content:
            if block.type == "text":
                print(block.text)
        break

    tool_results = []
    for block in response.content:
        if block.type == "tool_use" and block.name == TOOL_NAME:
            print()
            print(f"=== Claude called {TOOL_NAME} with: {block.input} ===")
            try:
                result = run_tool(block.input)
            except Exception as e:
                result = f"ERROR: {e}"
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result,
            })

    messages.append({"role": "user", "content": tool_results})
