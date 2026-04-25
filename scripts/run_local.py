from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VENV_DIR = ROOT / ".venv"
IS_WINDOWS = os.name == "nt"
VENV_PYTHON = VENV_DIR / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")


def main() -> None:
    if not VENV_PYTHON.exists():
        raise SystemExit("Missing .venv. Run `python scripts/setup_local.py` first.")

    port = os.getenv("PORT", "8011")
    app_url = f"http://127.0.0.1:{port}"

    print("Starting Playwright Lighthouse Analysis...")
    print(f"App URL: {app_url}")
    print(f"Open: {app_url}")
    print()

    raise SystemExit(
        subprocess.run(
            [str(VENV_PYTHON), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", port],
            cwd=ROOT,
        ).returncode
    )


if __name__ == "__main__":
    main()
