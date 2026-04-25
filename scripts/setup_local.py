from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VENV_DIR = ROOT / ".venv"
IS_WINDOWS = os.name == "nt"
VENV_PYTHON = VENV_DIR / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")


def run(*args: str) -> None:
    subprocess.run(list(args), check=True, cwd=ROOT)


def ensure_python_version() -> None:
    if sys.version_info < (3, 11):
        raise SystemExit("Python 3.11+ is required.")


def ensure_venv() -> None:
    if not VENV_DIR.exists():
        print("Creating Python virtual environment...")
        run(sys.executable, "-m", "venv", str(VENV_DIR))


def install_requirements() -> None:
    print("Installing Python dependencies...")
    run(str(VENV_PYTHON), "-m", "pip", "install", "--upgrade", "pip")
    run(str(VENV_PYTHON), "-m", "pip", "install", "-r", "app/requirements.txt")


def install_playwright() -> None:
    print("Installing Playwright Chromium...")
    run(str(VENV_PYTHON), "-m", "playwright", "install", "chromium")


def check_lighthouse() -> None:
    if shutil.which("npx") is None:
        print("Node.js/npx not found. Install Node.js so Lighthouse can run via npx or npm.")
    else:
        print("npx found on PATH. Lighthouse can run via npx.")


def ensure_env_template() -> None:
    env_path = ROOT / ".env"
    if env_path.exists():
        print(".env already exists; leaving it unchanged.")
        return

    env_path.write_text(
        "\n".join(
            [
                "GEMINI_API_KEY=your_key_here",
                "PLA_LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai",
                "PLA_LLM_MODEL=models/gemini-2.5-flash",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print("Created .env template. Fill in your API key before running.")


def main() -> None:
    print("Playwright Lighthouse Analysis local setup")
    print(f"Repository: {ROOT}")
    ensure_python_version()
    print(f"Python: {sys.version.split()[0]}")
    ensure_venv()
    install_requirements()
    install_playwright()
    check_lighthouse()
    ensure_env_template()

    print("\nSetup complete.")
    print("Next:")
    print("  1. Edit .env if needed")
    if IS_WINDOWS:
        print("  2. python scripts\\run_local.py")
    else:
        print("  2. python3 scripts/run_local.py")


if __name__ == "__main__":
    main()
