#  Global constants

"""
What It Does
While settings.py loads from YAML/env (changeable), this file contains hardcoded global constants (things that should NEVER change during runtime).

Examples:

Hard constraint: max 8k tokens per call
Hard constraint: max 1800 tokens per chunk
Domain authority scores (trusted sites)
Fallback API URLs
Query type descriptions
"""

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