import os
import uuid
import json
import asyncio
import requests
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from typing import List, Optional, Literal, AsyncGenerator
import uvicorn
app = FastAPI()

# Read environment variables and set default values
PORT = int(os.getenv("PORT", 8080))
BACKEND_URL = os.getenv("BACKEND_URL", None)


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
    messages: List[Message]
    stream: bool = False

    @field_validator("messages")
    @classmethod
    def messages_not_empty(cls, v: List[Message]) -> List[Message]:
        if not v:
            raise ValueError("messages list cannot be empty")
        return v


class ChatResponse(BaseModel):
    id: str
    choices: List[dict]
    usage: dict


# ========== Streaming Helper ==========

async def generate_stream(req_id: str, content: str) -> AsyncGenerator[str, None]:
    """Generate SSE stream in OpenAI-compatible format."""
    words = content.split()

    for i, word in enumerate(words):
        chunk = {
            "id": req_id,
            "object": "chat.completion.chunk",
            "choices": [{
                "index": 0,
                "delta": {
                    "role": "assistant",
                    "content": word + " "
                } if i == 0 else {"content": word + " "},
                "finish_reason": None
            }]
        }
        yield f"data: {json.dumps(chunk)}\n\n"
        await asyncio.sleep(0.05)  # Simulate token-by-token delay

    # Final chunk with finish_reason
    final_chunk = {
        "id": req_id,
        "object": "chat.completion.chunk",
        "choices": [{
            "index": 0,
            "delta": {},
            "finish_reason": "stop"
        }]
    }
    yield f"data: {json.dumps(final_chunk)}\n\n"
    yield "data: [DONE]\n\n"


# ========== Endpoint ==========

@app.post("/v1/chat/completions")
async def chat_completion(
    request: ChatRequest,
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID")
):
    # 1. Handle Request ID: Use provided header or generate a new UUID
    req_id = x_request_id or str(uuid.uuid4())

    # 2. Extract the last user message as the prompt
    user_prompt = ""
    for msg in reversed(request.messages):
        if msg.role == "user":
            user_prompt = msg.content
            break

    if not user_prompt:
        raise HTTPException(status_code=400, detail="No user message found")

    # 3. Logic Dispatching
    if not BACKEND_URL:
        # Case A: Return Echo response if no backend is configured
        reply_content = f"Echo: {user_prompt}"
    else:
        # Case B: Forward request to the backend
        try:
            resp = requests.post(BACKEND_URL, json=request.model_dump(), timeout=10)
            # Extract content from backend response (assuming OpenAI-compatible shape)
            backend_data = resp.json()
            reply_content = backend_data["choices"][0]["message"]["content"]
        except Exception as e:
            reply_content = f"Error calling backend: {str(e)}"

    # 4. Return streaming or regular response
    if request.stream:
        return StreamingResponse(
            generate_stream(req_id, reply_content),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )

    return {
        "id": req_id,
        "choices": [{
            "message": {"role": "assistant", "content": reply_content},
            "finish_reason": "stop"
        }],
        "usage": {
            "prompt_tokens": len(user_prompt),
            "completion_tokens": len(reply_content),
            "total_tokens": len(user_prompt) + len(reply_content)
        }
    }

def main():                                                                                                                                                                                                                                             
    uvicorn.run("simple_ai_gateway.main:app", host="0.0.0.0", port=PORT, reload=False)                                                                  
    if __name__ == "__main__":                                                                                                            
      main()