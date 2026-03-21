# For chunk.py

"""
What chunk.py Does
After fetching a website, we break it into chunks (small pieces). Each chunk gets:

The actual text content
A label (price, review, fact, policy, etc.)
Metadata (source URL, timestamp, confidence)
Why labels? So agents can quickly find relevant chunks. Example:
"""

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