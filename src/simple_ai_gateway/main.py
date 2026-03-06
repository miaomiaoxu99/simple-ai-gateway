import asyncio
import json
import os
import time
import uuid
from pathlib import Path
import yaml
import httpx
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import AsyncGenerator
from typing import Literal, Optional, List, Dict, Any
from .backends import get_backend_instance

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

def get_limiter(config):                                                                                                                          
      rl_config = config.get("rate_limiter", {})                                                                                                    
      storage_type = rl_config.get("storage", "memory")                                                                                             
                                                                                                                                                    
      if storage_type == "redis":                                                                                                                   
          try:                                                                                                                                      
              import redis                                                                                                                          
          except ImportError:                                                                                                                       
              raise RuntimeError(                                                                                                                   
                  "Redis storage configured but 'redis' package not installed. "                                                                    
                  "Install with: uv pip install -e '.[redis]'"                                                                                      
              )                                                                                                                                     
                                                                                                                                                    
          redis_url = rl_config.get("redis_url", "redis://localhost:6379")                                                                          
          try:                                                                                                                                      
              r = redis.from_url(redis_url)                                                                                                         
              r.ping()                                                                                                                              
          except redis.ConnectionError as e:                                                                                                        
              raise RuntimeError(f"Cannot connect to Redis at {redis_url}: {e}")                                                                    
                                                                                                                                                    
          print(f"Rate limiter using Redis: {redis_url}")                                                                                           
          return Limiter(key_func=get_remote_address, storage_uri=redis_url)                                                                        
                                                                                                                                                    
      print("Rate limiter using in-memory storage")                                                                                                 
      return Limiter(key_func=get_remote_address) 

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

limiter = get_limiter(CONFIG)
app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
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

@app.middleware("http")
async def track_queue_time(request: Request, call_next):
    request.state.arrival_time = time.perf_counter()
    response = await call_next(request)
    return response

@app.post("/v1/chat/completions")
@limiter.limit("5/minute")
async def chat_completion(
    chat_req: ChatRequest,
    request: Request,
    x_request_id: str | None = Header(None, alias="X-Request-ID"),
):  
    queue_time = time.perf_counter() - request.state.arrival_time
    # 1. Apply Rate Limiting
    execution_start = time.perf_counter()
    # check_rate_limit(request.client.host)

    # 2. Handle Request ID
    req_id = x_request_id or str(uuid.uuid4())

    try:
        # 3. Dynamic Routing & Interface Usage
        backend_executor = get_backend_instance(chat_req.model, CONFIG)
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
    execution_time = time.perf_counter() - execution_start
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
        "metrics" :{
            "queue_time": queue_time,
            "tftt": execution_time
        }
    }

def main():
    uvicorn.run(app, host="0.0.0.0", port=PORT) 
if __name__ == "__main__":
    main()
