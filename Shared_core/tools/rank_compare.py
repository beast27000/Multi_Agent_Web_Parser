#RankCompareTool

# Shared_core/tools/rank_compare.py

from typing import List, Dict, Optional, Tuple
from datetime import datetime
from ..models.chunk import ChunkSchema
from ..models.ranking import RankingResultSchema, RankingStrategy
from ..utils.token_counter import TokenCounter
from ..config.constants import DOMAIN_AUTHORITY
from ..logger.structured_logger import StructuredLogger
from difflib import SequenceMatcher


class RankCompareTool:
    """Rank, score, and compare chunks for ranking and synthesis."""
    
    def __init__(self):
        """Initialize ranker with token counter and logger."""
        self.token_counter = TokenCounter()
        self.logger = StructuredLogger()
    
    def score_chunk(
        self,
        chunk: ChunkSchema,
        query: Optional[str] = None,
        strategy: RankingStrategy = RankingStrategy.WEIGHTED,
    ) -> float:
        """
        Score a single chunk using multiple criteria.
        
        Args:
            chunk: Chunk to score
            query: Optional query for BM25 scoring
            strategy: Scoring strategy (WEIGHTED, SEMANTIC_ONLY, AUTHORITY_ONLY)
        
        Returns:
            Score (0-1)
        """
        scores = {}
        
        # 1. Semantic score (from metadata)
        semantic_score = chunk.metadata.get('similarity_score', 0.7) if chunk.metadata else 0.7
        scores['semantic'] = semantic_score
        
        # 2. Authority score (domain authority)
        domain = chunk.metadata.get('domain', 'unknown') if chunk.metadata else 'unknown'
        authority_rank = DOMAIN_AUTHORITY.get(domain, 100)
        authority_score = 1.0 / (1.0 + authority_rank / 10.0)  # Inverse rank → score
        scores['authority'] = authority_score
        
        # 3. BM25 score (keyword match to query)
        if query:
            query_terms = set(query.lower().split())
            chunk_terms = set(chunk.content.lower().split())
            overlap = len(query_terms & chunk_terms)
            bm25_score = overlap / (len(query_terms) + 1)
            scores['bm25'] = bm25_score
        else:
            scores['bm25'] = 0.5
        
        # 4. Freshness score (recency)
        if chunk.extracted_at:
            try:
                extract_dt = datetime.fromisoformat(chunk.extracted_at)
                days_old = (datetime.utcnow() - extract_dt).days
                freshness_score = 1.0 / (1.0 + days_old / 7.0)  # Decay over weeks
            except:
                freshness_score = 0.5
        else:
            freshness_score = 0.5
        scores['freshness'] = freshness_score
        
        # 5. Length score (prefer medium-length chunks, avoid tiny/huge)
        token_count = len(chunk.content.split())
        optimal_tokens = 500  # Sweet spot
        length_score = 1.0 - abs(token_count - optimal_tokens) / (optimal_tokens * 2)
        length_score = max(0, min(1, length_score))
        scores['length'] = length_score
        
        # Combine scores based on strategy
        if strategy == RankingStrategy.WEIGHTED:
            # Weighted average: semantic 40%, authority 25%, bm25 20%, freshness 10%, length 5%
            final_score = (
                0.40 * scores['semantic'] +
                0.25 * scores['authority'] +
                0.20 * scores['bm25'] +
                0.10 * scores['freshness'] +
                0.05 * scores['length']
            )
        elif strategy == RankingStrategy.SEMANTIC_ONLY:
            final_score = scores['semantic']
        elif strategy == RankingStrategy.AUTHORITY_ONLY:
            final_score = scores['authority']
        else:
            final_score = scores['semantic']
        
        return min(1.0, max(0.0, final_score))
    
    def rank_chunks(
        self,
        chunks: List[ChunkSchema],
        query: Optional[str] = None,
        strategy: RankingStrategy = RankingStrategy.WEIGHTED,
    ) -> List[Tuple[ChunkSchema, float]]:
        """
        Rank chunks by relevance.
        
        Args:
            chunks: List of chunks to rank
            query: Optional query for BM25 component
            strategy: Ranking strategy
        
        Returns:
            List of (chunk, score) tuples, sorted by score (highest first)
        """
        rank_start = datetime.utcnow()
        scored = []
        
        for chunk in chunks:
            score = self.score_chunk(chunk, query, strategy)
            scored.append((chunk, score))
        
        # Sort by score descending
        ranked = sorted(scored, key=lambda x: x[1], reverse=True)
        
        rank_ms = (datetime.utcnow() - rank_start).total_seconds() * 1000
        
        self.logger.log_metric(
            component='rank_compare',
            event='rank_chunks',
            wall_time_ms=rank_ms,
            tokens_used=len(chunks),
            metadata={
                'chunks': len(chunks),
                'strategy': strategy.value,
                'query': query[:50] if query else None,
            }
        )
        
        return ranked
    
    def similarity_score(
        self,
        chunk_a: ChunkSchema,
        chunk_b: ChunkSchema,
    ) -> float:
        """
        Calculate semantic similarity between two chunks (0-1).
        
        Args:
            chunk_a: First chunk
            chunk_b: Second chunk
        
        Returns:
            Similarity score
        """
        # Simple ratio: how much text overlap
        ratio = SequenceMatcher(None, chunk_a.content, chunk_b.content).ratio()
        return ratio
    
    def deduplicate_chunks(
        self,
        chunks: List[ChunkSchema],
        threshold: float = 0.85,
    ) -> List[ChunkSchema]:
        """
        Remove highly similar (duplicate) chunks.
        
        Args:
            chunks: List of chunks
            threshold: Similarity threshold for keeping both (default 0.85 = 85%)
        
        Returns:
            De-duplicated list
        """
        dedup_start = datetime.utcnow()
        
        if len(chunks) <= 1:
            return chunks
        
        unique = []
        
        for chunk in chunks:
            is_duplicate = False
            for unique_chunk in unique:
                sim = self.similarity_score(chunk, unique_chunk)
                if sim >= threshold:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                unique.append(chunk)
        
        dedup_ms = (datetime.utcnow() - dedup_start).total_seconds() * 1000
        removed = len(chunks) - len(unique)
        
        self.logger.log_metric(
            component='rank_compare',
            event='deduplicate',
            wall_time_ms=dedup_ms,
            tokens_used=sum(len(c.content.split()) for c in chunks),
            metadata={
                'input_chunks': len(chunks),
                'output_chunks': len(unique),
                'removed': removed,
                'threshold': threshold,
            }
        )
        
        return unique
    
    def create_ranking_result(
        self,
        chunks: List[ChunkSchema],
        query: Optional[str] = None,
        strategy: RankingStrategy = RankingStrategy.WEIGHTED,
    ) -> RankingResultSchema:
        """
        Create a RankingResultSchema from ranked chunks.
        
        Args:
            chunks: List of chunks to rank
            query: Optional query context
            strategy: Ranking strategy
        
        Returns:
            RankingResultSchema with ranked chunks
        """
        ranked_pairs = self.rank_chunks(chunks, query, strategy)
        
        ranked_chunks = [
            {
                'chunk': chunk,
                'score': score,
                'rank': i + 1,
            }
            for i, (chunk, score) in enumerate(ranked_pairs)
        ]
        
        return RankingResultSchema(
            query=query or '',
            input_chunks=len(chunks),
            ranked_chunks=ranked_chunks,
            strategy=strategy,
            created_at=datetime.utcnow().isoformat(),
        )
    
    def compare_chunks(
        self,
        chunk_a: ChunkSchema,
        chunk_b: ChunkSchema,
    ) -> Dict[str, any]:
        """
        Compare two chunks side-by-side.
        
        Args:
            chunk_a: First chunk
            chunk_b: Second chunk
        
        Returns:
            Comparison dict with similarity, differences, metadata
        """
        similarity = self.similarity_score(chunk_a, chunk_b)
        
        # Extract domains
        domain_a = chunk_a.metadata.get('domain', 'unknown') if chunk_a.metadata else 'unknown'
        domain_b = chunk_b.metadata.get('domain', 'unknown') if chunk_b.metadata else 'unknown'
        
        # Token counts
        tokens_a = self.token_counter.count_tokens(chunk_a.content)
        tokens_b = self.token_counter.count_tokens(chunk_b.content)
        
        comparison = {
            'similarity_score': similarity,
            'are_duplicates': similarity >= 0.85,
            'chunk_a': {
                'url': chunk_a.url,
                'domain': domain_a,
                'label': chunk_a.label.value if chunk_a.label else 'unknown',
                'tokens': tokens_a,
                'title': chunk_a.title,
            },
            'chunk_b': {
                'url': chunk_b.url,
                'domain': domain_b,
                'label': chunk_b.label.value if chunk_b.label else 'unknown',
                'tokens': tokens_b,
                'title': chunk_b.title,
            },
            'compared_at': datetime.utcnow().isoformat(),
        }
        
        self.logger.log_metric(
            component='rank_compare',
            event='compare_chunks',
            wall_time_ms=0,
            tokens_used=tokens_a + tokens_b,
            metadata={
                'similarity': similarity,
                'domain_a': domain_a,
                'domain_b': domain_b,
            }
        )
        
        return comparison
    
    def merge_chunks(
        self,
        chunks: List[ChunkSchema],
        separator: str = '\n\n---\n\n',
    ) -> ChunkSchema:
        """
        Merge multiple chunks into one (for synthesis).
        
        Args:
            chunks: List of chunks to merge
            separator: Separator string between chunks
        
        Returns:
            New merged chunk
        """
        if not chunks:
            return ChunkSchema(
                url='merged',
                label=None,
                content='',
                source_id='merged',
            )
        
        # Combine content
        combined_content = separator.join(c.content for c in chunks)
        
        # Use first chunk's metadata as base
        first = chunks[0]
        urls = [c.url for c in chunks]
        
        merged = ChunkSchema(
            url='|'.join(urls),  # Pipe-separated URLs
            label=first.label,
            content=combined_content,
            title=first.title + ' [merged]',
            source_id=first.source_id,
            extracted_at=datetime.utcnow().isoformat(),
            metadata={
                'merged_from': len(chunks),
                'source_urls': urls,
                'source_domains': list(set(
                    c.metadata.get('domain', 'unknown') for c in chunks if c.metadata
                )),
            }
        )
        
        self.logger.log_metric(
            component='rank_compare',
            event='merge_chunks',
            wall_time_ms=0,
            tokens_used=len(combined_content.split()),
            metadata={'merged_from': len(chunks)}
        )
        
        return merged
    
    async def get_ranker_stats(self) -> Dict[str, any]:
        """Get ranking statistics."""
        return {
            'queried_at': datetime.utcnow().isoformat(),
        }


# Singleton getter for easy import
_ranker_instance = None

async def get_rank_compare_tool() -> RankCompareTool:
    """Get or create the global rank/compare tool singleton."""
    global _ranker_instance
    if _ranker_instance is None:
        _ranker_instance = RankCompareTool()
    return _ranker_instance