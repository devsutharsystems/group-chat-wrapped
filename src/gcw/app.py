"""Group Chat Wrapped: local Streamlit app.  Run:  streamlit run src/gcw/app.py   (binds 127.0.0.1 only; see .streamlit/config.toml).

The chat lives in st.session_state (memory) only. Stats-only mode makes no network call. AI mode sends pseudonymised text to Anthropic only after the consent
checkbox is ticked AND Run is pressed (even the exact token count sends the text). Every string that comes from the chat is drawn with st.text or a dataframe,
never as markdown or HTML.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = str(Path(__file__).resolve().parents[1])
if _SRC not in sys.path:  # `streamlit run src/gcw/app.py` does not put src/ on the path
    sys.path.insert(0, _SRC)

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from gcw import analyze, appcore, chunked, cost, review  # noqa: E402

STEPS = ["1 Load", "2 Settings", "3 Stats card", "4 AI", "5 Review"]


def S(key, default=None):
    return st.session_state.get(key, default)


def parsed():
    """(df, view) for the loaded text and the chosen date order; re-parsed only when one of them changes."""
    text = S("text")
    if text is None:
        return None, None
    order = S("order", "auto")
    key = (id(text), order)
    if S("_parsed_key") != key:
        try:
            st.session_state["_parsed"] = appcore.parse_view(text, None if order == "auto" else order)
            st.session_state["_parsed_err"] = None
        except appcore.AppError as e:
            st.session_state["_parsed"] = (None, None)
            st.session_state["_parsed_err"] = str(e)
        st.session_state["_parsed_key"] = key
    return st.session_state["_parsed"]


def step_load():
    st.header("Step 1: load a chat")
    st.caption("The chat stays in memory in this browser session. It is never written to disk by this app.")
    src = st.radio("Source", ["Upload an export", "Bundled synthetic demo chat"], key="source")
    if src.startswith("Upload"):
        up = st.file_uploader("WhatsApp export (.txt, or a .zip with one .txt chat file; other files in the zip are ignored)", type=["txt", "zip"], key="upload")
        if up is not None and st.button("Use this file", key="use_upload"):
            try:
                st.session_state["text"] = appcore.read_upload(up.name, up.getvalue())
                st.session_state["chat_label"] = "uploaded file"
                _reset_downstream()
            except appcore.AppError as e:
                st.error(str(e))
    elif st.button("Load the demo chat", key="load_demo"):
        st.session_state["text"] = appcore.demo_text()
        st.session_state["chat_label"] = "synthetic demo chat"
        _reset_downstream()
    df, view = parsed()
    if S("_parsed_err"):
        st.error(S("_parsed_err"))
    if view is None:
        return
    st.success(f"Loaded: {S('chat_label')}")
    c = st.columns(4)
    c[0].metric("Messages", view["messages"])
    c[1].metric("System lines", view["system_lines"])
    c[2].metric("Unparsed lines", view["unparsed"])
    c[3].metric("Senders", len(view["senders"]))
    st.text(f"First message: {view['first']}   Last message: {view['last']}")
    st.text(f"Date order assumed: {'month/day' if view['date_order'] == 'mdy' else 'day/month'} (source: {view['date_order_source']})")
    if view["ambiguous"]:
        st.warning("The day/month order is ambiguous in this export; the card says the order is assumed. Override it in Step 2 if it is wrong.")
    for w in view["warnings"]:
        st.text("Warning: " + w)
    st.dataframe(pd.DataFrame({"sender": list(view["senders"]), "messages": list(view["senders"].values())}), hide_index=True)


def _reset_downstream():
    for k in ("png", "preview", "ai_result", "review", "review_png", "_parsed_key", "_prev_key", "consent", "aliases_table", "since", "until", "aliases"):
        st.session_state.pop(k, None)


def step_settings():
    st.header("Step 2: settings")
    df, view = parsed()
    if view is None:
        st.info("Load a chat in Step 1 first.")
        return
    st.subheader("Names")
    st.warning(appcore.LEAK_WARNING)
    how = st.radio("Aliases", ["Edit the table", "Upload aliases.json"], key="alias_how", horizontal=True)
    if how.startswith("Upload"):
        up = st.file_uploader("aliases.json", type=["json"], key="alias_up")
        if up is not None:
            try:
                st.session_state["aliases"] = appcore.aliases_from_upload(up.getvalue())
                st.success(f"{len(st.session_state['aliases'].members)} members loaded")
            except appcore.AppError as e:
                st.error(str(e))
    else:
        base = pd.DataFrame(appcore.alias_table(list(view["senders"])))
        edited = st.data_editor(base, key="aliases_table", hide_index=True, disabled=["export_name"], width="stretch",
                                column_config={"display": "Display name", "nicknames": "Nicknames (comma-separated)"})
        try:
            st.session_state["aliases"] = appcore.aliases_from_table(edited.to_dict("records"))
        except appcore.AppError as e:
            st.error(str(e))
    st.subheader("Date window")
    d0, d1 = appcore.default_window(view["last"])
    first = pd.Timestamp(view["first"]).date()
    last = pd.Timestamp(view["last"]).date()
    a, b = st.columns(2)
    since = a.date_input("From", value=pd.Timestamp(S("since") or max(pd.Timestamp(d0).date(), first)).date(), min_value=first, max_value=last, key="since_w")
    until = b.date_input("Until (inclusive)", value=pd.Timestamp(S("until") or last).date(), min_value=first, max_value=last, key="until_w")
    st.session_state["since"], st.session_state["until"] = str(since), str(until)  # widget state is dropped when another step is shown; these copies survive
    if since > until:
        st.error("The window starts after it ends.")
    orders = ["auto", "mdy", "dmy"]
    st.session_state["order"] = st.selectbox("Day/month order", orders, index=orders.index(S("order", "auto")), key="order_w", help="auto infers it; override when the card says the order is assumed")
    st.subheader("Mode")
    opts = ["Stats only (no network)", "AI (sends pseudonymised text to Anthropic after consent)"]
    ai = st.radio("Mode", opts, index=1 if S("ai_enabled") else 0, key="mode_radio")
    st.session_state["ai_enabled"] = ai.startswith("AI")
    if S("ai_enabled"):
        st.session_state["ai_mode"] = st.selectbox("AI mode", list(appcore.MODES), index=list(appcore.MODES).index(S("ai_mode", "auto")), key="ai_mode_w",
                                                   help=f"auto: single-pass up to {chunked.SINGLE_PASS_LIMIT:,} exact tokens, chunked above")


def _window():
    df, view = parsed()
    since, until = S("since"), S("until")
    if view is None:
        return None
    since = str(since or appcore.default_window(view["last"])[0])
    until = str(until or view["last"])
    return df, view, since, until


def step_card():
    st.header("Step 3: stats card")
    w = _window()
    if w is None:
        st.info("Load a chat in Step 1 first.")
        return
    df, view, since, until = w
    st.caption("Counted statistics only. Rendered locally in a separate process with no network access.")
    if st.button("Render stats card", key="render_stats"):
        try:
            with st.spinner("Rendering"):
                html = appcore.card_html(df, S("aliases"), since, until, view["date_order"] if view["ambiguous"] else None)
                st.session_state["png"] = appcore.render_png_bytes(html)
        except appcore.AppError as e:
            st.error(str(e))
    if S("png"):
        st.image(S("png"), width=720)
        st.download_button("Download card (PNG)", S("png"), file_name="group_chat_wrapped_stats.png", mime="image/png", key="dl_stats")


def step_ai():
    st.header("Step 4: AI analysis")
    w = _window()
    if w is None:
        st.info("Load a chat in Step 1 first.")
        return
    if not S("ai_enabled"):
        st.info("AI mode is off. Choose AI in Step 2 to use this step. Stats-only mode never sends anything.")
        return
    df, view, since, until = w
    try:
        key = (since, until, id(S("aliases")), id(S("text")), S("order"))
        if S("_prev_key") != key:
            st.session_state["preview"] = appcore.preview(df, S("aliases"), since, until)
            st.session_state["_prev_key"] = key
            st.session_state.pop("consent", None)
    except appcore.AppError as e:
        st.error(str(e))
        return
    pv = S("preview")
    st.subheader("Exactly what would be sent (pseudonymised; 20 lines, fixed seed)")
    st.text("\n".join(pv["lines"]))
    c = st.columns(3)
    c[0].metric("Messages in window", pv["messages"])
    c[1].metric("Withheld (sensitive keywords)", pv["withheld"])
    c[2].metric("Rough tokens (bytes / 2.37)", f"~{pv['rough_tokens']:,}")
    st.text("Replacements made: " + ", ".join(f"{k} {v}" for k, v in pv["replacements"].items()))
    st.text("Rough means rough: the exact token count needs a network call and happens only after consent.")
    mode = S("ai_mode", "auto")
    bound = pv["bounds"]["single_usd" if mode == "single" else "chunked_usd" if mode == "chunked" else "auto_usd"]
    caps = appcore.cap_status(bound)
    st.text(f"Worst-case cost upper bound for mode {mode}: ${bound:.2f} (computed offline; every call assumed to use all max_tokens). "
            f"Caps: ${caps['run_cap']:.2f} per run (GCW_COST_CAP_USD), ${caps['project_cap']:.2f} for the project (GCW_PROJECT_CAP_USD), ${caps['ledger_total']:.2f} already spent.")
    if not caps["ok"]:
        st.error("The worst-case bound is above a cost cap, so Run is disabled. Narrow the date window or raise the cap deliberately.")
    loaded = appcore.key_loaded()
    st.text(f"key loaded: {'yes' if loaded else 'no'}")
    if not loaded:
        st.warning("No API key is loaded (create .env in the project root, or set ANTHROPIC_API_KEY). Run is disabled.")
    consent = st.checkbox(appcore.CONSENT_TEXT, key="consent")
    if st.button("Run", key="run_ai", disabled=not (consent and caps["ok"] and loaded)):
        if not S("consent"):
            st.error("Consent is required.")
            return
        notes: list[str] = []
        try:
            with st.spinner("Counting tokens and analysing (this sends the pseudonymised text to Anthropic)"):
                res = appcore.run_ai(df, S("aliases"), since, until, mode, consent=True, log=notes.append)
            st.session_state["ai_result"] = res
            st.session_state["review"] = review.new_review(res["verified"], "app")
            st.session_state.pop("review_png", None)
        except (appcore.AppError, analyze.AnalysisError, cost.CostError, RuntimeError) as e:
            st.error("Run refused or failed: " + str(e))
        except Exception as e:  # an API error: shown once, nothing retried
            st.error(f"API or request error ({type(e).__name__}): {e}")
        for n in notes:
            st.warning(n)
    res = S("ai_result")
    if res:
        st.success(f"Done ({res['chosen']}): cost ${res['cost_usd']:.4f}, {res['request_tokens']:,} input tokens, {res['latency_s']} s. Continue in Step 5.")


def _source():
    """(report, index, rows, mapping, stats) from the last run, or from an uploaded saved report re-verified against this chat."""
    res = S("ai_result")
    if res:
        return res["verified"], res["index"], res["rows"], res["mapping"], res["stats"]
    w = _window()
    if w is None:
        return None
    df, view, since, until = w
    up = st.file_uploader("Or load a saved verified report (.report.json from analyze --save-response) for this chat and window", type=["json"], key="report_up")
    lg = st.file_uploader("Optional: the matching run log (.json), so the card says how many items the model proposed", type=["json"], key="log_up")
    if up is None:
        return None
    st.session_state["proposed"] = appcore.proposed_from_log(lg.getvalue()) if lg is not None else None
    if lg is None:
        st.caption("Without the run log, the card counts only the verified items as proposed (a saved report holds only verified items), and the window cannot be checked "
                   "against the run: stats and AI items must cover the same window.")
    try:
        prep = analyze.prepare(df, S("aliases"), slice_start=since, slice_end=until)
        covered = appcore.log_messages(lg.getvalue()) if lg is not None else None
        if covered is not None and covered != len(prep["rows"]):
            st.error(f"The run log covers {covered} messages but the window in Step 2 has {len(prep['rows'])}: stats and AI items must cover the same window. Set the window to match the run.")
            return None
        report, stats = appcore.load_report_upload(up.getvalue(), prep["index"], set(prep["members"]))
    except (appcore.AppError, analyze.AnalysisError) as e:
        st.error(str(e))
        return None
    if not S("review"):
        st.session_state["review"] = review.new_review(report, "app")
    st.session_state["_report_loaded"] = report
    return report, prep["index"], prep["rows"], prep["mapping"], stats


def step_review():
    st.header("Step 5: review")
    w = _window()
    if w is None:
        st.info("Load a chat in Step 1 first.")
        return
    src = _source()
    if src is None:
        st.info("Nothing to review yet: run the AI analysis in Step 4, or load a saved verified report above.")
        return
    report, index, rows, mapping, stats = src
    df, view, since, until = w
    names = appcore.names_for(mapping, S("aliases"))
    from gcw import display

    rv = S("review") or review.new_review(report, "app")
    rv = review.merge(rv, report)
    st.session_state["review"] = rv
    kept = {t: len(report.get(t) or []) for t in review.TYPES}
    st.text(f"Verified items: {sum(kept.values())} (running jokes {kept['running_jokes']}, moments {kept['moments']}, awards {kept['awards']})")
    state_line = st.empty()
    st.caption("Only approved items render on the card. Pending and rejected items never do.")
    if appcore.is_frozen_text(S("text") or "") and st.button("Auto-approve all (synthetic demo only)", key="auto_approve"):
        auto = appcore.auto_approve_all(report, "app", S("text"))
        for iid, meta in auto["items"].items():
            rv["items"][iid]["status"] = meta["status"]
            st.session_state[f"dec_{iid}"] = "approved"  # set before the radios are created in this run
        rv["approval_mode"] = auto["approval_mode"]

    def quote_line(ev: dict) -> str:
        row = index.get(ev.get("message_id", ""))
        who = names.get(row["sender"], row["sender"]) if row else "?"
        when = f"{row['ts']:%Y-%m-%d}" if row else ""
        return f'{who}, {when}: "{display.detokenise(str(ev.get("quote", "")), names)}"'

    def context_text(ev: dict) -> str:
        return "\n".join(("> " if m["is_target"] else "  ") + f"{m['when']} {m['who']}: {m['text']}" for m in appcore.context(rows, ev.get("message_id", ""), names))

    for iid, typ, item in appcore.item_ids(report):
        st.divider()
        st.text(f"{typ.replace('_', ' ')}: {display.detokenise(str(item.get('title') or item.get('award') or ''), names)}")
        st.text(display.detokenise(str(item.get("summary", "")), names))
        evs = [e for e in (item.get("evidence") or []) if isinstance(e, dict)]
        if evs:
            st.text(quote_line(evs[0]))  # the first quote, then the controls; everything else is inside expanders
        a, b = st.columns([3, 1])
        key = f"dec_{iid}"
        kw = {} if key in st.session_state else {"index": ["pending", "approved", "rejected"].index(rv["items"][iid]["status"])}
        status = a.radio("Decision", ["pending", "approved", "rejected"], key=key, horizontal=True, **kw)
        rank = b.number_input("Rank (0 = model order)", min_value=0, max_value=99, value=int(rv["items"][iid].get("rank") or 0), key=f"rank_{iid}")
        if status != rv["items"][iid]["status"]:
            review.set_human(rv)  # a manual decision after an auto-approval makes the approvals human again
        review.set_status(rv, [iid], status)
        review.set_rank(rv, iid, int(rank) or None)
        if evs:
            with st.expander("Context around the first quote", expanded=False):
                st.text(context_text(evs[0]))
        if len(evs) > 1:
            with st.expander(f"{len(evs) - 1} more quote{'s' if len(evs) > 2 else ''}", expanded=False):
                for ev in evs[1:]:
                    st.text(quote_line(ev))
                    st.text(context_text(ev))
    k = review.counts(report, rv)
    state_line.text(f"Review state: {k}; approvals made by: {review.mode_of(rv)}")
    if st.button("Render card", key="render_review"):
        try:
            review.check_mode(rv, appcore.is_frozen_text(S("text") or ""))
            with st.spinner("Rendering"):
                ai = appcore.zone_for(report, rv, index, mapping, S("aliases"), stats, proposed=None if S("ai_result") else S("proposed"))
                html = appcore.card_html(df, S("aliases"), since, until, view["date_order"] if view["ambiguous"] else None, ai=ai)
                st.session_state["review_png"] = appcore.render_png_bytes(html)
                appcore.save_safe_review(rv, "app")
        except (appcore.AppError, review.ReviewError) as e:
            st.error(str(e))
    if S("review_png"):
        st.image(S("review_png"), width=720)
        st.download_button("Download card with AI items (PNG)", S("review_png"), file_name="group_chat_wrapped_ai.png", mime="image/png", key="dl_ai")


def main():
    st.set_page_config(page_title="Group Chat Wrapped", layout="wide")
    st.title("Group Chat Wrapped")
    st.sidebar.title("Steps")
    step = st.sidebar.radio("Go to", STEPS, key="step")
    st.sidebar.caption("Local only (127.0.0.1). Stats-only mode sends nothing anywhere.")
    {"1 Load": step_load, "2 Settings": step_settings, "3 Stats card": step_card, "4 AI": step_ai, "5 Review": step_review}[step]()


main()
