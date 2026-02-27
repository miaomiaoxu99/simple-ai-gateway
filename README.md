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

### 3. Create a .env file in the root directory:
```bash
PORT=8080
BACKEND_URL=  # Leave empty to enable "Echo Mode"
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

Method 1: Basic Echo Test (via cURL)
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

Method 2: Auto-ID Generation Test
If you don't provide an X-Request-ID header, the gateway will generate a unique UUID for you:
```bash
curl -X POST http://localhost:8080/v1/chat/completions \
-H "Content-Type: application/json" \
-d '{
  "messages": [{"role": "user", "content": "Hi, baby!"}]
}'

```
What to look for: A valid UUID in the "id" field (e.g., 550e8400-e29b-...).

Method 3: Streaming Test
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

Method 4: Rate Limiting Test
The gateway is configured to allow 5 requests per minute per IP. You can test this by running a quick loop:
```bash
for i in {1..6}; do 
  curl -s -o /dev/null -w "Request $i: %{http_code}\n" -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "ping"}]}'; 
done
```
What to look for: The first 5 requests should return 200, and the 6th request should return 429 (Too Many Requests).


Method 5: Interactive API Docs
FastAPI automatically generates a Swagger UI. You can test the API directly from your browser: http://localhost:8080/docs


### 6. Features
* Format Validation: Strict Pydantic models for OpenAI compatibility.
* Streaming: Supports SSE-based streaming responses.
* Rate Limiting: Built-in memory-based sliding window protection.




