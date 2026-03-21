# For SearchPlanSchema

"""
After the IntentExtractor understands the user's query, the SearchPlanner agent decides:

Which websites to search
What URL patterns to try
Which fallback APIs to use
This schema captures that plan.
"""

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