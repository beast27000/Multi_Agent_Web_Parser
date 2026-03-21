Before we write code, you need to understand why models come first:

Models (schemas)      ← You ARE HERE
   ↓
Config (settings load from YAML)
   ↓
Logger (tracks metrics)
   ↓
Everything else relies on these 3

Why models first?

They define the "shape" of your data (like a blueprint)
Every other part of the code will use these shapes
If models are broken, everything breaks
File 1: intent.py
What does this file do?
Your app receives queries like:

"Compare laptop prices at Amazon vs Newegg"
"What's the latest news on AI safety?"
"Show me reviews for the iPhone 15"
The IntentExtractor agent needs to understand which query type it is. That's what this schema does.

Key Concept: Pydantic
We use Pydantic (a Python library) because it:

Validates - ensures data matches the expected shape
Type-checks - catches errors early
Parses JSON - converts strings to Python objects automatically
The Code Structure


from enum import Enum
from pydantic import BaseModel, Field
from typing import List, Optional

# Step 1: Define query types (enum = list of allowed values)
class QueryType(str, Enum):
    PRODUCT_COMPARE = "product_compare"      # "Compare X vs Y"
    NEWS_SEARCH = "news_search"              # "Latest news on X"
    PRICE_TRACKING = "price_tracking"        # "Track price of X"
    POLICY_RESEARCH = "policy_research"      # "Explain policy X"
    FACT_CHECK = "fact_check"                # "Is X true?"


# Step 2: Define what an intent looks like
class IntentSchema(BaseModel):
    """Schema for parsed user query intent."""
    
    query_type: QueryType                    # Must be one of the 5 types
    main_entity: str                         # What are they asking about?
    secondary_entities: List[str] = []       # Optional secondary items (e.g., "compare A vs B")
    temporal_scope: Optional[str] = None     # "latest", "this year", etc.
    sites_to_search: List[str] = []          # Optional: which sites to prioritize
    confidence_score: float = Field(ge=0.0, le=1.0)  # 0-1 score (validated)

    class Config:
        json_schema_extra = {
            "example": {
                "query_type": "product_compare",
                "main_entity": "laptop",
                "secondary_entities": ["Dell XPS", "MacBook Pro"],
                "temporal_scope": "2026",
                "sites_to_search": ["amazon.com", "bestbuy.com"],
                "confidence_score": 0.95
            }
        }

What's Happening Here?
Line	What It Does
from enum import Enum	Imports the Enum class (allows fixed list of choices)
QueryType(str, Enum)	Creates 5 allowed query types. Can only be one of these.
BaseModel	Pydantic base - validates all fields automatically
Field(ge=0.0, le=1.0)	ge = greater-than-or-equal, le = less. So 0.0 to 1.0 only.
= []	Default value = empty list
Optional[str]	This field can be a string OR None (null)
Config class	Metadata, example data, display rules
Example: How It Validates


# This WORKS:
intent = IntentSchema(
    query_type="product_compare",
    main_entity="laptop",
    secondary_entities=["Dell", "HP"],
    confidence_score=0.85
)

# This FAILS (confidence_score > 1.0):
intent = IntentSchema(
    query_type="product_compare",
    main_entity="laptop",
    confidence_score=1.5  # ERROR! Must be 0-1
)

# This FAILS (invalid query_type):
intent = IntentSchema(
    query_type="random_type",  # ERROR! Must be one of the 5
    main_entity="laptop",
    confidence_score=0.85
)


### File 2: chunk.py

How This Relates to intent.py
Think of it this way:

User Query: "Compare laptop prices"
        ↓
IntentSchema (intent.py)  ← What are they asking?
        ↓
ETL fetches websites → BeautifulSoup parsing → extracts data
        ↓
ChunkSchema (chunk.py)  ← What data got extracted?

IntentSchema = Input (user's question)
ChunkSchema = Output (data from websites)

What chunk.py Does
After fetching a website, we break it into chunks (small pieces). Each chunk gets:

The actual text content
A label (price, review, fact, policy, etc.)
Metadata (source URL, timestamp, confidence)
Why labels? So agents can quickly find relevant chunks. Example:

Chunk 1: "$999 for Dell XPS 13"      → LABEL: "price"
Chunk 2: "5 stars, great keyboard"   → LABEL: "review"
Chunk 3: "Ships to 50 countries"     → LABEL: "policy"

The Code

from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# Label types for categorizing chunks
class ChunkLabel(str, Enum):
    PRICE = "price"                    # "Cost is $X"
    REVIEW = "review"                  # "5 stars, great..."
    SPECIFICATION = "specification"    # "Intel i7, 16GB RAM"
    COMPARISON = "comparison"          # "vs competitor X"
    POLICY = "policy"                  # "Ships to X countries"
    FACT = "fact"                      # "True/false claim"
    NEWS = "news"                      # "Latest development"
    OTHER = "other"                    # Unclassified


# Represents one chunk of extracted content
class ChunkSchema(BaseModel):
    """Schema for extracted web page chunks."""
    
    chunk_id: str                              # Unique ID
    content: str = Field(min_length=10)        # Text (minimum 10 chars)
    label: ChunkLabel                          # What type of info?
    source_url: str                            # Where it came from
    confidence_score: float = Field(ge=0.0, le=1.0)  # How confident we are (0-1)
    timestamp: datetime = Field(default_factory=datetime.utcnow)  # When extracted
    token_count: Optional[int] = None          # Optional: how many tokens?
    parent_intent_id: Optional[str] = None     # Links back to which user query?
    
    class Config:
        json_schema_extra = {
            "example": {
                "chunk_id": "chunk_001",
                "content": "Dell XPS 13 is priced at $1,099 with Intel i7 processor",
                "label": "price",
                "source_url": "https://amazon.com/dell-xps",
                "confidence_score": 0.92,
                "timestamp": "2026-03-22T10:30:00",
                "token_count": 18,
                "parent_intent_id": "intent_abc123"
            }
        }

Key Concepts Here

Concept	What It Does
ChunkLabel Enum	8 allowed categories (price, review, spec, etc.)
min_length=10	Content must be at least 10 characters (no junk)
default_factory=datetime.utcnow	Auto-fills timestamp when chunk created
parent_intent_id	Tracks which user query this chunk came from
token_count	Optional field (might not always have this)

How It Works Together (examples)

Concept	What It Does
ChunkLabel Enum	8 allowed categories (price, review, spec, etc.)
min_length=10	Content must be at least 10 characters (no junk)
default_factory=datetime.utcnow	Auto-fills timestamp when chunk created
parent_intent_id	Tracks which user query this chunk came from
token_count	Optional field (might not always have this)

### File 3: search_plan.py

What This Does
After the IntentExtractor understands the user's query, the SearchPlanner agent decides:

Which websites to search
What URL patterns to try
Which fallback APIs to use
This schema captures that plan.

The Code

from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum


class FallbackAPIType(str, Enum):
    GOOGLE = "google"
    DUCKDUCKGO = "duckduckgo"
    BING = "bing"
    SCRAPERAPI = "scraperapi"
    NONE = "none"


class SearchTarget(BaseModel):
    """One website to search."""
    
    url: str                                    # Base URL (e.g., amazon.com)
    priority: int = Field(ge=1, le=10)         # 1=most important, 10=least
    search_query: str                           # What to search for on this site
    fallback_api: FallbackAPIType = FallbackAPIType.NONE  # If stealth fails, use this


class SearchPlanSchema(BaseModel):
    """Schema for search strategy."""
    
    plan_id: str                                # Unique ID for tracking
    intent_id: str                              # Links back to user intent
    targets: List[SearchTarget]                 # List of sites to search
    max_parallel_fetches: int = Field(ge=1, le=6)  # How many simultaneous requests
    timeout_seconds: int = Field(ge=5, le=60)  # Max wait time per fetch
    use_stealth: bool = True                    # Use Playwright stealth mode?
    description: Optional[str] = None           # Human-readable plan summary
    
    class Config:
        json_schema_extra = {
            "example": {
                "plan_id": "plan_xyz789",
                "intent_id": "intent_abc123",
                "targets": [
                    {
                        "url": "amazon.com",
                        "priority": 1,
                        "search_query": "Dell XPS 13 price",
                        "fallback_api": "duckduckgo"
                    },
                    {
                        "url": "bestbuy.com",
                        "priority": 2,
                        "search_query": "Dell XPS 13",
                        "fallback_api": "scraperapi"
                    }
                ],
                "max_parallel_fetches": 4,
                "timeout_seconds": 30,
                "use_stealth": True,
                "description": "Fetch laptop prices from 2 major retailers"
            }
        }

Key Concepts
Part	Meaning
priority: 1-10	1 = most trust/importance. Search this first if limited time.
max_parallel_fetches: 1-6	Don't overload servers. Max 6 at once.
timeout_seconds: 5-60	Give up if fetch takes too long. Prevents hanging.
use_stealth: True/False	Use Playwright tricks to avoid bot detection?
fallback_api	If stealth fetch fails, try this API instead (Google, DuckDuckGo, etc.)
targets: List[SearchTarget]	Array of websites (can be 1 to N sites)

How It Connects

IntentSchema (what user asked)
        ↓
SearchPlanSchema (HOW to search for it)
        ↓
Agent fetches using this plan
        ↓
ChunkSchema (RESULTS from fetching)

Flow in words:

User: "Compare laptop prices"
IntentExtractor creates IntentSchema
SearchPlanner creates SearchPlanSchema with targets=[amazon.com, bestbuy.com]
MultiSiteFetcher uses SearchPlanSchema to fetch websites
ChunkProcessor converts HTML → ChunkSchema objects

### File 4: ranking.py

After fetching and chunking data from multiple websites, the CrossSiteRanker agent needs to:

Compare chunks across sites
Score relevance/quality
Return ranked results
This schema captures the ranked output.

The Code

from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum


class RankingStrategy(str, Enum):
    RELEVANCE = "relevance"              # How well does it match query?
    RECENCY = "recency"                  # How fresh is the info?
    SOURCE_AUTHORITY = "source_authority"  # How trustworthy is the site?
    CONSENSUS = "consensus"              # Do multiple sites agree?


class RankedChunk(BaseModel):
    """One chunk with its ranking score."""
    
    chunk_id: str
    content: str = Field(max_length=2000)       # Actual text
    source_url: str
    label: str                                   # price, review, etc.
    original_confidence: float = Field(ge=0.0, le=1.0)  # From extractor
    ranking_score: float = Field(ge=0.0, le=1.0)       # After comparison
    rank_position: int = Field(ge=1)            # 1 = best
    reasoning: Optional[str] = None             # Why ranked here?


class RankingResultSchema(BaseModel):
    """Final ranked results for a query."""
    
    ranking_id: str                             # Unique ID
    intent_id: str                              # Which query?
    strategy: RankingStrategy                   # How did we rank?
    ranked_chunks: List[RankedChunk]           # Sorted best-to-worst
    total_chunks_evaluated: int                 # How many did we see?
    final_confidence: float = Field(ge=0.0, le=1.0)  # Overall quality
    
    class Config:
        json_schema_extra = {
            "example": {
                "ranking_id": "rank_abc789",
                "intent_id": "intent_xyz123",
                "strategy": "relevance",
                "ranked_chunks": [
                    {
                        "chunk_id": "chunk_001",
                        "content": "Dell XPS 13 costs $1,099 (official price)",
                        "source_url": "amazon.com",
                        "label": "price",
                        "original_confidence": 0.90,
                        "ranking_score": 0.95,
                        "rank_position": 1,
                        "reasoning": "Official source + matches label"
                    },
                    {
                        "chunk_id": "chunk_002",
                        "content": "Best laptop for developers (5 stars)",
                        "source_url": "techreview.com",
                        "label": "review",
                        "original_confidence": 0.85,
                        "ranking_score": 0.88,
                        "rank_position": 2,
                        "reasoning": "Trusted reviewer, high confidence"
                    }
                ],
                "total_chunks_evaluated": 15,
                "final_confidence": 0.92
            }
        }

Key Concepts
Part	Meaning
RankingStrategy Enum	The algorithm used (relevance, recency, authority, consensus)
ranking_score	0-1 score AFTER comparing across sites. Not the same as original_confidence
rank_position: 1	Best result. Position 2, 3, etc. are lower quality.
reasoning	Optional: explanation for humans (e.g., "Amazon is official source")
total_chunks_evaluated	Did we evaluate 5 chunks or 50?
final_confidence	Overall quality of the entire result set


How All 4 Models Connect

IntentSchema        ← What user asked ("Compare laptops")
         ↓
SearchPlanSchema    ← Where/how to search (amazon.com, bestbuy.com)
         ↓
ChunkSchema         ← Raw extracted data ("$999", "5 stars", etc.)
         ↓
RankingResultSchema ← Final ranked answer ("Best: $999 from Amazon")

This is the flow of data through the entire system.

