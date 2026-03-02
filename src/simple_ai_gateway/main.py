import asyncio
import json
import os
import time
import uuid
from pathlib import Path
import yaml
import httpx
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import AsyncGenerator
from typing import Literal, Optional, List, Dict, Any

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

app = FastAPI()

# Backend Configuration Logic.
def load_config():
    # Resolve relative to this file so it works from any CWD.
    cfg_env = (os.getenv("SIMPLE_AI_GATEWAY_CONFIG") or "").strip()
    cfg_path = (
        Path(cfg_env).expanduser()
        if cfg_env
        else (Path(__file__).resolve().parent / "config.yaml")
    )
    with open(cfg_path, "r") as f:
        return yaml.safe_load(f)

CONFIG = load_config()

# Read environment variables and set default values
PORT = int(os.getenv("PORT", 8080))

# ========== Rate Limiting Configuration ==========
request_history = defaultdict(list)
RATE_LIMIT_WINDOW = 60
MAX_REQUESTS = 5

def check_rate_limit(client_ip: str):
    now = time.time()
    request_history[client_ip] = [
        t for t in request_history[client_ip] if now - t < RATE_LIMIT_WINDOW
    ]
    if len(request_history[client_ip]) >= MAX_REQUESTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
        )
    request_history[client_ip].append(now)

# ========== Backend Interface & Strategy Implementation ==========

class Backend(ABC):
    @abstractmethod
    async def generate(self, chat_req: "ChatRequest") -> str:
        pass

class EchoBackend(Backend):
    """Handles 'local' type - using your existing echo logic"""
    async def generate(self, chat_req: "ChatRequest") -> str:
        user_prompt = ""
        for msg in reversed(chat_req.messages):
            if msg.role == "user":
                user_prompt = msg.content
                break
        return f"Echo: {user_prompt}"

def _chat_to_prompt(messages: list["Message"]) -> str:
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

class RemoteBackend(Backend):
    """Handles 'modal', 'vllm', and any remote HTTP backends"""
    def __init__(self, url: str):
        self.url = url

    async def generate(self, chat_req: "ChatRequest") -> str:
        async with httpx.AsyncClient() as client:
            try:
                # Forwarding request to the URL specified in config.yaml
                resp = await client.post(self.url, json=chat_req.model_dump(), timeout=20.0)
                resp.raise_for_status()
                backend_data = resp.json()
                return backend_data["choices"][0]["message"]["content"]
            except Exception as e:
                return f"Backend Error ({self.url}): {str(e)}"

def get_backend_instance(model_name: Optional[str]) -> Backend:
    """
    Updated Factory to match your new config structure.
    """
    # 1. Look up the model in config, default to 'local' if missing
    backend_cfg = CONFIG["backends"].get(model_name)
    if not backend_cfg:
        backend_cfg = CONFIG["backends"][CONFIG["default_backend"]]
    
    b_type = backend_cfg.get("type")
    b_url = backend_cfg.get("url")

    # 2. Map types to Classes
    if b_type == "local":
        return EchoBackend()
    elif b_type == "modal":
        return ModalBackend(url=b_url)
    elif b_type in ["vllm", "remote"]:
        # These all use the same RemoteBackend logic but different URLs
        return RemoteBackend(url=b_url)
    
    raise ValueError(f"Unknown backend type: {b_type}")

# ========== Models with Validation ==========

class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str

    @field_validator("content")
    @classmethod
    def content_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("content cannot be empty")
        return v

class ChatRequest(BaseModel):
    messages: list[Message]
    model: Optional[str] = None  # Added for dynamic routing
    stream: bool = False

    @field_validator("messages")
    @classmethod
    def messages_not_empty(cls, v: list[Message]) -> list[Message]:
        if not v:
            raise ValueError("messages list cannot be empty")
        return v

class ChatResponse(BaseModel):
    id: str
    choices: list[dict]
    usage: dict

# ========== Streaming Helper ==========

async def generate_stream(req_id: str, content: str) -> AsyncGenerator[str, None]:
    words = content.split()
    for i, word in enumerate(words):
        chunk = {
            "id": req_id,
            "object": "chat.completion.chunk",
            "choices": [
                {
                    "index": 0,
                    "delta": (
                        {"role": "assistant", "content": word + " "}
                        if i == 0
                        else {"content": word + " "}
                    ),
                    "finish_reason": None,
                }
            ],
        }
        yield f"data: {json.dumps(chunk)}\n\n"
        await asyncio.sleep(0.05)

    final_chunk = {
        "id": req_id,
        "object": "chat.completion.chunk",
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(final_chunk)}\n\n"
    yield "data: [DONE]\n\n"

# ========== Endpoint ==========

@app.post("/v1/chat/completions")
async def chat_completion(
    chat_req: ChatRequest,
    http_req: Request,
    x_request_id: str | None = Header(None, alias="X-Request-ID"),
):
    # 1. Apply Rate Limiting
    check_rate_limit(http_req.client.host)

    # 2. Handle Request ID
    req_id = x_request_id or str(uuid.uuid4())

    try:
        # 3. Dynamic Routing & Interface Usage
        backend_executor = get_backend_instance(chat_req.model)
        reply_content = await backend_executor.generate(chat_req)
    except Exception as e:
        reply_content = f"Gateway Error: {type(e).__name__}: {e}"

    # 4. Return streaming or regular response
    if chat_req.stream:
        return StreamingResponse(
            generate_stream(req_id, reply_content),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    return {
        "id": req_id,
        "choices": [
            {
                "message": {"role": "assistant", "content": reply_content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0, # Placeholder
            "completion_tokens": len(reply_content),
            "total_tokens": len(reply_content),
        },
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)