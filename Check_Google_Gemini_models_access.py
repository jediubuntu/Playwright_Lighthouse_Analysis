from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def get_api_key() -> str:
    api_key = (
        os.getenv("PLA_LLM_API_KEY")
        or os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    )
    if not api_key:
        raise RuntimeError(
            "Missing API key. Set PLA_LLM_API_KEY, GEMINI_API_KEY, GOOGLE_API_KEY, or OPENAI_API_KEY in .env."
        )
    return api_key


def get_base_url() -> str:
    return os.getenv("PLA_LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai").rstrip("/")


def list_models(base_url: str, api_key: str) -> list[dict]:
    request = Request(
        f"{base_url}/models",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
        method="GET",
    )
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("data", [])


def test_model(base_url: str, api_key: str, model: str) -> tuple[bool, str]:
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with exactly: ok"}],
        "temperature": 0,
    }
    request = Request(
        f"{base_url}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8"))
        content = payload["choices"][0]["message"]["content"]
        if isinstance(content, list):
            text_parts = [
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and isinstance(part.get("text"), str)
            ]
            content = "\n".join(part for part in text_parts if part).strip()
        return True, str(content)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return False, f"HTTP {exc.code}: {body}"


def main() -> None:
    load_dotenv(Path(__file__).resolve().with_name(".env"))

    api_key = get_api_key()
    base_url = get_base_url()

    print(f"Base URL: {base_url}")
    print("Listing available models...\n")

    try:
        models = list_models(base_url, api_key)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code}")
        print(body)
        return
    except URLError as exc:
        print(f"Network error: {exc.reason}")
        return

    if not models:
        print("No models returned.")
        return

    print(f"Found {len(models)} model(s):")
    for item in models:
        model_id = item.get("id", "<unknown>")
        owned_by = item.get("owned_by")
        if owned_by:
            print(f"- {model_id} (owned_by={owned_by})")
        else:
            print(f"- {model_id}")

    print("\nTesting chat completions access for each model...\n")
    for item in models:
        model_id = item.get("id")
        if not model_id:
            continue
        ok, result = test_model(base_url, api_key, model_id)
        status = "OK" if ok else "FAIL"
        print(f"[{status}] {model_id}")
        print(f"  {result}\n")


if __name__ == "__main__":
    main()
