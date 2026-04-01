from .backend_interface import Backend
import httpx
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RemoteBackend_logger")
class RemoteBackend(Backend):
    """Handles 'modal', 'vllm', and any remote HTTP backends"""
    def __init__(self, url: str, model_name: str = None):
        self.url = url
        self.model_name = model_name

    async def generate(self, chat_req: "ChatRequest", path: str = "/v1/chat/completions") -> str:
        async with httpx.AsyncClient() as client:
            try:
                payload = chat_req.model_dump()
                logger.info(f"Sending request to {self.url}")
                if self.model_name:
                    payload["model"] = self.model_name
                # payload["model"] = self.model_name  # override with vLLM model name
                resp = await client.post(
                            f"{self.url}{path}",
                            json=payload,
                            timeout=120.0,
                        )
                resp.raise_for_status()
                backend_data = resp.json()
                return backend_data["choices"][0]["message"]["content"]
            except Exception as e:
                return f"Backend Error ({self.url}): {str(e)}"