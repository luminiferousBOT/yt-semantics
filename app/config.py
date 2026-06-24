from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./yt_semantics.db"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "video_chunks_local"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"
    youtube_api_key: str | None = None
    embedding_dimensions: int = 384


settings = Settings()
