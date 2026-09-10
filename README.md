# Agentic Analytics

Prototypes exploring how an LLM agent should query a business's data: through a
governed semantic layer (Sidemantic + DuckDB), never raw SQL against raw tables.

## sample_data/ -- Brightcart semantic layer + chat app

The main project. "Brightcart" is a synthetic e-commerce/subscription business
modeled as a realistic, heavily-normalized OLTP schema (hub-and-satellite
tables, enum/lookup tables, no single `customers` or `products` table) --
`generate_brightcart_fragmented.py` generates ~4 years of history (Jan 2023 to
today) into a DuckDB file.

`brightcart_layer.py` builds a [Sidemantic](https://github.com/sidemantic/sidemantic)
semantic layer on top of that fragmented schema: models for `customer`,
`orders`, `product`, `subscriptions`, `subscription_events`, and `payments`,
each with governed dimensions, metrics (including ratio/derived metrics like
`active_customer_rate` and `net_revenue`), and segments (`active_customers`,
`churned_customers`, etc.) -- the agent only ever sees this governed vocabulary,
never the underlying tables or joins.

`app.py` is a Streamlit chat UI: ask a question in plain English and watch
Claude interpret it, call the semantic layer (or a chart tool), and answer --
with an "Explore this data" panel on every result to keep pivoting (more
columns, filters, a chart) still entirely through the governed layer.

`bootstrap_new_tables.py` is the onboarding workflow for new OLTP tables: it
introspects the live database, skips anything already listed in
`MODELED_TABLES` (in `brightcart_layer.py`), and drafts a starter model per
new table into `models/*.yml` for a human to review and fold in.

### Run it

```bash
python -m venv .venv
.venv/Scripts/pip install sidemantic duckdb pandas anthropic streamlit faker pyyaml

cd sample_data
python generate_brightcart_fragmented.py        # writes brightcart_fragmented.duckdb
ANTHROPIC_API_KEY=sk-... ../.venv/Scripts/streamlit run app.py
```

Other scripts in `sample_data/`:
- `agent_test.py` -- scripted, non-interactive version of the same agent loop (no UI)
- `test_semantic_layer.py` -- quick check that the fragmented schema resolves correctly
- `generate_brightcart.py` -- an earlier, un-fragmented (flatter) version of the schema

## Earlier prototypes (repo root)

- `agentic_analytics_prototype.py` -- single-question skeleton for the
  "explicit lists" agent loop: question -> agent picks
  `{metrics, dimensions, filters}` -> validated against the model's own
  vocabulary -> compiled to SQL and run -> chart picked by a rule, not the
  agent -> scored against a known target. Has a stub mode (no API key needed)
  to test the Sidemantic plumbing on its own.
- `query_bench.py` -- a small Flask UI on top of the prototype: ask a
  question, watch the agent's steps, verify each answer, and build up an
  answer key in `verifications.jsonl`.

Both predate the Brightcart work in `sample_data/` and use a simpler,
unfragmented schema.
