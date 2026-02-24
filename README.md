# Simple AI Gateway

A lightweight AI API Gateway built with Python and **FastAPI**. It follows the OpenAI-compatible request format and can be configured to either echo back prompts or forward them to a real AI inference backend.

## 🚀 Quick Start

### 1. Prerequisites
Ensure you have Python 3.9+ installed. It is highly recommended to use a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate  # Mac/Linux
pip install -r requirements.txt

```

### 2. Environment Setup (Optional)
Create a .env file in the root directory.
```bash
PORT=8080
BACKEND_URL=  # Leave empty to enable "Echo Mode"
```

### 3. Run the Server
Start the server.
```bash
python main.py
```

### 4. Testing the Gateway
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

### 5. Auto-ID Generation Test
If you don't provide an X-Request-ID header, the gateway will generate one for you:
```bash
curl -X POST http://localhost:8080/v1/chat/completions \
-H "Content-Type: application/json" \
-d '{
  "messages": [{"role": "user", "content": "Hi, baby!"}]
}'

```
What to look for: A valid UUID in the "id" field (e.g., 550e8400-e29b-...).






