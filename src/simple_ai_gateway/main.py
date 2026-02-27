import asyncio
import json
import os
import time
import uuid
from collections import defaultdict
from collections.abc import AsyncGenerator
from typing import Literal

import requests
import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

app = FastAPI()

# Read environment variables and set default values
PORT = int(os.getenv("PORT", 8080))
BACKEND_URL = os.getenv("BACKEND_URL", None)

# ========== Rate Limiting Configuration ==========
# Using a dictionary to track request timestamps per IP
# In production, use Redis for distributed rate limiting
request_history = defaultdict(list)
RATE_LIMIT_WINDOW = 60  # seconds
MAX_REQUESTS = 5  # requests per window


def check_rate_limit(client_ip: str):
    """
    In-memory sliding window rate limiter.
    Removes timestamps older than the window and checks current count.
    """
    now = time.time()
    # Remove timestamps older than 60 seconds
    request_history[client_ip] = [
        t for t in request_history[client_ip] if now - t < RATE_LIMIT_WINDOW
    ]

    if len(request_history[client_ip]) >= MAX_REQUESTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
        )

    # Record the new request timestamp
    request_history[client_ip].append(now)


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
    """Generate SSE stream in OpenAI-compatible format."""
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
        await asyncio.sleep(0.05)  # Simulate token-by-token delay

    # Final chunk with finish_reason
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
    chat_req: ChatRequest,  # Avoid naming conflict with FastAPI Request
    http_req: Request,      # For capturing client IP (rate limiting)
    x_request_id: str | None = Header(None, alias="X-Request-ID"),
):
    # 1. Apply Rate Limiting
    client_ip = http_req.client.host
    check_rate_limit(client_ip)

    # 2. Handle Request ID: Use provided header or generate a new UUID
    req_id = x_request_id or str(uuid.uuid4())

    # 3. Extract the last user message as the prompt
    user_prompt = ""
    for msg in reversed(chat_req.messages):
        if msg.role == "user":
            user_prompt = msg.content
            break

    if not user_prompt:
        raise HTTPException(status_code=400, detail="No user message found")

    # 4. Logic Dispatching
    if not BACKEND_URL:
        # Case A: Return Echo response if no backend is configured
        reply_content = f"Echo: {user_prompt}"
    else:
        # Case B: Forward request to the backend
        try:
            # For production, use httpx.AsyncClient for non-blocking I/O.
            # Here, synchronous requests.post is sufficient.
            resp = requests.post(BACKEND_URL, json=chat_req.model_dump(), timeout=10)
            backend_data = resp.json()
            reply_content = backend_data["choices"][0]["message"]["content"]
        except Exception as e:
            reply_content = f"Error calling backend: {str(e)}"

    # 5. Return streaming or regular response
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
            "prompt_tokens": len(user_prompt),
            "completion_tokens": len(reply_content),
            "total_tokens": len(user_prompt) + len(reply_content),
        },
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
