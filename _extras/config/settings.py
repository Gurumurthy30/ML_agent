import os
from pathlib import Path
from typing import Optional
import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Ensure environment variables from .env are loaded whenever settings are accessed
load_dotenv()


class ProviderConfig(BaseModel):
    server_url: str = "https://integrate.api.nvidia.com/v1"
    name: str = "deepseek-ai/deepseek-v4-flash-0731"
    api_key_env: str = "NVIDIA_API_KEY"


class ModelConfig(BaseModel):
    server_url: str = "https://integrate.api.nvidia.com/v1"
    name: str = "deepseek-ai/deepseek-v4-flash-0731"
    api_key_env: str = Field(
        default="NVIDIA_API_KEY",
        description=(
            "Name of the environment variable holding the API key for model.server_url. "
            "Common values: NVIDIA_API_KEY (NVIDIA NIM), GROQ_API_KEY (Groq), GOOGLE_API_KEY (Google)."
        ),
    )

    # Role-based provider routing
    # selector + planner_deep → deep_thinking_provider (NVIDIA NIM / DeepSeek V4)
    # coder + planner_default → primary_provider (Groq), failover → fallback_provider (Google)
    deep_thinking_provider: ProviderConfig = Field(
        default_factory=lambda: ProviderConfig(
            server_url="https://integrate.api.nvidia.com/v1",
            name="deepseek-ai/deepseek-v4-flash-0731",
            api_key_env="NVIDIA_API_KEY"
        )
    )
    primary_provider: ProviderConfig = Field(
        default_factory=lambda: ProviderConfig(
            server_url="https://api.groq.com/openai/v1",
            name="llama-3.3-70b-versatile",
            api_key_env="GROQ_API_KEY"
        )
    )
    fallback_provider: ProviderConfig = Field(
        default_factory=lambda: ProviderConfig(
            server_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            name="gemini-3.1-flash-lite",
            api_key_env="GOOGLE_API_KEY"
        )
    )


class BudgetConfig(BaseModel):
    actions_total: int = 100
    time_total_minutes: float = 60.0


class SelectorConfig(BaseModel):
    plateau_n_rounds: int = 3
    plateau_epsilon_relative: float = 0.005  # 0.5% relative improvement threshold


class RAGConfig(BaseModel):
    library_docs_path: str = "rag/library_docs_index"
    technique_cheatsheet_path: str = "rag/technique_cheatsheet_index"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    source_docs_path: str = ""

    def validate_source_docs(self) -> None:
        if not self.source_docs_path or not self.source_docs_path.strip():
            raise ValueError(
                "[CONFIG ERROR] 'source_docs_path' is not configured in settings.yaml.\n"
                "Please set rag.source_docs_path to a local directory containing source documentation before running rag/build_index.py."
            )
        if not os.path.exists(self.source_docs_path):
            raise ValueError(
                f"[CONFIG ERROR] Source docs path does not exist: '{self.source_docs_path}'"
            )


class SessionsConfig(BaseModel):
    storage_path: str = "state/sessions/"
    checkpointer: str = "memory"  # "memory" | "sqlite" | "postgres"
    exec_timeout_seconds: int = 300
    upload_staging_path: str = "state/upload_staging/"


class Settings(BaseModel):
    model: ModelConfig = Field(default_factory=ModelConfig)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    selector: SelectorConfig = Field(default_factory=SelectorConfig)
    rag: RAGConfig = Field(default_factory=RAGConfig)
    sessions: SessionsConfig = Field(default_factory=SessionsConfig)

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "Settings":
        if config_path is None:
            config_path = str(Path(__file__).parent / "settings.yaml")

        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"[CONFIG ERROR] Config file not found at: {config_path}")

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        # Drop legacy keys that may still exist in old settings files
        data.get("model", {}).pop("local_model_path", None)
        data.get("model", {}).pop("ctx_size", None)
        data.get("model", {}).pop("n_gpu_layers", None)
        data.pop("dataset", None)

        settings = cls(**data)
        return settings


def get_settings(config_path: Optional[str] = None) -> Settings:
    return Settings.load(config_path)