from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from app.database import active_criteria, all_criteria, complete_run, create_run, export_run, fail_run, initialize, update_criteria
from app.evaluator import PROVIDERS, demo_evaluate, evaluate_with_openai, extract_pdf_text
from app.models import LLMScorecard, SupplierInput, ValidatedSupplier
from app.scoring import detect_result_anomalies, normalize_scorecard, rank_sensitivity, rank_suppliers, validate_active_criteria

ROOT = Path(__file__).parent
DATABASE = ROOT / "data" / "rfp_evaluation.db"
DATABASE.parent.mkdir(parents=True, exist_ok=True)
initialize(DATABASE)

st.set_page_config(page_title="Agentic RFP Evaluation", page_icon="🏆", layout="wide")

try:
    secrets = st.secrets.to_dict()
except StreamlitSecretNotFoundError:
    secrets = {}
for key in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"):
    if key in secrets:
        os.environ[key] = str(secrets[key])

st.title("🏆 Agentic RFP Evaluation")
st.caption("Evidence-grounded supplier assessment, deterministic scoring, benchmarking, and auditable ranking.")

with st.sidebar:
    st.header("Evaluation mode")
    mode = st.radio("Evaluator", ["Demo (offline)", "Configured provider"], help="Demo mode requires no API key. Provider mode uses an OpenAI-compatible API.")
    provider = st.selectbox("Provider", list(PROVIDERS), disabled=mode == "Demo (offline)")
    defaults = PROVIDERS[provider]
    api_key = st.text_input("API key", value=os.getenv("OPENAI_API_KEY", ""), type="password", disabled=mode == "Demo (offline)")
    base_url = st.text_input("Base URL", value=os.getenv("OPENAI_BASE_URL", defaults["base_url"]), disabled=mode == "Demo (offline)")
    model = st.text_input("Model", value=os.getenv("OPENAI_MODEL", defaults["model"]), disabled=mode == "Demo (offline)")

criteria_tab, suppliers_tab, results_tab = st.tabs(["Configuration", "Supplier Proposals", "Results"])

with criteria_tab:
    st.subheader("Configuration & Evaluation Metrics")
    criteria = all_criteria(DATABASE)
    st.info(f"Active criteria weight: {sum(c.weight for c in criteria if c.is_active):g}%")
    edited = []
    for criterion in criteria:
        c1, c2, c3 = st.columns([3, 1, 1])
        active = c1.checkbox(criterion.name, value=criterion.is_active, key=f"active-{criterion.criterion_id}")
        weight = c2.number_input("Weight %", min_value=0.0, max_value=100.0, value=float(criterion.weight), step=5.0, key=f"weight-{criterion.criterion_id}")
        c3.caption(criterion.description)
        edited.append(criterion.model_copy(update={"is_active": active, "weight": weight}))
    if st.button("Save criteria", type="primary"):
        try:
            update_criteria(DATABASE, edited)
            st.success("Criteria saved. Active weights total 100%.")
        except ValueError as exc:
            st.error(str(exc))

with suppliers_tab:
    st.subheader("Supplier Proposals")
    st.write("Upload at least two proposal PDFs. Supplier name defaults to the filename; you can edit metadata after upload.")
    uploads = st.file_uploader("Proposal PDFs", type=["pdf"], accept_multiple_files=True)
    supplier_inputs = []
    if uploads:
        for index, upload in enumerate(uploads):
            default_name = Path(upload.name).stem.replace("_", " ").replace("-", " ").title()
            c1, c2, c3 = st.columns([3, 1.5, 1.5])
            name = c1.text_input("Supplier", value=default_name, key=f"supplier-name-{index}")
            submitted = c2.date_input("Submission date", value=date.today(), key=f"submission-date-{index}")
            experience = c3.number_input("Experience rating", min_value=0.0, value=5.0, max_value=10.0, step=1.0, key=f"experience-{index}")
            supplier_inputs.append((upload, SupplierInput(supplier_name=name, submission_date=submitted, experience_rating=experience, document_text="")))
            st.caption(f"📄 {upload.name}")

    if st.button("Evaluate batch", type="primary", disabled=len(supplier_inputs) < 2):
        try:
            criteria = active_criteria(DATABASE)
            validate_active_criteria(criteria)
            names = [item[1].supplier_name.casefold() for item in supplier_inputs]
            if len(names) != len(set(names)):
                raise ValueError("Supplier names must be unique.")
            run_id = create_run(DATABASE)
            validated = []
            with st.status(f"Evaluating {len(supplier_inputs)} suppliers…", expanded=True) as status:
                for upload, supplier in supplier_inputs:
                    text = extract_pdf_text(upload)
                    if mode == "Demo (offline)":
                        raw = demo_evaluate(supplier.supplier_name, text, criteria)
                    else:
                        raw = evaluate_with_openai(supplier.supplier_name, text, criteria, api_key=api_key, base_url=base_url, model=model)
                    normalized, warnings = normalize_scorecard(raw, supplier.supplier_name, criteria, text)
                    validated.append(ValidatedSupplier(supplier=supplier.model_copy(update={"document_text": text}), scorecard=LLMScorecard.model_validate(normalized), warnings=warnings))
                    st.write(f"✓ {supplier.supplier_name}: proposal extracted and scorecard validated")
                results = rank_suppliers(validated, criteria)
                complete_run(DATABASE, run_id, results)
                st.session_state["last_run_id"] = run_id
                st.session_state["last_results"] = results
                st.session_state["last_sensitivity"] = rank_sensitivity(results, criteria)
                st.session_state["last_anomalies"] = detect_result_anomalies(results)
                status.update(label=f"Completed — {run_id}", state="complete")
            st.success(f"Evaluation complete. RFP_RUN_ID: {run_id}")
        except Exception as exc:
            if "run_id" in locals():
                fail_run(DATABASE, run_id, str(exc))
                st.error(f"Evaluation failed. RFP_RUN_ID: {run_id}. {exc}")
            else:
                st.error(str(exc))

with results_tab:
    st.subheader("Results")
    results = st.session_state.get("last_results")
    run_id = st.session_state.get("last_run_id")
    if not results:
        st.info("Run an evaluation batch to see the leaderboard and evidence-backed scorecards.")
    else:
        st.success(f"RFP_RUN_ID: {run_id}")
        rows = [{"Rank": r.final_rank, "Supplier": r.supplier_name, "PPI": r.ppi, "Absolute score": r.absolute_score, "Confidence": f"{r.confidence:.0%}", "Review": "Yes" if r.review_required else "No"} for r in results]
        st.dataframe(rows, use_container_width=True, hide_index=True)
        if st.session_state.get("last_anomalies"):
            st.warning(" | ".join(st.session_state["last_anomalies"]))
        sensitivity = st.session_state.get("last_sensitivity", {})
        st.caption(f"Weight sensitivity stable: {'Yes' if sensitivity.get('stable', True) else 'No'}")
        selected = st.selectbox("Supplier detail", [r.supplier_name for r in results])
        result = next(r for r in results if r.supplier_name == selected)
        st.markdown(f"### #{result.final_rank} {result.supplier_name}")
        st.write(result.tie_break_explanation)
        for row in result.criteria:
            with st.expander(f"{row['name']} — {row['score']:g}/{row['max_score']:g}"):
                st.write(f"**Justification:** {row['justification'] or 'Not supplied'}")
                st.write(f"**Evidence:** {row['evidence'] or 'No evidence supplied'}")
                st.write(f"**Page:** {row['evidence_page'] or '—'} · **Verified:** {'Yes' if row['evidence_verified'] else 'No'} · **Confidence:** {row['confidence']:.0%}")
                st.write(f"**Benchmark:** {row['benchmark']:g} · **Gap:** {row['gap']:g} · **Relative:** {row['relative_percent']:.1f}%")
        if result.risks:
            st.warning("Risks: " + " | ".join(result.risks))
        st.download_button("Download run JSON", data=json.dumps(export_run(DATABASE, run_id), indent=2), file_name=f"{run_id}.json", mime="application/json")
