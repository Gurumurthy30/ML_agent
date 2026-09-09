import json
import re
import urllib.request
import urllib.error
from typing import Dict, Any, Optional
from config.settings import get_settings

def call_llm(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    max_tokens: int = 2048
) -> str:
    """
    Calls the local llama-server OpenAI-compatible /v1/chat/completions endpoint.
    If the endpoint is unreachable or fails, raises a clear RuntimeError unless mock mode is active.
    """
    settings = get_settings()
    server_url = settings.model.server_url.rstrip("/")
    endpoint = f"{server_url}/chat/completions"

    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": temperature,
        "max_tokens": max_tokens
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=data,
        headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body["choices"][0]["message"]["content"]
    except urllib.error.URLError as e:
        # If server is unreachable and mock mode is enabled, caller can handle fallback
        raise RuntimeError(
            f"[LLM SERVER ERROR] Could not connect to llama-server at '{endpoint}'.\n"
            "Please start the model server using 'model_server/launch_llama_server.sh' or verify model.server_url in settings.yaml."
        ) from e
    except Exception as e:
        raise RuntimeError(f"[LLM ERROR] Exception during LLM generation: {str(e)}") from e

def extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Extracts a JSON dictionary from LLM markdown response."""
    try:
        return json.loads(text)
    except Exception:
        pass
    
    # Match ```json ... ```
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass

    # Find raw JSON dict braces
    match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass

    return None
