import os
import uuid
import requests
from fastapi import FastAPI, Request, Header
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI()

# Read environment variables and set default values
PORT = int(os.getenv("PORT", 8080))
BACKEND_URL = os.getenv("BACKEND_URL", None)

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[Message]

class ChatResponse(BaseModel):
    id: str
    choices: List[dict]
    usage: dict

@app.post("/v1/chat/completions", response_model=ChatResponse)
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

    # 3. Logic Dispatching
    if not BACKEND_URL:
        # Case A: Return Echo response if no backend is configured
        reply_content = f"Echo: {user_prompt}"
    else:
        # Case B: Forward request to the backend
        try:
            resp = requests.post(BACKEND_URL, json=request.dict(), timeout=10)
            # Extract content from backend response (assuming OpenAI-compatible shape)
            backend_data = resp.json()
            reply_content = backend_data["choices"][0]["message"]["content"]
        except Exception as e:
            reply_content = f"Error calling backend: {str(e)}"

    # 4. Construct standardized response
    return {
        "id": req_id,
        "choices": [{
            "message": {"role": "assistant", "content": reply_content},
            "finish_reason": "stop"
        }],
        "usage": {
            "prompt_tokens": len(user_prompt), # 简单模拟
            "completion_tokens": len(reply_content),
            "total_tokens": len(user_prompt) + len(reply_content)
        }
    }