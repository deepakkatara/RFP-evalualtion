from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import initialize

DATABASE = ROOT / "data" / "rfp_evaluation.db"
DATABASE.parent.mkdir(parents=True, exist_ok=True)
initialize(DATABASE)
print("Initialized SQLite database with active criteria totaling 100%.")
