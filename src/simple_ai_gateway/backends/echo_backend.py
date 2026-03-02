from .backend_interface import Backend
class EchoBackend(Backend):
    """Handles 'local' type - using your existing echo logic"""
    async def generate(self, chat_req: "ChatRequest") -> str:
        user_prompt = ""
        for msg in reversed(chat_req.messages):
            if msg.role == "user":
                user_prompt = msg.content
                break
        return f"Echo: {user_prompt}"