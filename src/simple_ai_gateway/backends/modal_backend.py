import json
import httpx

from .backend_interface import Backend


def _chat_to_prompt(messages: list) -> str:
    """Convert chat messages into a single prompt string for completion-style backends."""
    lines: list[str] = []
    for m in messages:
        role = (m.role or "user").strip()
        if role == "system":
            lines.append(f"System: {m.content.strip()}")
        elif role == "assistant":
            lines.append(f"Assistant: {m.content.strip()}")
        else:
            lines.append(f"User: {m.content.strip()}")
    lines.append("Assistant:")
    return "\n".join(lines).strip()


class ModalBackend(Backend):
    """Calls the Modal llama app (/completion endpoint)."""
    def __init__(self, url: str):
        self.base_url = url.rstrip("/")

    async def generate(self, chat_req: "ChatRequest") -> str:
        prompt = _chat_to_prompt(chat_req.messages)
        payload = {"prompt": prompt, "stream": False}
        # Modal scales to zero; first request can take 30–90s (cold start).
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                # First, try the JSON body format used by this repo's Modal app.
                try:
                    resp = await client.post(
                        f"{self.base_url}/completion", json=payload
                    )
                    resp.raise_for_status()
                except httpx.HTTPStatusError as e:
                    # Some deployed versions expect a ?request=... query param (often with POST).
                    if e.response.status_code in (422, 405):
                        resp = await client.post(
                            f"{self.base_url}/completion",
                            params={"request": json.dumps(payload)},
                            timeout=120.0,
                        )
                        resp.raise_for_status()
                    else:
                        raise
                data = resp.json()
                # llama.cpp /completion typically returns {"content": "..."}.
                if isinstance(data, dict):
                    if "content" in data and isinstance(data["content"], str):
                        return data["content"]
                    # Fallback for OpenAI-like wrappers.
                    choices = data.get("choices")
                    if isinstance(choices, list) and choices:
                        msg = (choices[0] or {}).get("message") or {}
                        content = (msg or {}).get("content")
                        if isinstance(content, str):
                            return content
                return ""
            except Exception as e:
                # Make backend errors easier to debug by surfacing status code and body.
                if isinstance(e, httpx.HTTPStatusError) and e.response is not None:
                    body_snippet = (e.response.text or "")[:500]
                    return (
                        f"Backend Error ({self.base_url}): "
                        f"HTTP {e.response.status_code} - {body_snippet}"
                    )
                err_msg = str(e).strip() or repr(e) or type(e).__name__
                hint = ""
                try:
                    if isinstance(e, httpx.TimeoutException):
                        hint = " (Modal may be cold—first request can take 30–60s)"
                    elif isinstance(e, (httpx.ConnectError, httpx.NetworkError)):
                        hint = " (check network / Modal URL)"
                except AttributeError:
                    pass
                return f"Backend Error ({self.base_url}): {type(e).__name__}: {err_msg}{hint}"