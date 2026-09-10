"""
Chat UI for the Brightcart semantic layer.

Ask a question in plain English and watch the agent work: it explains what
it understood, calls the semantic layer tool (you see the metrics/dimensions
it chose and the SQL that compiled to), shows the result set, then writes
the final answer. Every query/chart result also gets an "Explore this data"
panel to keep pivoting on -- more columns, filters, a chart -- still entirely
through the governed semantic layer.

Run with:
    .venv/Scripts/python.exe -m streamlit run sample_data/app.py
"""

import json
import os
from datetime import date

import streamlit as st
from anthropic import Anthropic

from brightcart_layer import (
    CHART_TOOL_NAME,
    CHART_TOOL_SCHEMA,
    TOOL_NAME,
    TOOL_SCHEMA,
    build_catalog,
    build_chart,
    build_layer,
    compile_sql,
    run_query,
)

st.set_page_config(page_title="Brightcart Analyst", page_icon="📊", layout="centered")

MODEL = "claude-sonnet-5"


@st.cache_resource
def get_layer():
    return build_layer()


@st.cache_resource
def get_catalog():
    return build_catalog(get_layer())


@st.cache_resource
def get_client():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        st.error("ANTHROPIC_API_KEY is not set in this environment.")
        st.stop()
    return Anthropic(api_key=api_key)


def system_prompt() -> str:
    return (
        "You are a data analyst answering questions about Brightcart's business. "
        f"Today's date is {date.today().isoformat()} -- resolve relative time "
        "references ('this year', 'last month', 'year to date', 'this quarter') "
        "against that date, not against when the data happens to end. "
        "You can only see the following catalog of models, dimensions, metrics, "
        "and segments -- you have no knowledge of the underlying database schema, "
        "tables, or joins:\n\n"
        + json.dumps(get_catalog(), indent=2)
        + "\n\nSegments are the governed definition of terms like 'active' or "
        "'churned' -- when the user's question uses a word that matches a segment, "
        "use that segment instead of guessing your own filter for it. Ratio/derived "
        "metrics (like active_customer_rate) are governed business numbers -- prefer "
        "them over recomputing the same thing from raw measures. "
        "Before calling a tool, briefly state in one or two sentences how "
        "you're interpreting the question (which metrics/dimensions you'll need). "
        "Use query_semantic_layer for a data answer (numbers, a table). Use "
        "visualize_semantic_layer instead when the user asks to see/plot/chart/"
        "visualize/graph something, or a trend/comparison would read better as a "
        "picture -- it renders a chart directly to the user and also returns the "
        "underlying data so you can describe what it shows. Always reference "
        "fields as '<model>.<field>'. After you get results, answer the original "
        "question directly and concisely, grounded only in the returned data."
    )


def catalog_field_options(kind: str) -> list[str]:
    """All '<model>.<field>' names of the given kind ('dimensions', 'metrics', 'segments')
    across the whole catalog -- the full set the workspace lets you pick from, not just
    whatever fields the agent happened to use."""
    options = []
    for model in get_catalog():
        for field in model[kind]:
            options.append(f"{model['model']}.{field['name']}")
    return options


def render_workspace(seed: dict, key_prefix: str):
    """A self-service panel seeded from one tool call's input. Every control here still
    goes through compile_sql/run_query/build_chart -- same governed semantic layer the
    agent uses, just with the user driving instead of the agent.

    The last run's result is cached in st.session_state under key_prefix so it survives
    reruns triggered by *other* widgets on the page (otherwise Streamlit's "only the
    button-press rerun sees st.button() return True" behavior would make the result
    vanish the instant you touched anything else)."""
    layer = get_layer()
    result_key = f"{key_prefix}_result"

    dim_options = catalog_field_options("dimensions")
    metric_options = catalog_field_options("metrics")
    segment_options = catalog_field_options("segments")

    metrics = st.multiselect(
        "Metrics", metric_options,
        default=[m for m in seed.get("metrics", []) if m in metric_options],
        key=f"{key_prefix}_metrics",
    )
    dimensions = st.multiselect(
        "Columns (dimensions)", dim_options,
        default=[d for d in seed.get("dimensions", []) if d in dim_options],
        key=f"{key_prefix}_dims",
    )
    segments = st.multiselect(
        "Segments (governed filters)", segment_options,
        default=[s for s in seed.get("segments", []) if s in segment_options],
        key=f"{key_prefix}_segs",
    )
    filters_text = st.text_area(
        "Filters (SQL boolean expressions, one per line)",
        value="\n".join(seed.get("filters") or []),
        key=f"{key_prefix}_filters", height=80,
    )
    limit = st.number_input(
        "Row limit", min_value=1, max_value=5000,
        value=seed.get("limit") or 50, key=f"{key_prefix}_limit",
    )
    view_mode = st.radio(
        "View", ["Table", "Chart"], horizontal=True,
        index=1 if "mark" in seed else 0, key=f"{key_prefix}_mode",
    )
    mark = "auto"
    if view_mode == "Chart":
        mark = st.selectbox(
            "Chart type", ["auto", "bar", "line", "area", "scatter", "point"],
            index=["auto", "bar", "line", "area", "scatter", "point"].index(seed.get("mark", "auto")),
            key=f"{key_prefix}_mark",
        )

    if st.button("Run", key=f"{key_prefix}_run", type="primary"):
        filters = [f.strip() for f in filters_text.splitlines() if f.strip()]
        tool_input = {
            "metrics": metrics, "dimensions": dimensions, "segments": segments,
            "filters": filters, "limit": int(limit),
        }
        try:
            if view_mode == "Chart":
                spec, _rows, sql = build_chart(layer, {**tool_input, "mark": mark})
                st.session_state[result_key] = {"mode": "chart", "sql": sql, "spec": spec, "error": None}
            else:
                sql = compile_sql(layer, tool_input)
                df = run_query(layer, tool_input)
                st.session_state[result_key] = {"mode": "table", "sql": sql, "df": df, "error": None}
        except Exception as e:
            st.session_state[result_key] = {"mode": view_mode.lower(), "error": str(e)}

    result = st.session_state.get(result_key)
    if result:
        if result["error"]:
            st.error(result["error"])
        else:
            st.code(result["sql"], language="sql")
            if result["mode"] == "chart":
                st.vega_lite_chart(result["spec"], width="stretch")
            else:
                st.dataframe(result["df"], width="stretch")


def render_query_block(sql: str, df, error: str | None, tool_input: dict, key: str):
    label = "Query failed" if error else "Query complete"
    with st.status(label, state="error" if error else "complete", expanded=False):
        st.markdown("**Requested:**")
        st.json(tool_input)
        st.markdown("**Compiled SQL:**")
        st.code(sql, language="sql")
        if error:
            st.error(error)
        else:
            st.markdown("**Result:**")
            st.dataframe(df, width="stretch")
    if not error:
        with st.popover("🔍 Explore this data"):
            render_workspace(tool_input, key_prefix=f"{key}_ws")


def render_chart_block(sql: str, spec, error: str | None, tool_input: dict, key: str):
    if error:
        st.error(error)
        return
    # The chart is the deliverable here, so it stays visible (unlike the query
    # tool's status box, which collapses).
    with st.expander("Chart details (requested fields + SQL)"):
        st.markdown("**Requested:**")
        st.json(tool_input)
        st.markdown("**Compiled SQL:**")
        st.code(sql, language="sql")
    st.vega_lite_chart(spec, width="stretch")
    with st.popover("🔍 Explore this data"):
        render_workspace(tool_input, key_prefix=f"{key}_ws")


def render_blocks(blocks: list):
    """Replays one assistant turn's recorded blocks -- used both for the turn that
    was just answered and for every earlier turn, on every rerun. Each query/chart
    block carries the Anthropic tool_use id, which becomes the widget key -- it MUST
    stay identical between the live render and every later replay, or Streamlit treats
    it as a brand-new widget on the next rerun and silently drops whatever the user
    was doing inside its Explore popover (this bit us once already)."""
    for block in blocks:
        if block["type"] == "text":
            st.markdown(block["text"])
        elif block["type"] == "query":
            render_query_block(block["sql"], block["df"], block["error"], block["input"], block["id"])
        elif block["type"] == "chart":
            render_chart_block(block["sql"], block["spec"], block["error"], block["input"], block["id"])


def run_turn(user_question: str, messages: list):
    """Drives the tool-use loop for one user question, streaming each step live.

    `messages` is the full running conversation in Anthropic message format
    (persisted in st.session_state by the caller) -- it's mutated in place so
    later turns still have the earlier questions, answers, and tool calls.

    Returns (final_text, blocks) where `blocks` is the same structure render_blocks
    replays later -- the caller must save it, or this turn's status boxes and Explore
    popovers won't survive the next rerun."""
    client = get_client()
    layer = get_layer()

    messages.append({"role": "user", "content": user_question})

    final_text = ""
    blocks = []
    while True:
        with client.messages.stream(
            model=MODEL,
            max_tokens=4096,
            system=system_prompt(),
            tools=[TOOL_SCHEMA, CHART_TOOL_SCHEMA],
            messages=messages,
        ) as stream:
            thinking_box = None
            thinking_placeholder = None
            thinking_text = ""
            text_placeholder = None
            streamed = ""

            for event in stream:
                if event.type == "content_block_start":
                    if event.content_block.type == "thinking":
                        thinking_box = st.status("🤔 Thinking...", expanded=True)
                        thinking_placeholder = thinking_box.empty()
                    elif event.content_block.type == "text":
                        text_placeholder = st.empty()
                elif event.type == "content_block_delta":
                    if event.delta.type == "thinking_delta" and thinking_placeholder:
                        thinking_text += event.delta.thinking
                        thinking_placeholder.markdown(thinking_text)
                    elif event.delta.type == "text_delta" and text_placeholder:
                        streamed += event.delta.text
                        text_placeholder.markdown(streamed)
                elif event.type == "content_block_stop" and thinking_box and not text_placeholder:
                    thinking_box.update(label="Thought it through", state="complete", expanded=False)

            response = stream.get_final_message()

        messages.append({"role": "assistant", "content": response.content})

        if streamed:
            blocks.append({"type": "text", "text": streamed})

        if response.stop_reason != "tool_use":
            final_text = streamed
            break

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            if block.name == TOOL_NAME:
                sql = compile_sql(layer, block.input)
                try:
                    df = run_query(layer, block.input)
                    result_text = df.to_csv(index=False)
                    error = None
                except Exception as e:
                    df = None
                    error = str(e)
                    result_text = f"ERROR: {e}"
                render_query_block(sql, df, error, block.input, block.id)
                blocks.append({"type": "query", "id": block.id, "input": block.input,
                                "sql": sql, "df": df, "error": error})

            elif block.name == CHART_TOOL_NAME:
                try:
                    spec, rows, sql = build_chart(layer, block.input)
                    error = None
                    result_text = json.dumps(rows, default=str)
                except Exception as e:
                    spec, sql = None, None
                    error = str(e)
                    result_text = f"ERROR: {e}"
                render_chart_block(sql, spec, error, block.input, block.id)
                blocks.append({"type": "chart", "id": block.id, "input": block.input,
                                "sql": sql, "spec": spec, "error": error})

            else:
                result_text = f"ERROR: unknown tool {block.name}"

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result_text,
            })

        messages.append({"role": "user", "content": tool_results})

    return final_text, blocks


st.title("📊 Brightcart Analyst")
st.caption(
    "Ask a question about Brightcart's customers and orders. The agent only "
    "sees a semantic catalog -- it doesn't know the data is spread across "
    "5 fragmented tables underneath."
)

if "history" not in st.session_state:
    st.session_state.history = []  # [{role: "user", content}] or [{role: "assistant", content, blocks}]
if "api_messages" not in st.session_state:
    st.session_state.api_messages = []  # full Anthropic-format conversation, incl. tool calls

for turn in st.session_state.history:
    with st.chat_message(turn["role"]):
        if turn["role"] == "user":
            st.markdown(turn["content"])
        else:
            render_blocks(turn.get("blocks", []))

question = st.chat_input("Ask about customers or orders...")

if question:
    st.session_state.history.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        # run_turn already streams everything live into the page as it arrives --
        # don't re-render it here, render_blocks will replay it on the next rerun.
        answer, blocks = run_turn(question, st.session_state.api_messages)

    st.session_state.history.append({"role": "assistant", "content": answer, "blocks": blocks})
