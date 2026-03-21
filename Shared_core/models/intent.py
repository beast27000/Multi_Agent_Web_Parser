# For IntentSchema
"""
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
"""


from enum import Enum
from pydantic import BaseModel,Field
from typing import List, Optional

# Step 1: Define query types (enum = list of allowed values)

class QueryType(str, Enum):   # Creates 5 allowed query types. Can only be one of these.
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
    
    class Config:  #This class is for giving the agent an example for how to structure the output
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
    


