import os
import uuid
import requests
from fastapi import FastAPI, Request, Header
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI()

# 读取环境变量，设置默认值
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
    # 1. 处理 Request ID
    req_id = x_request_id or str(uuid.uuid4())
    
    # 2. 提取最后一条用户消息
    user_prompt = ""
    for msg in reversed(request.messages):
        if msg.role == "user":
            user_prompt = msg.content
            break

    # 3. 逻辑分发
    if not BACKEND_URL:
        # 情况 A: 返回 Echo
        reply_content = f"Echo: {user_prompt}"
    else:
        # 情况 B: 转发到后端
        try:
            resp = requests.post(BACKEND_URL, json=request.dict(), timeout=10)
            # 这里简单起见直接取后端返回的 content，实际可根据需要调整
            backend_data = resp.json()
            reply_content = backend_data["choices"][0]["message"]["content"]
        except Exception as e:
            reply_content = f"Error calling backend: {str(e)}"

    # 4. 构造统一响应
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