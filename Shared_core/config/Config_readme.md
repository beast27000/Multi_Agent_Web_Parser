File 1: settings.py
What It Does
After creating models (step 1), we need a central place to load settings. This file reads from YAML + environment variables.

All agents will use this to get:

Model path (where is Qwen-3-4B-VL?)
Redis connection (host, port, TTL)
Chroma path (where to store vectors?)
Timeouts (how long to wait for Playwright?)
Token limits (8k, 1800 chunks)

The Code
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

Key Concepts
Concept	Meaning
BaseSettings	Pydantic class that reads from .env files + environment
env_file = ".env"	Automatically reads .env file (if exists)
Default values	Settings have defaults (can override via .env)
Singleton	settings = Settings() — one instance for whole app

How It Works
Example: Using later in code

from Shared_core.config.settings import settings

# Access any setting
print(settings.max_tokens_per_call)    # 8000
print(settings.redis_host)              # "localhost"
print(settings.model_path)              # "./models/qwen-vl"

Example: Override via .env

Connections
From Models: Uses IntentSchema, ChunkSchema (as type hints later)
To Logger: Logger will read settings to know where to write logs
To ETL: ETL reads chunk size from settings
To Tools: Tools read timeouts/limits from settings

### File 2: constants.py

What It Does
While settings.py loads from YAML/env (changeable), this file contains hardcoded global constants (things that should NEVER change during runtime).

Examples:

Hard constraint: max 8k tokens per call
Hard constraint: max 1800 tokens per chunk
Domain authority scores (trusted sites)
Fallback API URLs
Query type descriptions

The Code

"""Global constants - hardcoded project-wide limits & mappings."""

# Hard Constraints (from rules.md - NEVER change during runtime)
MAX_TOKENS_PER_CALL = 8000          # Qwen context limit
MAX_CHUNK_SIZE = 1800                # Keep reasoning context
MAX_CHUNKS_PER_QUERY = 3             # Agent sees 2-3 chunks max

# Parallel execution limits
MAX_PARALLEL_FETCHES = 6             # Don't overload servers
MIN_PARALLEL_FETCHES = 1

# Cache config (static)
REDIS_CACHE_TTL_MINUTES = 45         # Query result expiry
REDIS_RETRY_ATTEMPTS = 3
REDIS_RETRY_DELAY_SECONDS = 1

# Timeouts (seconds)
FETCH_TIMEOUT_MIN = 5
FETCH_TIMEOUT_MAX = 60
FETCH_TIMEOUT_DEFAULT = 30

# Domain authority scoring (0-100, higher = more trusted)
DOMAIN_AUTHORITY = {
    "amazon.com": 95,
    "bestbuy.com": 90,
    "newegg.com": 85,
    "techcrunch.com": 80,
    "wikipedia.org": 75,
    "arxiv.org": 90,
    "github.com": 85,
    "reddit.com": 40,  # Lower authority
}

# Fallback API URLs
FALLBACK_APIS = {
    "google": "https://www.google.com/search",
    "duckduckgo": "https://duckduckgo.com",
    "bing": "https://www.bing.com/search",
}

# Query type descriptions
QUERY_TYPE_DESCRIPTIONS = {
    "product_compare": "Compare prices/specs of products across sites",
    "news_search": "Find latest news on a topic",
    "price_tracking": "Track current price of a product",
    "policy_research": "Research policies or terms",
    "fact_check": "Verify if a claim is true or false",
}

# Chunk label descriptions
CHUNK_LABELS_DESCRIPTIONS = {
    "price": "Cost/pricing information",
    "review": "User reviews or ratings",
    "specification": "Technical specs or features",
    "comparison": "Comparison with competitors",
    "policy": "Rules, terms, or policies",
    "fact": "Factual claims or statements",
    "news": "News or recent updates",
    "other": "Other unclassified content",
}

Key Concepts:

Concept	Purpose	Used By
MAX_TOKENS_PER_CALL	Ensures LLM calls never exceed Qwen's limits	LangGraph agent (message building)
MAX_CHUNK_SIZE	Chunks never exceed this; enforced by ChunkProcessor	ETL pipeline + LLM interface
MAX_PARALLEL_FETCHES	Controls concurrency; prevents system overload	MultiSiteFetcher agent
DOMAIN_AUTHORITY	Scores websites by trustworthiness; used by CrossSiteRanker	Ranking logic (chunk comparison)
FALLBACK_APIS	Search URLs when primary fetch fails	SearchPlanner agent
QUERY_TYPE_DESCRIPTIONS	Human-readable mapping for QueryType enum	Logging + debugging
CHUNK_LABEL_DESCRIPTIONS	Human-readable mapping for ChunkLabel enum	Logging + debugging
How It Connects:

settings.py loads env vars; constants.py stores hardcoded rules
Chunk Processor enforces MAX_CHUNK_SIZE when splitting documents
LangGraph Agent uses MAX_TOKENS_PER_CALL to validate message sizes before calling Qwen
CrossSiteRanker uses DOMAIN_AUTHORITY dict to score chunks by source trustworthiness
Descriptions enums enable easy logging without string literals scattered everywhere

### File 3: config_default.yaml — User Configuration Template

This YAML file is what users copy and customize. It holds all the runtime settings that might change between deployments (local dev vs. production, different Redis servers, different model paths, etc.).

# Shared_core/config/config_default.yaml

# Model Configuration (local Qwen LLM)
model:
  name: "Qwen2-VL-3B-Instruct"  # Local Qwen model identifier
  context_size: 27000           # Max context tokens for Qwen
  max_tokens_per_call: 8000     # Max output tokens per inference call

# Redis Cache (for deduplication + search result caching)
redis:
  host: "localhost"
  port: 6379
  db: 0
  password: null                # Set if Redis requires authentication
  cache_ttl_seconds: 2700       # 45 minutes — chunk cache lifetime

# Chroma Vector Store (semantic search on fetched chunks)
chroma:
  persist_directory: "./chroma_data"  # Where embeddings are stored
  collection_name: "web_chunks"       # Chroma collection for this project

# Logging & Metrics
logging:
  log_dir: "./logs"
  json_log_file: "agent_metrics.jsonl"  # Structured JSON logs
  log_level: "INFO"                     # DEBUG, INFO, WARNING, ERROR

# Request & Fetch Settings
requests:
  timeout_seconds: 30           # HTTP timeout per fetch
  max_retries: 2                # Retry failed fetches this many times
  user_agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"  # Stealth header

# Feature Flags (optional, for A/B testing)
features:
  enable_redis_cache: true
  enable_chroma_vector_search: true
  enable_fallback_search_api: true

  Key Concepts:

Setting	Purpose	Who Uses It
model.name	Identifier for language model executable/path	LangGraph agent (inference calls)
model.max_tokens_per_call	Override for constants.py MAX_TOKENS_PER_CALL	LLM interface (message validation)
redis.host + redis.port	Connection to Redis instance	RedisManager (cache reads/writes)
cache_ttl_seconds	How long chunks stay cached (45 min default)	RedisManager (invalidation logic)
chroma.persist_directory	Where vector embeddings live on disk	ChromaManager (collection initialization)
logging.log_dir	Where to write JSON metrics	StructuredLogger (file I/O)
timeout_seconds	Network timeout for Playwright fetches	MultiSiteFetcher agent
enable_redis_cache	Toggle caching on/off without code changes	ETL pipeline (conditional logic)
How It Connects:

settings.py defines the class structure (which fields exist + types); config_default.yaml provides the actual values
When you run the system, load config_default.yaml → Pydantic parses it → settings object created
Each agent reads from settings (e.g., settings.redis_host) — no hardcoding
Users customize this file per environment without touching Python code
Example use case: Dev uses localhost:6379 for Redis; production uses prod-redis.internal:6379


