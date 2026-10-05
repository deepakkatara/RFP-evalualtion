# Agentic RFP Evaluation and Supplier Ranking

[![Open live Streamlit app](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://rfp-evalualtion-z87z4g7e6beqkslddtsdsi.streamlit.app/)

**🚀 [Open the live RFP Evaluation app](https://rfp-evalualtion-z87z4g7e6beqkslddtsdsi.streamlit.app/)**

A Streamlit application that reads supplier RFP PDFs, obtains criterion-level evidence-grounded LLM scorecards, validates them, and calculates reproducible supplier rankings.

## Design principle

The LLM assesses only proposal evidence. Python owns validation, weighted arithmetic, peer benchmarks, PPI, mandatory tie-breaks, and final ranks. This keeps the outcome explainable and deterministic once scorecards have been validated.

## Project structure

```text
app/                 domain models, SQLite persistence, PDF/LLM evaluation, scoring
assets/rfps/         four synthetic supplier responses
data/                generated SQLite database (not committed)
scripts/             database and sample-document generators
tests/               deterministic scoring tests
streamlit_app.py     user interface and batch orchestrator
```

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/init_db.py
streamlit run streamlit_app.py
```

The app works immediately in **Demo** mode for an offline reproducible walkthrough. For evidence-grounded LLM evaluation, configure an OpenAI-compatible provider through Streamlit secrets or the Provider connection panel.

### Provider configuration

Create `.streamlit/secrets.toml` locally from `.streamlit/secrets.toml.example`, or add the same values in Streamlit Community Cloud Secrets:

```toml
OPENAI_API_KEY = "your-key"
OPENAI_BASE_URL = "https://openrouter.ai/api/v1"
OPENAI_MODEL = "openai/gpt-4o-mini"
```

The secret file is ignored by Git. Never commit API keys.

## Architecture

1. Streamlit loads active criteria from SQLite.
2. A user uploads supplier PDFs and enters metadata.
3. The orchestrator creates a persistent `RFP_RUN_ID` with status `running`, then extracts text with `pypdf`.
4. The evaluator builds a prompt from the current active criteria and requests JSON-only LLM output.
5. The validator ignores unknown criteria, fills omissions with zero, clips invalid scores, and retains warnings.
6. The deterministic ranking tool calculates all formulas and applies the required stable tie-break order.
7. The application persists either a `completed` result or a `failed` run with an error message under one `RFP_RUN_ID`, then displays scorecards and exports JSON.

## Formulae and business rules

- Absolute score = sum `(criterion score / maximum score) × criterion weight`
- Criterion benchmark = the highest valid supplier score for that criterion
- Gap = supplier score - benchmark
- Relative % = `(supplier score / benchmark) × 100`; a zero benchmark is treated as 100% for every supplier because all suppliers match it
- PPI = weighted average of criterion relative percentages
- Rank sort = higher PPI, earlier submission date, higher experience rating, supplier name ascending

The default active criteria are Technical Capability (30%), Implementation Plan (20%), Commercial Value (20%), Security & Compliance (20%), and Support & Experience (10%). SQLite is the source of truth for active criteria and weights.

## Deploy to Streamlit Community Cloud

The repository is configured for Streamlit Community Cloud:

- `runtime.txt` selects Python 3.11.
- `requirements.txt` pins the application dependencies.
- `.streamlit/config.toml` sets the upload limit and visual theme.
- `.streamlit/secrets.toml.example` documents the optional LLM secret without exposing one.
- GitHub Actions runs the deterministic tests on every push and pull request.

1. Open Streamlit Community Cloud and create a new app.
2. Select repository `deepakkatara/RFP-evalualtion`, branch `main`, and entry point `streamlit_app.py`.
3. Add `OPENAI_API_KEY`, `OPENAI_BASE_URL` (if using OpenRouter), and `OPENAI_MODEL` in Advanced settings → Secrets for live LLM evaluation.
4. Without a key, the Demo provider remains usable for a complete offline walkthrough.

## Testing

```bash
python -m unittest discover -s tests -v
```

The test suite covers database initialization, workflow tracing, scoring validation, evidence verification, deterministic ranking, sensitivity checks, and the Streamlit UI.
