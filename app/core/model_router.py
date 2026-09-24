from langchain_core.language_models.chat_models import BaseChatModel
from langchain_ollama import ChatOllama
from app.config import OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_API_KEY


class ModelRouter:
    """Router abstraction providing LLM instances for agent roles."""

    def __init__(
        self,
        base_url: str = OLLAMA_BASE_URL,
        model_name: str = OLLAMA_MODEL,
        api_key: str = OLLAMA_API_KEY,
    ):
        self.base_url = base_url
        self.model_name = model_name
        self.api_key = api_key
        self._models: dict[str, BaseChatModel] = {}

    def get_model(self, role: str, temperature: float = 0.0) -> BaseChatModel:
        """Returns a configured chat model for the requested agent role.
        
        All roles default to the configured Ollama model (gpt-oss:120b).
        Caching the instance per role ensures clean separation and flexibility.
        """
        cache_key = f"{role}_{temperature}"
        if cache_key in self._models:
            return self._models[cache_key]

        client_kwargs = {}
        if self.api_key:
            client_kwargs["headers"] = {"Authorization": f"Bearer {self.api_key}"}

        model = ChatOllama(
            base_url=self.base_url,
            model=self.model_name,
            temperature=temperature,
            client_kwargs=client_kwargs if client_kwargs else None,
        )
        self._models[cache_key] = model
        return model
