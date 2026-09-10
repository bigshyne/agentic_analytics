"""
agentic_analytics_prototype.py
==============================

A single-question, end-to-end skeleton for the "explicit lists" agent loop:

    question
      -> agent picks {metrics, dimensions, filters}   (constrained tool call)
      -> validate against the model's OWN vocabulary   (illegal = declined)
      -> compile to SQL and run                        (Sidemantic + DuckDB)
      -> pick a chart from the query shape             (a rule, not the agent)
      -> score the three lists against a known target  (per-field pass/fail)

Run it in STUB mode first (no API key). Stub returns a canned query so you can
prove the Sidemantic half works on its own. Then flip to LIVE to test the agent.

    pip install sidemantic duckdb pandas anthropic
    AGENT_MODE=stub python agentic_analytics_prototype.py     # plumbing only
    AGENT_MODE=live ANTHROPIC_API_KEY=sk-... python agentic_analytics_prototype.py

TWO SEAMS marked `# SWAP` are the only things you change for your real setup:
  1. how the model is loaded (inline demo model -> your SML directory)
  2. the question/target pair (one here -> a list you loop over)
Everything between load and score is model-agnostic and stays as is.
"""

import json
import os

from sidemantic import SemanticLayer, Model, Dimension, Metric

# ----------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------
AGENT_MODE = os.environ.get("AGENT_MODE", "stub")   # "stub" or "live"

# Verify the current model string before a live run:
# https://docs.claude.com/en/docs/about-claude/models
MODEL = os.environ.get("AGENT_MODEL", "claude-sonnet-5")

FILTER_OPERATORS = ["=", "!=", "<", "<=", ">", ">=", "in"]


# ----------------------------------------------------------------------
# 1. Load the model.  # SWAP
#
# This inline model is a faithful stand-in for your SML: same metrics, same
# non-additive count-distinct, same asset_type dimension, and the billing rule
# baked INTO the metric (removed_at IS NULL) so the agent must not re-add it.
#
# For your real model, delete build_demo_layer() and use instead:
#     from sidemantic.loaders import load_from_directory
#     layer = SemanticLayer(connection="duckdb:///sample.duckdb")
#     load_from_directory(layer, "your-sml-dir/")
# (point the connection at a DuckDB file holding a sample of your data).
# The rest of this file does not change.
# ----------------------------------------------------------------------
SAMPLE_SQL = """
SELECT * FROM (
  SELECT 1 AS asset_id, 'reefer' AS asset_type, 'Acme Freight'   AS customer, NULL::DATE     AS removed_at, CURRENT_DATE - INTERVAL 3  DAY AS last_ping
  UNION ALL SELECT 2,'reefer','Acme Freight',   NULL,           CURRENT_DATE - INTERVAL 40 DAY
  UNION ALL SELECT 3,'reefer','Acme Freight',   DATE '2026-01-01', CURRENT_DATE - INTERVAL 5  DAY
  UNION ALL SELECT 4,'dry',   'Acme Freight',   NULL,           CURRENT_DATE - INTERVAL 2  DAY
  UNION ALL SELECT 5,'reefer','Bolt Logistics', NULL,           CURRENT_DATE - INTERVAL 10 DAY
  UNION ALL SELECT 6,'dry',   'Bolt Logistics', NULL,           CURRENT_DATE - INTERVAL 60 DAY
  UNION ALL SELECT 7,'reefer','Cargo Motors',   DATE '2025-12-01', CURRENT_DATE - INTERVAL 1  DAY
  UNION ALL SELECT 8,'reefer','Cargo Motors',   NULL,           CURRENT_DATE - INTERVAL 2  DAY
) t
"""


def build_demo_layer() -> SemanticLayer:
    layer = SemanticLayer()
    layer.add_model(Model(
        name="fleet",
        sql=SAMPLE_SQL,
        primary_key="asset_id",
        description="One row per device installation in a trailer (asset).",
        dimensions=[
            Dimension(name="asset_type", type="categorical", sql="asset_type",
                      description="Trailer type. One of: dry, reefer."),
            Dimension(name="customer", type="categorical", sql="customer",
                      description="Customer that owns the trailer."),
        ],
        metrics=[
            Metric(name="billable_assets", agg="count_distinct", sql="asset_id",
                   filters=["{model}.removed_at IS NULL"],
                   description=("Distinct trailers with a device installed right now. "
                                "This is the number the customer is billed for. "
                                "ALREADY limited to current installations. "
                                "Do NOT add an installed / removed filter.")),
            Metric(name="active_assets", agg="count_distinct", sql="asset_id",
                   filters=["{model}.removed_at IS NULL",
                            "{model}.last_ping >= CURRENT_DATE - INTERVAL 30 DAY"],
                   description=("Distinct trailers whose installed device pinged in the "
                                "last 30 days. ALREADY limited to installed AND recently "
                                "pinged. Do NOT add a date or installed filter.")),
        ],
    ))
    return layer


# ----------------------------------------------------------------------
# 2. Introspect the loaded model -> the agent's vocabulary.
# Built at runtime so it never drifts from the model definition.
# ----------------------------------------------------------------------
def build_catalog(layer: SemanticLayer):
    metric_refs, dim_refs = [], []
    dim_type = {}          # ref -> "categorical" | "time" | ...
    allowed_values = {}    # categorical ref -> [values]
    lines = []

    for model in layer.graph.models.values():
        lines.append(f"Model `{model.name}`: {model.description or ''}".rstrip())
        for met in model.metrics:
            ref = f"{model.name}.{met.name}"
            metric_refs.append(ref)
            lines.append(f"  metric    {ref} — {met.description or ''}".rstrip())
        for dim in model.dimensions:
            ref = f"{model.name}.{dim.name}"
            dim_refs.append(ref)
            dim_type[ref] = dim.type
            note = dim.description or ""
            if dim.type == "categorical":
                vals = [str(v) for v in
                        layer.query(dimensions=[ref]).fetchdf().iloc[:, 0].tolist()]
                allowed_values[ref] = vals
                note = (note + f" Allowed values: {vals}.").strip()
            lines.append(f"  dimension {ref} [{dim.type}] — {note}".rstrip())

    return {
        "metric_refs": metric_refs,
        "dim_refs": dim_refs,
        "dim_type": dim_type,
        "allowed_values": allowed_values,
        "text": "\n".join(lines),
    }


# ----------------------------------------------------------------------
# 3. The agent. Its ENTIRE output is the three-key object, and the tool
# schema constrains metric/dimension/attribute to the catalog enums, so it
# cannot name an object the model does not have.
# ----------------------------------------------------------------------
def build_tool(cat):
    return {
        "name": "emit_query",
        "description": "Answer the question by selecting semantic objects. "
                       "Do not write SQL. Do not add a filter that a chosen "
                       "metric already encodes (read the metric descriptions).",
        "input_schema": {
            "type": "object",
            "properties": {
                "metrics": {
                    "type": "array",
                    "items": {"type": "string", "enum": cat["metric_refs"]},
                },
                "dimensions": {
                    "type": "array",
                    "items": {"type": "string", "enum": cat["dim_refs"]},
                },
                "filters": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "attribute": {"type": "string", "enum": cat["dim_refs"]},
                            "operator": {"type": "string", "enum": FILTER_OPERATORS},
                            "value": {"type": "string"},
                        },
                        "required": ["attribute", "operator", "value"],
                    },
                },
            },
            "required": ["metrics", "dimensions", "filters"],
        },
    }


def ask_agent_live(question, cat):
    from anthropic import Anthropic  # imported only when actually used
    client = Anthropic()
    tool = build_tool(cat)
    system = ("You translate a business question into a semantic query for a "
              "governed model. Select only from the catalog below. Prefer the "
              "fewest objects that answer the question.\n\nCATALOG\n" + cat["text"])
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=system,
        tools=[tool],
        tool_choice={"type": "tool", "name": "emit_query"},
        messages=[{"role": "user", "content": question}],
    )
    for block in resp.content:
        if block.type == "tool_use" and block.name == "emit_query":
            return block.input
    raise RuntimeError("Model did not emit the emit_query tool call.")


def ask_agent_stub(question, cat):
    # Canned answer for the demo question, so you can test the loop with no API
    # key. Edit this to a WRONG answer to watch the scorer turn red.
    return {
        "metrics": ["fleet.billable_assets"],
        "dimensions": ["fleet.customer"],
        "filters": [{"attribute": "fleet.asset_type", "operator": "=", "value": "reefer"}],
    }


# ----------------------------------------------------------------------
# 4. Validate against the catalog. This is the "decline, don't hallucinate"
# gate: an out-of-vocabulary query is refused, never run.
# ----------------------------------------------------------------------
def validate(q, cat):
    errs = []
    for m in q["metrics"]:
        if m not in cat["metric_refs"]:
            errs.append(f"unknown metric: {m}")
    for d in q["dimensions"]:
        if d not in cat["dim_refs"]:
            errs.append(f"unknown dimension: {d}")
    for f in q["filters"]:
        a = f["attribute"]
        if a not in cat["dim_refs"]:
            errs.append(f"unknown filter attribute: {a}")
        elif a in cat["allowed_values"] and f["value"] not in cat["allowed_values"][a]:
            errs.append(f"value {f['value']!r} not valid for {a}; "
                        f"allowed {cat['allowed_values'][a]}")
    if not q["metrics"]:
        errs.append("a query needs at least one metric")
    return errs


def compile_filters(filters):
    out = []
    for f in filters:
        a, op, v = f["attribute"], f["operator"], f["value"]
        if op.lower() == "in":
            out.append(f"{a} IN ({v})")
        else:
            out.append(f"{a} {op} '{v}'")
    return out


# ----------------------------------------------------------------------
# 5. Chart from the query shape. A rule, so it is never an agent error.
# ----------------------------------------------------------------------
def pick_chart(q, cat):
    dims = q["dimensions"]
    if not dims:
        return "single_number"
    if len(dims) == 1:
        return "line" if cat["dim_type"].get(dims[0]) == "time" else "bar"
    if len(dims) == 2:
        return "grouped_bar"
    return "table"


# ----------------------------------------------------------------------
# 6. Score: set-compare metrics and dimensions, field-compare filters.
# ----------------------------------------------------------------------
def _norm_filter(f):
    return (f["attribute"], f["operator"].lower(), str(f["value"]).lower())


def score(agent, target):
    r = {
        "metrics": set(agent["metrics"]) == set(target["metrics"]),
        "dimensions": set(agent["dimensions"]) == set(target["dimensions"]),
        "filters": {_norm_filter(x) for x in agent["filters"]}
                    == {_norm_filter(x) for x in target["filters"]},
    }
    r["overall"] = all(r.values())
    return r


# ----------------------------------------------------------------------
# Run one question end to end.
# ----------------------------------------------------------------------
def main():
    # SWAP: one question/target pair here; in the real eval this is a list.
    QUESTION = "How many reefers is each customer billed for?"
    TARGET = {
        "metrics": ["fleet.billable_assets"],
        "dimensions": ["fleet.customer"],
        "filters": [{"attribute": "fleet.asset_type", "operator": "=", "value": "reefer"}],
    }

    layer = build_demo_layer()
    cat = build_catalog(layer)

    print("=" * 70)
    print("CATALOG (this is the agent's whole world)\n")
    print(cat["text"])
    print("\n" + "=" * 70)
    print(f"QUESTION: {QUESTION}\n")

    agent = (ask_agent_stub if AGENT_MODE == "stub" else ask_agent_live)(QUESTION, cat)
    print(f"AGENT ({AGENT_MODE}) emitted:")
    print(json.dumps(agent, indent=2))

    errs = validate(agent, cat)
    if errs:
        print("\nDECLINED. Query is not runnable:")
        for e in errs:
            print("  -", e)
        return

    filters = compile_filters(agent["filters"])
    sql = layer.compile(metrics=agent["metrics"], dimensions=agent["dimensions"],
                        filters=filters)
    print("\nCOMPILED SQL (deterministic, from the model):\n")
    print(sql)

    df = layer.query(metrics=agent["metrics"], dimensions=agent["dimensions"],
                     filters=filters).fetchdf()
    print("\nRESULT:\n")
    print(df.to_string(index=False))

    print(f"\nCHART: {pick_chart(agent, cat)}")

    s = score(agent, TARGET)
    print("\nSCORE vs target")
    for k in ("metrics", "dimensions", "filters"):
        print(f"  {k:<11} {'PASS' if s[k] else 'FAIL'}")
    print(f"  {'OVERALL':<11} {'PASS' if s['overall'] else 'FAIL'}")


if __name__ == "__main__":
    main()
