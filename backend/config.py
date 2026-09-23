"""Application configuration and the dataset's fixed evaluation date."""

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DATE = date(2026, 10, 1)
GRADE_ORDER = ("Junior", "Middle", "Senior", "Lead")


def default_data_dir() -> Path:
    """Use provided starter files when present, otherwise labeled demo fixtures."""
    real_data = PROJECT_ROOT / "data"
    return real_data if real_data.exists() else PROJECT_ROOT / "sample_data"


@dataclass(frozen=True)
class Settings:
    """Explicit settings also allow isolated tests without reading local secrets."""

    data_dir: Path = field(default_factory=default_data_dir)
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    llm_api_key: str = field(default="", repr=False)
    llm_base_url: str = "https://integrate.api.nvidia.com/v1/"
    llm_model: str = "meta/llama-3.1-8b-instruct"
    llm_timeout_seconds: float = 6.0

    def __post_init__(self) -> None:
        if not 0 < self.llm_timeout_seconds <= 6:
            raise ValueError("LLM_TIMEOUT_SECONDS must be greater than 0 and at most 6.")
        url = urlparse(self.llm_base_url)
        if url.scheme not in {"http", "https"} or not url.netloc:
            raise ValueError("LLM_BASE_URL must be an absolute HTTP(S) URL.")
        if not self.llm_model.strip():
            raise ValueError("LLM_MODEL must not be empty.")

    @classmethod
    def from_env(cls) -> "Settings":
        """Read project .env without overriding existing environment variables."""
        load_dotenv(PROJECT_ROOT / ".env", override=False)
        data_value = os.getenv("DATA_DIR", "").strip()
        data_path = Path(data_value) if data_value else default_data_dir()
        if not data_path.is_absolute():
            data_path = PROJECT_ROOT / data_path
        origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
        return cls(
            data_dir=data_path,
            cors_origins=tuple(origin.strip() for origin in origins.split(",") if origin.strip()),
            llm_api_key=(os.getenv("LLM_API_KEY") or os.getenv("NVIDIA_API_KEY") or "").strip(),
            llm_base_url=os.getenv("LLM_BASE_URL", cls.llm_base_url).rstrip("/") + "/",
            llm_model=os.getenv("LLM_MODEL", cls.llm_model),
            llm_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "6")),
        )
