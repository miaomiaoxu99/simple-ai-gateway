from .backend_interface import Backend
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