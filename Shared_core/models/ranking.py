#  RankingSchema

from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum


class RankingStrategy(str, Enum):
    WEIGHTED = "weighted"                # Combined scoring: semantic + authority
    SEMANTIC_ONLY = "semantic_only"      # Match relevance to query only
    AUTHORITY_ONLY = "authority_only"    # Trust/domain ranking only
    CONSENSUS = "consensus"              # Multiple sources agreement


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