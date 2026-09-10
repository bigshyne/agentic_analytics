"""
One-command starting point for onboarding new tables into the semantic layer.

Run this whenever the OLTP database gains a table that isn't represented in
brightcart_layer.py yet. It introspects the live schema, skips anything
already listed in MODELED_TABLES there, and writes a draft model -- inferred
primary key, dimension types, FK-based relationships, generic metrics -- to
models/*.yml for each new table, using sidemantic's own model-inference logic
(sidemantic.bootstrap.generate_model_dict, the same code behind
`sidemantic init --from`).

This is deliberately NOT the last step. A draft doesn't know your business
vocabulary: whether a table is its own model or a satellite that should merge
into an existing hub-and-satellite model (the way item_descriptor/item_price
merged into `product`), what "active" should mean, or what the table is even
for. A human reviews each draft, writes a real description, adds segments/
governed metrics for named business terms, then folds it into build_layer()
and adds its table(s) to MODELED_TABLES -- at which point re-running this
script no longer flags it.

Re-running is safe: a table with an existing (possibly hand-edited) draft in
models/ is left alone, not overwritten. Delete the file to regenerate it.

Run:
    .venv/Scripts/python.exe sample_data/bootstrap_new_tables.py
"""

from pathlib import Path

import yaml
from sidemantic.bootstrap import ColumnInfo, TableInfo, generate_model_dict
from sidemantic.db.duckdb import DuckDBAdapter

from brightcart_layer import MODELED_TABLES

DB_PATH = "brightcart_fragmented.duckdb"
MODELS_DIR = Path(__file__).parent / "models"
_EXCLUDED_SCHEMAS = ("information_schema", "pg_catalog", "system", "temp")


def introspect(con) -> list[TableInfo]:
    excluded = ", ".join(f"'{s}'" for s in _EXCLUDED_SCHEMAS)
    rows = con.execute(
        "select table_name, column_name, data_type from information_schema.columns "
        f"where lower(table_schema) not in ({excluded}) order by table_name, ordinal_position"
    ).fetchall()
    tables: dict[str, TableInfo] = {}
    for table_name, column_name, data_type in rows:
        info = tables.setdefault(table_name, TableInfo(name=table_name))
        info.columns.append(ColumnInfo(name=column_name, data_type=str(data_type)))
    return list(tables.values())


def profile(con, table: TableInfo) -> None:
    """Row/distinct counts -- lets generate_model_dict tell a categorical column
    from a free-text one. Best-effort: skipped if it fails for any reason."""
    try:
        table.row_count = con.execute(f'select count(*) from "{table.name}"').fetchone()[0]
    except Exception:
        return
    candidates = [c.name for c in table.columns if c.category == "string" or c.name.lower().endswith("_id")]
    if not candidates:
        return
    selects = ", ".join(f'approx_count_distinct("{n}")' for n in candidates)
    try:
        counts = con.execute(f'select {selects} from "{table.name}"').fetchone()
    except Exception:
        return
    table.distinct_counts = dict(zip(candidates, counts))


def main():
    adapter = DuckDBAdapter(DB_PATH)
    con = adapter.raw_connection
    try:
        all_tables = [t for t in introspect(con) if t.columns]
        new_tables = [t for t in all_tables if t.name not in MODELED_TABLES]
        for t in new_tables:
            profile(con, t)
        # Relationship inference matches FK columns like "item_id" against this
        # set of raw-table-derived names -- not against our curated model names
        # (e.g. it'll say "item", never "product"). That mapping is exactly the
        # kind of thing a human resolves during review.
        all_table_names = {t.name.lower() for t in all_tables}
    finally:
        adapter.close()

    if not new_tables:
        print("No new tables found -- everything in the database is already "
              "listed in brightcart_layer.py's MODELED_TABLES.")
        return

    print(f"Found {len(new_tables)} table(s) not yet in MODELED_TABLES:")
    for t in sorted(new_tables, key=lambda x: x.name):
        print(f"  - {t.name} ({len(t.columns)} columns, {t.row_count or '?'} rows)")
    print()

    MODELS_DIR.mkdir(exist_ok=True)
    written, skipped = [], []
    for t in sorted(new_tables, key=lambda x: x.name):
        model = generate_model_dict(t, all_table_names)
        target = MODELS_DIR / f"{model['name']}.yml"
        if target.exists():
            skipped.append(target)
            continue
        target.write_text(yaml.dump({"models": [model]}, sort_keys=False, default_flow_style=False))
        written.append(target)

    if written:
        print(f"Wrote {len(written)} draft model(s) to {MODELS_DIR}/:")
        for p in written:
            print(f"  - {p.name}")
    if skipped:
        print(f"Left {len(skipped)} existing draft(s) alone (delete to regenerate):")
        for p in skipped:
            print(f"  - {p.name}")

    print()
    print("These are starting points, not final models. For each: write a real "
          "description, decide whether it stands alone or merges into an existing "
          "model, add segments/governed metrics for any named business terms -- "
          "then fold it into build_layer() and add its table(s) to MODELED_TABLES.")


if __name__ == "__main__":
    main()
