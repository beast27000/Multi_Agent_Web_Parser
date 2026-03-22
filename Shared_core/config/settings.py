# Pydantic BaseSettings


"""
What It Does
After creating models (step 1), we need a central place to load settings. This file reads from YAML + environment variables.

All agents will use this to get:

Model path (where is Qwen-3-4B-VL?)
Redis connection (host, port, TTL)
Chroma path (where to store vectors?)
Timeouts (how long to wait for Playwright?)
Token limits (8k, 1800 chunks)
"""

from pydantic_settings import BaseSettings
from typing import Optional
from pathlib import Path


class Settings(BaseSettings):
    """Central config for all agents. Loads from YAML + env vars."""
    
    # Model config
    model_name: str = "Qwen2-VL-4B-Instruct"
    model_path: str = "./models/qwen-vl"
    max_tokens_per_call: int = 8000          # Hard constraint
    
    # Chunking config
    max_chunk_size: int = 1800               # Hard constraint
    chunk_overlap: int = 200                 # For context continuity
    
    # Search config
    max_parallel_fetches: int = 6            # Max concurrent requests
    fetch_timeout_seconds: int = 30          # How long to wait
    
    # Redis config
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    cache_ttl_minutes: int = 45              # Cache expiry
    
    # Chroma config
    chroma_path: str = "./data/chroma"       # Vector DB location
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    
    # Logging config
    log_level: str = "INFO"
    log_dir: str = "./logs"
    
    class Config:
        env_file = ".env"                    # Load from .env file
        env_file_encoding = "utf-8"


# Singleton instance (use throughout app)
settings = Settings()