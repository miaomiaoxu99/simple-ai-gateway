from abc import ABC, abstractmethod
class Backend(ABC):
    @abstractmethod
    async def generate(self, chat_req: "ChatRequest") -> str:
        pass