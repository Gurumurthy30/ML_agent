import os
from pathlib import Path
from typing import Optional
import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


class ModelConfig(BaseModel):
    server_url: str = "http://localhost:8000/v1"
    local_model_path: str = Field(default="", description="Path to local GGUF weights")
    ctx_size: int = 8192
    n_gpu_layers: int = 999

    def validate_local_path(self, require_exists: bool = True) -> None:
        """Validates that local_model_path is set and points to an existing file."""
        if not self.local_model_path or not self.local_model_path.strip():
            raise ValueError(
                "[CONFIG ERROR] 'local_model_path' is not configured in settings.yaml or environment.\n"
                "Please set model.local_model_path in config/settings.yaml to point to your local GGUF file.\n"
                "Note: Automatic model downloads (Hugging Face / Git LFS) are strictly disabled."
            )
        if require_exists and not os.path.exists(self.local_model_path):
            raise ValueError(
                f"[CONFIG ERROR] Local model path does not exist: '{self.local_model_path}'\n"
                "Please verify the file exists on disk and update settings.yaml accordingly."
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
    embedding_model: str = "BAAI/bge-m3"
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


class MLEDojoConfig(BaseModel):
    use_mock: bool = True


class Settings(BaseModel):
    model: ModelConfig = Field(default_factory=ModelConfig)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    selector: SelectorConfig = Field(default_factory=SelectorConfig)
    rag: RAGConfig = Field(default_factory=RAGConfig)
    mle_dojo: MLEDojoConfig = Field(default_factory=MLEDojoConfig)

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "Settings":
        if config_path is None:
            config_path = str(Path(__file__).parent / "settings.yaml")
        
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"[CONFIG ERROR] Config file not found at: {config_path}")
        
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            
        settings = cls(**data)
        return settings


# Global settings loader instance
def get_settings(config_path: Optional[str] = None) -> Settings:
    return Settings.load(config_path)
