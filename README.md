# Simple AI Gateway

A lightweight AI API Gateway built with Python and **FastAPI**. It follows the OpenAI-compatible request format and can be configured to either echo back prompts or forward them to a real AI inference backend.

## 🚀 Quick Start

### 1. Prerequisites
Ensure you have [uv](https://docs.astral.sh/uv/) installed. `uv` is an extremely fast Python package manager that replaces `pip` and `venv`.

```bash
# If you don't have uv yet (macOS)
brew install uv
```

### 2. Installation & Environment Setup
uv will automatically manage your virtual environment and dependencies based on pyproject.toml.
```bash
# Clone the repository
git clone <your-repo-url>
cd simple-ai-gateway/src/simple_ai_gateway

# Sync dependencies and create a virtual environment automatically
uv sync
```

### 3. Configuration
The gateway uses a config.yaml file for routing. Ensure this file exists in the same directory as main.py.

Sample config.yaml:
```YAML
default_backend: local

backends:
  local:
    type: local
    url: http://127.0.0.1:8081
  modal:
    type: modal
    url: https:/YOUR_MODAL_URL
  modal_vllm:
    type: vllm
    url: https://YOUR_MODAL_VLLM_URL
```

### 4. Run the Server
Start the server.
```bash
uv run main.py
```

### 5. Testing the Gateway
Start the server at 8080:
```bash
uv run uvicorn main:app --host 0.0.0.0 --port 8080
```

Once the server is at http://localhost:8080, you can verify it using the following methods:

#### Method 1: Basic Echo Test (via cURL)
Test if the gateway correctly extracts your message and echoes it back:
```bash
curl -X POST http://localhost:8080/v1/chat/completions \
-H "Content-Type: application/json" \
-H "X-Request-ID: my-custom-id-123" \
-d '{
  "messages": [
    {"role": "user", "content": "Hello, world!"}
  ]
}'

```

What to look for:
*  The response should contain "content": "Echo: Hello, world!".
*  The "id" field should match "my-custom-id-123".

#### Method 2: Auto-ID Generation Test
If you don't provide an X-Request-ID header, the gateway will generate a unique UUID for you:
```bash
curl -X POST http://localhost:8080/v1/chat/completions \
-H "Content-Type: application/json" \
-d '{
  "messages": [{"role": "user", "content": "Hi, baby!"}]
}'

```
What to look for: A valid UUID in the "id" field (e.g., 550e8400-e29b-...).

#### Method 3: Streaming Test
Test the Server-Sent Events (SSE) streaming functionality. Use the -N flag to disable buffering and see the "typewriter" effect:
```bash
curl -N -X POST http://localhost:8080/v1/chat/completions \
-H "Content-Type: application/json" \
-d '{
  "stream": true,
  "messages": [{"role": "user", "content": "This is a streaming test."}]
}'
```

What to look for: The response should arrive in chunks (prefixes of data: {...}) rather than all at once.

#### Method 4: Rate Limiting Test
The gateway is configured to allow 5 requests per minute per IP. You can test this by running a quick loop:
```bash
for i in {1..6}; do 
  curl -s -o /dev/null -w "Request $i: %{http_code}\n" -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "ping"}]}'; 
done
```
What to look for: The first 5 requests should return 200, and the 6th request should return 429 (Too Many Requests).


#### Method 5: Interactive API Docs
FastAPI automatically generates a Swagger UI. You can test the API directly from your browser: http://localhost:8080/docs

### 6. Routing Verification

#### Method 1: Local Route (Echo)
Verify that specifying the local model triggers the local echo backend:

```bash
curl -s -X POST http://localhost:8080/v1/chat/completions \
-H "Content-Type: application/json" \
-d '{"model": "local", "messages": [{"role": "user", "content": "Hello local"}]}'
```

Expected Response:

```JSON
{
  "id": "...",
  "choices": [{"message": {"role": "assistant", "content": "Echo: Hello local"}, "finish_reason": "stop"}],
  "usage": {"total_tokens": 17}
}
```

#### Method 2: Remote Route - Non-Streaming
Verify forwarding to a remote inference backend (e.g., TinyLlama on Modal).
```bash
curl -s -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"modal","stream":false,"messages":[{"role":"user","content":"What is the capital city in US"}]}'
```

Expected Response:
Note: The content will vary depending on the specific model (e.g., TinyLlama) deployed on your backend.

```JSON
{
  "id": "cffcf1de-30d6-4a1c-b06b-b56af8ef7d46",
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": " Yes, the capital city of the United States is Washington D.C."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 0,
    "completion_tokens": 62,
    "total_tokens": 62
  }
}
```

#### Method 3: Remote Route - Streaming
Verify the gateway's ability to handle Server-Sent Events (SSE). Use the `-N` flag to disable buffering and observe the real-time token generation.

```bash
curl -s -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"modal","stream":true,"messages":[{"role":"user","content":"What is the capital city in US"}]}'
```

Example Response (Chunks):
```Plaintext
data: {"id": "170a33e4-db0d-4803-983e-09dcccc048cd", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {"role": "assistant", "content": "Boston, "}, "finish_reason": null}]}
data: {"id": "170a33e4-db0d-4803-983e-09dcccc048cd", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {"content": "Massachusetts "}, "finish_reason": null}]}
...
data: {"id": "170a33e4-db0d-4803-983e-09dcccc048cd", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {"content": "The "}, "finish_reason": null}]}
data: {"id": "170a33e4-db0d-4803-983e-09dcccc048cd", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {"content": "Star "}, "finish_reason": null}]}
data: {"id": "170a33e4-db0d-4803-983e-09dcccc048cd", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {"content": "Spangled "}, "finish_reason": null}]}
data: {"id": "170a33e4-db0d-4803-983e-09dcccc048cd", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {"content": "Banner "}, "finish_reason": null}]}
data: {"id": "170a33e4-db0d-4803-983e-09dcccc048cd", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
data: [DONE]
```

#### Method 4: Fallback Logic (Missing Model)
Verify that an unknown model correctly falls back to the default_backend (local):

```bash
curl -s -X POST http://localhost:8080/v1/chat/completions \
-H "Content-Type: application/json" \
-d '{"model": "unknown-model", "messages": [{"role": "user", "content": "Where am I?"}]}'
```
Expect: Response content prefixed with `Echo:`  if `default_backend` is set to `local`.


### 7. Features
* Interface Driven: Clean `generate()` contract for all backend.
* Dynamic Routing: Route requests based on the `model` field in the payload.
* Config-Driven: Add or update backends in `config.yaml` with zero code changes.
* Streaming: Supports SSE-based streaming responses.
* Rate Limiting: Built-in memory-based sliding window protection.




