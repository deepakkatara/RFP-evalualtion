from __future__ import annotations

import json
import os
from datetime import date
from html import escape
from pathlib import Path
from uuid import uuid4

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from app.database import active_criteria, all_criteria, complete_run, create_run, export_run, fail_run, initialize, update_criteria, update_run_trace
from app.evaluator import PROVIDERS, demo_evaluate, evaluate_with_openai, extract_pdf_text, provider_defaults, validate_provider_connection
from app.models import LLMScorecard, RankedSupplier, SupplierInput, ValidatedSupplier
from app.scoring import detect_result_anomalies, normalize_scorecard, rank_sensitivity, rank_suppliers
from app.workflow import PHASES, WORKFLOW, initial_trace, trace_lookup, update_trace_step

ROOT = Path(__file__).parent
DATABASE = ROOT / "data" / "rfp_evaluation.db"
DATABASE.parent.mkdir(parents=True, exist_ok=True)
initialize(DATABASE)


def supplier_name_from_upload(uploaded_file: object | None) -> str:
    """Create a readable fallback supplier name from an uploaded PDF filename."""
    filename = getattr(uploaded_file, "name", "")
    return Path(filename).stem.replace("_", " ").replace("-", " ").title()


st.set_page_config(page_title="RFP Command Center", page_icon="🏆", layout="wide", initial_sidebar_state="expanded")

try:
    app_secrets = st.secrets.to_dict()
except StreamlitSecretNotFoundError:
    app_secrets = {}
for provider_setting in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"):
    if provider_setting in app_secrets and not os.getenv(provider_setting):
        os.environ[provider_setting] = str(app_secrets[provider_setting])

st.markdown("""
<style>
    .stApp { background: #f4f7fb; color: #172b4d; font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    .stApp button, .stApp input, .stApp textarea, .stApp [data-baseweb="select"], .stApp [data-testid="stMarkdownContainer"], .stApp [data-testid="stText"] { font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    .block-container { max-width: 1180px; padding-top: 1.35rem; padding-bottom: 3rem; }
    [data-testid="stSidebar"] { background: linear-gradient(180deg, #102a43 0%, #163e63 100%); }
    [data-testid="stSidebar"] * { color: #f8fbff; }
    [data-testid="stSidebar"] [data-baseweb="input"] input { color: #172b4d !important; }
    [data-testid="stSidebar"] [data-baseweb="select"] * { color: #172b4d; }
    .hero { padding: 1.2rem 1.5rem; border-radius: 12px; color: white; background: linear-gradient(112deg, #102a43, #1f5f8b 58%, #2a9d8f); margin-bottom: 1rem; }
    .hero h1 { font-size: 1.85rem; margin: 0; letter-spacing: -0.03em; }
    .hero p { font-size: .95rem; margin: .35rem 0 0; opacity: .92; }
    .hero-tag { font-size: .72rem; font-weight: 700; text-transform: uppercase; letter-spacing: .11em; opacity: .76; }
    [data-testid="stMetric"] { background: white; border: 1px solid #dbe5f0; border-radius: 10px; padding: .7rem .9rem; }
    [data-testid="stTabs"] [data-baseweb="tab-list"] { gap: .4rem; border-bottom: 1px solid #dbe5f0; }
    [data-testid="stTabs"] [data-baseweb="tab"] { height: 2.8rem; padding: 0 .9rem; font-size: .88rem; font-weight: 650; color: #52667e; }
    [data-testid="stTabs"] [aria-selected="true"] { color: #174b73; }
    [data-testid="stTabs"] [data-baseweb="tab-highlight"] { background-color: #2a9d8f; height: 3px; }
    .readiness-strip { display: flex; gap: .7rem; flex-wrap: wrap; margin: .15rem 0 1rem; }
    .readiness-item { background: #ffffff; border: 1px solid #dbe5f0; border-radius: 8px; padding: .48rem .7rem; color: #52667e; font-size: .82rem; }
    .readiness-item strong { color: #172b4d; }
    .upload-note { color: #63758a; font-size: .82rem; margin: -.45rem 0 .7rem; }
    .supplier-file { color: #63758a; font-size: .77rem; padding-top: .35rem; overflow-wrap: anywhere; }
    .supplier-row { border-top: 1px solid #e4ebf2; padding: .75rem 0 .2rem; }
    .live-stage { display: flex; align-items: center; gap: .5rem; border: 1px solid #dbe5f0; border-radius: 7px; padding: .38rem .55rem; margin: .28rem 0; background: #ffffff; color: #52667e; font-size: .82rem; }
    .live-stage.completed { border-color: #b8ddcf; background: #f4fbf8; color: #24755e; }
    .live-stage.running { border-color: #7dc4bc; background: #e9f8f5; color: #12695f; font-weight: 650; }
    .live-stage.failed { border-color: #e4a39d; background: #fff4f3; color: #a33d35; font-weight: 650; }
    .live-stage-icon { width: 1.1rem; text-align: center; font-weight: 700; }
    .live-summary { background: #ffffff; border: 1px solid #dbe5f0; border-radius: 10px; padding: 1rem; min-height: 100%; }
    .stage-caption { color: #63758a; font-size: .78rem; margin: 0 0 .25rem .15rem; }
    [class*="st-key-stage-"] button { min-height: 2.65rem; text-align: left; justify-content: flex-start; padding: .45rem .65rem; font-size: .86rem; }
    .detail-panel { background: #ffffff; border: 1px solid #dbe5f0; border-radius: 10px; padding: 1rem 1.05rem; min-height: 100%; }
    .detail-label { color: #63758a; font-size: .72rem; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; margin-bottom: .15rem; }
    .detail-value { color: #172b4d; font-size: .9rem; line-height: 1.4; margin-bottom: .85rem; overflow-wrap: anywhere; }
    .evidence-list { margin: .35rem 0 0; padding-left: 1.1rem; color: #42576e; font-size: .88rem; }
    [data-testid="stSidebar"] [data-testid="stMetric"] { color: #172b4d; }
    @media (max-width: 700px) {
        .block-container { padding-left: 1rem; padding-right: 1rem; }
        .hero { padding: 1.2rem; }
        .hero h1 { font-size: 1.65rem; }
        [data-testid="stTabs"] [data-baseweb="tab-list"] { overflow-x: auto; }
        [data-testid="stTabs"] [data-baseweb="tab"] { padding: 0 .65rem; font-size: .78rem; white-space: nowrap; }
    }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
  <div class="hero-tag">Procurement intelligence workspace</div>
  <h1>Agentic RFP Evaluation</h1>
  <p>Evidence-grounded proposal assessment with transparent validation, peer benchmarking, and deterministic supplier ranking.</p>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("Provider connection")
    st.caption("Keys remain only in this browser session. They are never written to SQLite, files, Git, logs, or exported results.")
    provider_name = st.selectbox("Provider", list(PROVIDERS), key="provider-name")
    defaults = provider_defaults(provider_name)
    provider_key = st.text_input("API key", type="password", key=f"provider-key-{provider_name}")
    provider_base_url = st.text_input("Compatible API base URL", value=defaults["base_url"], key=f"provider-base-url-{provider_name}")
    provider_model = st.text_input("Model", value=defaults["model"], key=f"provider-model-{provider_name}")
    st.caption("The connection test sends only a tiny JSON readiness prompt; supplier PDFs are never used for the test.")
    if st.button("Test connection and use provider", type="primary", use_container_width=True):
        try:
            response_text = validate_provider_connection(provider_key, provider_base_url, provider_model)
            st.session_state.provider_config = {"provider": provider_name, "api_key": provider_key, "base_url": provider_base_url, "model": provider_model}
            st.success(f"Connected to {provider_name}. Validator response: {response_text[:40]}")
        except Exception as exc:
            st.error(f"Not connected: {exc}")
    if configured := st.session_state.get("provider_config"):
        st.success(f"Session active\n\n{configured['provider']} / {configured['model']}")
    elif os.getenv("OPENAI_API_KEY"):
        st.info("A provider is configured through local or Streamlit secrets.")
    st.divider()
    st.caption("Decision boundary")
    st.write("**LLM:** reads proposal evidence and returns a criterion scorecard.")
    st.write("**Python:** validates output, applies formulas, benchmarks peers, resolves tie-breaks, and persists results.")


def render_live_flow(trace: dict) -> None:
    states = trace_lookup(trace)
    status_icons = {"pending": "○", "running": "●", "completed": "✓", "failed": "!"}
    active = next((step for step in WORKFLOW if states.get(step["key"], {}).get("status") == "running"), None)
    completed = sum(item.get("status") == "completed" for item in states.values())
    summary, stages = st.columns([1, 1.25], gap="large")
    with summary:
        st.markdown("#### Evaluation in progress")
        st.progress(completed / len(WORKFLOW), text=f"{completed} of {len(WORKFLOW)} stages completed")
        if active:
            active_trace = states[active["key"]]
            st.markdown(
                f"<div class='live-summary'><div class='detail-label'>Current stage</div>"
                f"<div class='detail-value'>{active['number']} · {active['title']}</div>"
                f"<div class='detail-label'>Current activity</div>"
                f"<div class='detail-value'>{escape(active_trace['summary'])}</div></div>",
                unsafe_allow_html=True,
            )
    with stages:
        st.markdown("<div class='stage-caption'>LIVE EXECUTION TRACE</div>", unsafe_allow_html=True)
        for step in WORKFLOW:
            outcome = states.get(step["key"], {"status": "pending"})
            status = outcome["status"]
            st.markdown(
                f"<div class='live-stage {status}'><span class='live-stage-icon'>{status_icons[status]}</span>"
                f"{step['number']} · {step['title']} <span style='margin-left:auto;font-size:.72rem'>{status.title()}</span></div>",
                unsafe_allow_html=True,
            )


def run_pending_evaluation(live_flow: st.delta_generator.DeltaGenerator) -> None:
    pending = st.session_state.get("pending_evaluation")
    if not pending:
        return

    run_id = create_run(DATABASE)
    st.session_state.last_run_id = run_id
    criteria_for_run = active_criteria(DATABASE)
    trace = initial_trace()
    active_step = "configure"

    def advance(step: str, status: str, summary: str, details: list[str] | None = None) -> None:
        nonlocal trace, active_step
        active_step = step
        st.session_state.selected_workflow_step = step
        trace = update_trace_step(trace, step, status, summary, details)
        update_run_trace(DATABASE, run_id, trace)
        with live_flow.container():
            render_live_flow(trace)

    try:
        advance("configure", "running", "Validating the active evaluation configuration.")
        configuration_details = [
            f"{len(criteria_for_run)} active criteria",
            f"Active weight: {sum(item.weight for item in criteria_for_run):g}%",
            *[f"{item.name}: {item.weight:g}% (max {item.max_score:g})" for item in criteria_for_run],
        ]
        advance("configure", "completed", "Loaded and validated the active evaluation configuration.", configuration_details)

        advance("ingest", "running", "Extracting text from submitted proposal PDFs.")
        suppliers, ingested = [], []
        for position, row in enumerate(pending["suppliers"], 1):
            supplier_name = row["name"]
            advance("ingest", "running", f"Extracting {supplier_name} ({position} of {len(pending['suppliers'])}).", ingested)
            text = extract_pdf_text(row["file"])
            supplier = SupplierInput(supplier_name=row["name"], submission_date=row["date"], experience_rating=row["experience"], document_text=text)
            suppliers.append(supplier)
            ingested.append(f"{supplier.supplier_name}: {row['file'].name} ({len(text):,} extracted characters)")
        advance("ingest", "completed", "Extracted text from every submitted proposal.", ingested)

        advance("assess", "running", "Producing criterion scorecards from proposal evidence.")
        raw_scorecards, assessed = [], []
        for position, supplier in enumerate(suppliers, 1):
            advance("assess", "running", f"Assessing {supplier.supplier_name} ({position} of {len(suppliers)}).", assessed)
            if pending["mode"].startswith("Demo"):
                raw = demo_evaluate(supplier.supplier_name, supplier.document_text, criteria_for_run)
                assessed.append(f"{supplier.supplier_name}: deterministic demo scorecard returned.")
            else:
                config = st.session_state.get("provider_config")
                if not config and not os.getenv("OPENAI_API_KEY"):
                    raise ValueError("Choose and validate a provider in the sidebar before starting an LLM evaluation.")
                raw = evaluate_with_openai(supplier.supplier_name, supplier.document_text, criteria_for_run,
                                           api_key=config["api_key"] if config else None,
                                           base_url=config["base_url"] if config else None,
                                           model=config["model"] if config else None)
                assessed.append(f"{supplier.supplier_name}: {config['provider'] if config else 'configured provider'} returned a structured scorecard.")
            raw_scorecards.append(raw)
        advance("assess", "completed", "Returned proposal-only criterion scorecards.", assessed)

        advance("validate", "running", "Normalizing scorecards and capturing validation warnings.")
        validated, validation_details = [], []
        for supplier, raw in zip(suppliers, raw_scorecards):
            normal, warnings = normalize_scorecard(raw, supplier.supplier_name, criteria_for_run, supplier.document_text)
            verified = sum(1 for item in normal["criteria"] if item["evidence_verified"])
            validation_details.append(f"{supplier.supplier_name}: {verified}/{len(criteria_for_run)} evidence excerpts verified; {len(warnings)} validation warning(s).")
            validated.append(ValidatedSupplier(supplier=supplier, scorecard=LLMScorecard(**normal), warnings=warnings))
        advance("validate", "completed", "Normalized scorecards and retained validation warnings.", validation_details)

        ranked = rank_suppliers(validated, criteria_for_run)
        sensitivity = rank_sensitivity(ranked, criteria_for_run)
        anomalies = detect_result_anomalies(ranked)
        advance("score", "completed", "Calculated weighted absolute scores.", [f"{result.supplier_name}: {result.absolute_score:.2f}." for result in ranked])
        advance("benchmark", "completed", "Calculated peer benchmarks, gaps, relative performance, and PPI.", [f"{result.supplier_name}: PPI {result.ppi:.2f}." for result in ranked])
        rank_details = [f"#{result.final_rank} {result.supplier_name}: {result.tie_break_explanation}" for result in ranked]
        rank_details.append("Weight sensitivity: " + ("leader remained stable" if sensitivity["stable"] else "leader changes in at least one scenario") + ".")
        rank_details.extend(anomalies)
        advance("rank", "completed", "Applied deterministic tie-breaks and flagged low-confidence decisions for review.", rank_details)
        advance("persist", "running", "Saving results and the execution trace.")
        trace = update_trace_step(trace, "persist", "completed", f"Stored {len(ranked)} ranked supplier result(s) under {run_id}.", ["Results and trace are available here and in the JSON export."])
        complete_run(DATABASE, run_id, ranked, trace)
        with live_flow.container():
            render_live_flow(trace)
        st.session_state.execution_notice = f"{run_id} completed. Review any flow step, then open Results."
    except Exception as exc:
        trace = update_trace_step(trace, active_step, "failed", f"Stopped: {exc}", [str(exc)])
        update_run_trace(DATABASE, run_id, trace)
        fail_run(DATABASE, run_id, str(exc))
        with live_flow.container():
            render_live_flow(trace)
        st.session_state.execution_notice = f"{run_id} failed: {exc}"
    finally:
        st.session_state.pop("pending_evaluation", None)


criteria = active_criteria(DATABASE)
active_weight = sum(item.weight for item in criteria)
configuration_ready = abs(active_weight - 100) < 0.001
provider_ready = bool(st.session_state.get("provider_config") or os.getenv("OPENAI_API_KEY"))

configuration_tab, suppliers_tab, execution_tab, results_tab = st.tabs(PHASES)

with configuration_tab:
    st.subheader("Configuration & Evaluation Metrics")
    st.caption("Define the decision model first. Every supplier batch reads this configuration directly from SQLite.")
    metric_a, metric_b, metric_c = st.columns(3)
    metric_a.metric("Active metrics", len(criteria))
    metric_b.metric("Active weight", f"{active_weight:g}%")
    metric_c.metric("Configuration", "Ready" if abs(active_weight - 100) < 0.001 else "Needs attention")
    edited_criteria = []
    with st.form("criteria_admin"):
        for criterion in all_criteria(DATABASE):
            active_col, name_col, weight_col, max_col = st.columns([1.5, 3.5, 2, 2])
            is_active = active_col.checkbox("Active", value=criterion.is_active, key=f"criterion-active-{criterion.criterion_id}")
            name_col.write(criterion.name)
            weight = weight_col.number_input("Weight %", min_value=0.1, max_value=100.0, value=float(criterion.weight), step=0.5, key=f"criterion-weight-{criterion.criterion_id}")
            max_col.write(f"Maximum score: {criterion.max_score:g}")
            edited_criteria.append(criterion.model_copy(update={"is_active": is_active, "weight": weight}))
        save_criteria = st.form_submit_button("Save criteria changes", type="primary")
    if save_criteria:
        try:
            update_criteria(DATABASE, edited_criteria)
            st.success("Criteria saved. The next batch will use the updated configuration.")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
    st.caption("The active criteria above are the configuration that will be applied to the next evaluation.")

with suppliers_tab:
    st.subheader("Supplier Proposals")
    st.caption("Upload the proposals you want to compare. Supplier names are derived from PDF filenames unless you provide an override.")
    provider_status = "Connected" if provider_ready else "Demo available"
    st.markdown(
        f"<div class='readiness-strip'>"
        f"<div class='readiness-item'><strong>Configuration:</strong> {'Ready' if configuration_ready else 'Needs attention'}</div>"
        f"<div class='readiness-item'><strong>Active criteria:</strong> {len(criteria)}</div>"
        f"<div class='readiness-item'><strong>Provider:</strong> {provider_status}</div>"
        f"</div>", unsafe_allow_html=True,
    )
    mode = st.radio("Evaluation mode", ["Demo (offline, reproducible)", "Configured provider (evidence-grounded LLM)"], index=1, horizontal=True)
    if mode.startswith("Configured") and not provider_ready:
        st.warning("Connect and validate a provider in the sidebar before preparing an LLM evaluation, or use Demo mode for an offline walkthrough.")

    if "rows" not in st.session_state:
        st.session_state.rows = []
    if "excluded_upload_sources" not in st.session_state:
        st.session_state.excluded_upload_sources = set()

    uploaded_files = st.file_uploader(
        "Upload supplier proposal PDFs",
        type="pdf",
        accept_multiple_files=True,
        key="batch-pdf-upload",
        help="Select or drop multiple proposals. A supplier row is created for each PDF.",
    )
    st.markdown("<div class='upload-note'>Upload multiple PDFs in one action. Supplier names are pre-filled from filenames and remain editable below.</div>", unsafe_allow_html=True)

    uploaded_by_source = {f"{file.name}:{file.size}": file for file in uploaded_files}
    current_by_source = {row.get("source"): row for row in st.session_state.rows if row.get("source")}
    active_sources = [source for source in uploaded_by_source if source not in st.session_state.excluded_upload_sources]
    if set(current_by_source) != set(active_sources) or any(not row.get("source") for row in st.session_state.rows):
        st.session_state.rows = [
            {
                **current_by_source.get(source, {"id": uuid4().hex, "name": "", "date": date.today(), "experience": 5.0}),
                "source": source,
                "file": uploaded_by_source[source],
            }
            for source in active_sources
        ]
        st.rerun()

    if not st.session_state.rows:
        st.info("Upload at least two proposal PDFs to create a supplier comparison batch.")
    else:
        with st.form("supplier_input"):
            updated = []
            remove_requested = None
            for index, row in enumerate(st.session_state.rows, 1):
                st.markdown("<div class='supplier-row'></div>", unsafe_allow_html=True)
                left, middle, right, action = st.columns([3, 1.7, 1.55, 0.75])
                default_name = row["name"] or supplier_name_from_upload(row["file"])
                name = left.text_input("Supplier name", value=default_name, key=f"name-{row['id']}", label_visibility="visible")
                submission_date = middle.date_input("Submission date", value=row["date"], key=f"date-{row['id']}")
                experience = right.number_input("Experience", min_value=0.0, max_value=10.0, value=float(row["experience"]), key=f"experience-{row['id']}")
                action.markdown("<div class='supplier-file'>PDF</div>", unsafe_allow_html=True)
                if action.form_submit_button("Remove", key=f"remove-{row['id']}"):
                    remove_requested = row["source"]
                st.caption(f"{index}. {row['file'].name}")
                updated.append({"id": row["id"], "source": row["source"], "name": name.strip(), "date": submission_date, "experience": experience, "file": row["file"]})
            prepare_batch = st.form_submit_button("Prepare evaluation", type="primary", use_container_width=True)

        if remove_requested:
            st.session_state.excluded_upload_sources.add(remove_requested)
            st.session_state.rows = [row for row in updated if row["source"] != remove_requested]
            st.rerun()

    if st.session_state.rows and prepare_batch:
        st.session_state.rows = updated
        supplied_names = [row["name"].strip() for row in updated]
        missing_pdf_rows = [str(index) for index, row in enumerate(updated, 1) if not row["file"]]
        blank_name_rows = [str(index) for index, name in enumerate(supplied_names, 1) if not name]
        duplicate_names = {name for name in supplied_names if name and sum(item.casefold() == name.casefold() for item in supplied_names) > 1}
        if not configuration_ready:
            st.error("Configuration must have active weights totaling 100% before a batch can be prepared.")
        elif len(updated) < 2:
            st.error("Upload at least two supplier proposals to create a peer benchmark.")
        elif missing_pdf_rows:
            st.error("Upload a proposal PDF for row(s): " + ", ".join(missing_pdf_rows) + ".")
        elif blank_name_rows:
            st.error("Enter a supplier name only for row(s) whose PDF filename cannot provide one: " + ", ".join(blank_name_rows) + ".")
        elif duplicate_names:
            st.error("Supplier names must be unique within a batch: " + ", ".join(sorted(duplicate_names)))
        elif mode.startswith("Configured") and not provider_ready:
            st.error("Connect and validate a provider in the sidebar before preparing an LLM evaluation, or select Demo mode.")
        else:
            st.session_state.pending_evaluation = {"suppliers": updated, "mode": mode}
            st.success("Batch is ready. Open the Execution Flow tab and start the evaluation when you are ready.")

with execution_tab:
    st.subheader("Execution Flow")
    st.caption("Select any stage to inspect its owner, inputs, intended outcome, and recorded run evidence.")
    if "selected_workflow_step" not in st.session_state:
        st.session_state.selected_workflow_step = "configure"
    if st.session_state.get("pending_evaluation"):
        pending = st.session_state.pending_evaluation
        st.info(f"{len(pending['suppliers'])} supplier proposal(s) are ready in {pending['mode']} mode.")
        if st.button("Start evaluation", type="primary", key="start-evaluation"):
            live_flow = st.empty()
            run_pending_evaluation(live_flow)

    latest_run = export_run(DATABASE, st.session_state.last_run_id)["run"] if st.session_state.get("last_run_id") else None
    current_trace = latest_run.get("trace") if latest_run else initial_trace()
    trace_by_key = trace_lookup(current_trace)
    rail, details = st.columns([1, 1.65], gap="large")
    status_icons = {"pending": "○", "running": "●", "completed": "✓", "failed": "!"}
    with rail:
        st.markdown("<div class='stage-caption'>EVALUATION STAGES</div>", unsafe_allow_html=True)
        for step in WORKFLOW:
            outcome = trace_by_key.get(step["key"], {"status": "pending"})
            status = outcome["status"]
            label = f"{status_icons[status]}  {step['number']} · {step['title']}  —  {status.title()}"
            if st.button(label, key=f"stage-{step['key']}", use_container_width=True,
                         type="primary" if st.session_state.selected_workflow_step == step["key"] else "secondary"):
                st.session_state.selected_workflow_step = step["key"]
                st.rerun()

    selected = next(step for step in WORKFLOW if step["key"] == st.session_state.selected_workflow_step)
    selected_trace = trace_by_key.get(selected["key"])
    with details:
        status = selected_trace["status"] if selected_trace else "pending"
        st.markdown(f"#### {selected['number']} · {selected['title']}")
        st.markdown(
            f"<div class='detail-panel'>"
            f"<div class='detail-label'>Owner</div><div class='detail-value'>{selected['owner']}</div>"
            f"<div class='detail-label'>Input</div><div class='detail-value'>{selected['input']}</div>"
            f"<div class='detail-label'>Expected outcome</div><div class='detail-value'>{selected['outcome']}</div>"
            f"</div>", unsafe_allow_html=True,
        )
        if selected_trace and status != "pending":
            status_message = st.success if status == "completed" else st.error if status == "failed" else st.info
            status_message(selected_trace["summary"])
            if selected_trace["details"]:
                st.markdown("**Recorded evidence**")
                st.markdown("<ul class='evidence-list'>" + "".join(f"<li>{escape(detail)}</li>" for detail in selected_trace["details"]) + "</ul>", unsafe_allow_html=True)
        else:
            st.info("This is the planned outcome. Start a prepared batch to populate evidence for this stage.")
    if latest_run:
        st.caption(f"Latest run: {latest_run['rfp_run_id']} · {latest_run['status']} · {latest_run['created_at']}")
        if latest_run.get("error_message"):
            st.error(latest_run["error_message"])
        elif latest_run["status"] == "completed":
            st.success("Evaluation is complete. Open the Results tab to review the leaderboard and evidence scorecards.")
    if notice := st.session_state.pop("execution_notice", None):
        if latest_run and latest_run["status"] == "completed":
            st.success(notice)
        else:
            st.error(notice)

with results_tab:
    if run_id := st.session_state.get("last_run_id"):
        payload = export_run(DATABASE, run_id)
        run = payload["run"]
        st.subheader("Run results")
        top_a, top_b, top_c = st.columns(3)
        top_a.metric("RFP_RUN_ID", run["rfp_run_id"])
        top_b.metric("Status", run["status"].upper())
        top_c.metric("Suppliers ranked", len(payload["supplier_results"]))
        if run.get("error_message"):
            st.error("Run failed: " + run["error_message"])
        if payload["supplier_results"]:
            st.markdown("#### Supplier leaderboard")
            st.dataframe([{
                "final_rank": result["final_rank"], "supplier_name": result["supplier_name"],
                "absolute_score": result["absolute_score"], "ppi": result["ppi"],
                "evidence_coverage": result.get("evidence_coverage"), "confidence": result.get("confidence"),
                "review_required": result.get("review_required", False), "submission_date": result["submission_date"],
                "experience_rating": result["experience_rating"],
            } for result in payload["supplier_results"]], hide_index=True, use_container_width=True)
            enriched_results = [result for result in payload["supplier_results"] if "evidence_coverage" in result]
            if len(enriched_results) == len(payload["supplier_results"]):
                enriched_ranked = [RankedSupplier(**result) for result in enriched_results]
                sensitivity = rank_sensitivity(enriched_ranked, criteria)
                anomalies = detect_result_anomalies(enriched_ranked)
                if sensitivity["stable"]:
                    st.success("Weight sensitivity check: increasing any one active criterion by 10 percentage points did not change the recommended supplier.")
                else:
                    changed = ", ".join(item["criterion"] for item in sensitivity["scenarios"] if item["leader_changed"])
                    st.warning("Weight sensitivity check: the recommended supplier changes when these criteria are emphasized: " + changed + ".")
                if anomalies:
                    st.warning("Quality signals: " + " ".join(anomalies))
            else:
                st.info("Evidence-confidence and sensitivity checks will be available on the next evaluation run.")
            st.markdown("#### Evidence scorecards")
            for result in payload["supplier_results"]:
                with st.expander(f"#{result['final_rank']}  {result['supplier_name']}  |  PPI {result['ppi']:.2f}"):
                    st.write(result["overall_summary"])
                    st.info(result["tie_break_explanation"])
                    coverage, confidence = result.get("evidence_coverage"), result.get("confidence")
                    if coverage is not None and confidence is not None:
                        metric_a, metric_b = st.columns(2)
                        metric_a.metric("Verified evidence coverage", f"{coverage:.0%}")
                        metric_b.metric("Weighted confidence", f"{confidence:.0%}")
                    st.dataframe(result["criteria"], hide_index=True, use_container_width=True)
                    if result.get("review_required"):
                        st.warning("Human review recommended: " + " ".join(result.get("review_reasons", [])))
                    if result["warnings"]:
                        st.warning("\n".join(result["warnings"]))
                    if result["risks"]:
                        st.caption("Risks: " + "; ".join(result["risks"]))
            st.download_button("Download complete run JSON", json.dumps(payload, indent=2), file_name=f"{run_id}.json", mime="application/json", type="primary")
    else:
        st.info("Prepare a supplier batch, then start it from the Execution Flow tab to populate this workspace.")
