"""Run the retention jobs: purge expired session content (60 min) and old metadata (30 days)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.db.session import SessionLocal, init_db  # noqa: E402
from app.documents.service import run_retention  # noqa: E402


def main() -> None:
    init_db()
    with SessionLocal() as db:
        print(run_retention(db))


if __name__ == "__main__":
    main()
