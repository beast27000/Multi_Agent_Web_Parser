#VectorRetrieveTool

"""
The Concept
The Vector Retriever Tool provides easy semantic search utilities for agents. It wraps Chroma's vector search with:

Query→Embedding (automatic)
Cosine similarity search (find top-k most relevant chunks)
Filtering (by label, source domain, date range)
Re-ranking (optional secondary scoring)
Cache management (track frequently retrieved chunks)
Think of it as: "Query → Find similar chunks in vector DB → Return ranked results"
"""

# Shared_core/tools/vector_retrieve.py

from typing import List, Dict, Optional, Any, Set
from datetime import datetime, timedelta
from ..models.chunk import ChunkSchema, ChunkLabel
from ..memory.chroma_manager import ChromaManager
from ..memory.redis_manager import RedisManager
from ..logger.structured_logger import StructuredLogger
from ..config.constants import DOMAIN_AUTHORITY


class VectorRetriever:
    """Semantic search and retrieval from vector database."""
    
    def __init__(self):
        """Initialize retriever with Chroma and cache."""
        self.chroma_mgr = ChromaManager()
        self.redis_mgr = RedisManager()
        self.logger = StructuredLogger()
    
    async def retrieve(
        self,
        query: str,
        top_k: int = 10,
        min_score: float = 0.5,
    ) -> List[ChunkSchema]:
        """
        Semantic search: Find top-k most similar chunks.
        
        Args:
            query: Search query string
            top_k: Number of results to return
            min_score: Minimum cosine similarity (0-1)
        
        Returns:
            List of ChunkSchema, sorted by relevance (highest first)
        """
        retrieve_start = datetime.utcnow()
        
        try:
            # Search Chroma by query embedding
            results = self.chroma_mgr.search(query, top_k=top_k * 2)  # Over-fetch
            
            # Filter by min_score and limit to top_k
            filtered_results = []
            for chunk in results[:top_k * 2]:
                # Extract score from metadata if available
                score = chunk.metadata.get('similarity_score', 1.0) if chunk.metadata else 1.0
                if score >= min_score:
                    filtered_results.append(chunk)
            
            final_results = filtered_results[:top_k]
            
            retrieve_ms = (datetime.utcnow() - retrieve_start).total_seconds() * 1000
            
            self.logger.log_metric(
                component='vector_retriever',
                event='retrieve_success',
                wall_time_ms=retrieve_ms,
                tokens_used=len(query.split()),
                metadata={
                    'query': query,
                    'results': len(final_results),
                    'min_score': min_score,
                }
            )
            
            return final_results
        
        except Exception as e:
            retrieve_ms = (datetime.utcnow() - retrieve_start).total_seconds() * 1000
            self.logger.log_metric(
                component='vector_retriever',
                event='retrieve_error',
                wall_time_ms=retrieve_ms,
                tokens_used=0,
                metadata={'query': query, 'error': str(e)}
            )
            return []
    
    async def retrieve_by_label(
        self,
        label: ChunkLabel,
        top_k: int = 10,
    ) -> List[ChunkSchema]:
        """
        Retrieve chunks by content label (HEADING, PARAGRAPH, etc).
        
        Args:
            label: ChunkLabel enum value
            top_k: Maximum results
        
        Returns:
            List of chunks with matching label
        """
        try:
            results = self.chroma_mgr.search_by_label(label, top_k=top_k)
            
            self.logger.log_metric(
                component='vector_retriever',
                event='retrieve_by_label',
                wall_time_ms=0,
                tokens_used=0,
                metadata={'label': label.value, 'results': len(results)}
            )
            
            return results
        
        except Exception as e:
            self.logger.log_metric(
                component='vector_retriever',
                event='retrieve_by_label_error',
                wall_time_ms=0,
                tokens_used=0,
                metadata={'label': label.value if label else 'unknown', 'error': str(e)}
            )
            return []
    
    async def retrieve_by_domain(
        self,
        query: str,
        domain: str,
        top_k: int = 10,
    ) -> List[ChunkSchema]:
        """
        Semantic search, filtered by source domain.
        
        Args:
            query: Search query
            domain: Domain name (e.g., 'github.com')
            top_k: Results to return
        
        Returns:
            Chunks from specified domain only
        """
        try:
            # Get all results
            all_results = await self.retrieve(query, top_k=top_k * 3)  # Over-fetch
            
            # Filter by domain
            domain_results = []
            for chunk in all_results:
                if chunk.metadata and chunk.metadata.get('domain') == domain:
                    domain_results.append(chunk)
            
            final_results = domain_results[:top_k]
            
            self.logger.log_metric(
                component='vector_retriever',
                event='retrieve_by_domain',
                wall_time_ms=0,
                tokens_used=len(query.split()),
                metadata={'query': query, 'domain': domain, 'results': len(final_results)}
            )
            
            return final_results
        
        except Exception as e:
            self.logger.log_metric(
                component='vector_retriever',
                event='retrieve_by_domain_error',
                wall_time_ms=0,
                tokens_used=0,
                metadata={'query': query, 'domain': domain, 'error': str(e)}
            )
            return []
    
    async def retrieve_by_authority(
        self,
        query: str,
        top_k: int = 10,
        preferred_domains: Optional[Set[str]] = None,
    ) -> List[ChunkSchema]:
        """
        Semantic search, prioritized by domain authority.
        
        Uses DOMAIN_AUTHORITY config to score domains.
        
        Args:
            query: Search query
            top_k: Results to return
            preferred_domains: Override authority with custom list
        
        Returns:
            Chunks sorted by domain authority + relevance
        """
        try:
            # Get all results
            all_results = await self.retrieve(query, top_k=top_k * 3)  # Over-fetch
            
            # Define authority scores
            if preferred_domains:
                authority_map = {d: i for i, d in enumerate(preferred_domains)}
            else:
                authority_map = DOMAIN_AUTHORITY  # From constants
            
            # Sort by authority, then by position
            def authority_score(chunk: ChunkSchema) -> tuple:
                domain = chunk.metadata.get('domain', 'unknown') if chunk.metadata else 'unknown'
                authority = authority_map.get(domain, 1000)  # Unknown domains last
                return (authority, all_results.index(chunk))
            
            sorted_results = sorted(all_results, key=authority_score)
            final_results = sorted_results[:top_k]
            
            self.logger.log_metric(
                component='vector_retriever',
                event='retrieve_by_authority',
                wall_time_ms=0,
                tokens_used=len(query.split()),
                metadata={'query': query, 'results': len(final_results)}
            )
            
            return final_results
        
        except Exception as e:
            self.logger.log_metric(
                component='vector_retriever',
                event='retrieve_by_authority_error',
                wall_time_ms=0,
                tokens_used=0,
                metadata={'query': query, 'error': str(e)}
            )
            return []
    
    async def retrieve_recent(
        self,
        query: str,
        days: int = 7,
        top_k: int = 10,
    ) -> List[ChunkSchema]:
        """
        Semantic search, filtered to recent chunks.
        
        Args:
            query: Search query
            days: Only chunks extracted in last N days
            top_k: Results to return
        
        Returns:
            Recent chunks, ranked by relevance
        """
        try:
            cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
            
            # Get all results
            all_results = await self.retrieve(query, top_k=top_k * 3)  # Over-fetch
            
            # Filter by date
            recent_results = []
            for chunk in all_results:
                extracted_at = chunk.extracted_at if chunk.extracted_at else ''
                if extracted_at >= cutoff_date:
                    recent_results.append(chunk)
            
            final_results = recent_results[:top_k]
            
            self.logger.log_metric(
                component='vector_retriever',
                event='retrieve_recent',
                wall_time_ms=0,
                tokens_used=len(query.split()),
                metadata={'query': query, 'days': days, 'results': len(final_results)}
            )
            
            return final_results
        
        except Exception as e:
            self.logger.log_metric(
                component='vector_retriever',
                event='retrieve_recent_error',
                wall_time_ms=0,
                tokens_used=0,
                metadata={'query': query, 'days': days, 'error': str(e)}
            )
            return []
    
    async def rerank_results(
        self,
        chunks: List[ChunkSchema],
        query: str,
        rerank_method: str = 'bm25',
    ) -> List[ChunkSchema]:
        """
        Re-rank chunks using secondary scoring (BM25, diversity, etc).
        
        Args:
            chunks: Initial results from semantic search
            query: Original query (for BM25 scoring)
            rerank_method: 'bm25' (keyword match) or 'diversity' (reduce redundancy)
        
        Returns:
            Re-ranked chunks
        """
        if not chunks:
            return chunks
        
        if rerank_method == 'bm25':
            # BM25: Boost chunks with keyword matches in query
            query_terms = set(query.lower().split())
            
            def bm25_score(chunk: ChunkSchema) -> float:
                content_terms = set(chunk.content.lower().split())
                matches = len(query_terms & content_terms)
                return matches / (len(query_terms) + 1)
            
            ranked = sorted(chunks, key=bm25_score, reverse=True)
            return ranked
        
        elif rerank_method == 'diversity':
            # Diversity: Avoid similar chunks, select diverse sources
            selected = []
            seen_domains: Set[str] = set()
            
            for chunk in chunks:
                domain = chunk.metadata.get('domain', '') if chunk.metadata else ''
                if domain not in seen_domains:
                    selected.append(chunk)
                    seen_domains.add(domain)
            
            return selected
        
        else:
            return chunks
    
    async def batch_retrieve(
        self,
        queries: List[str],
        top_k: int = 5,
    ) -> Dict[str, List[ChunkSchema]]:
        """
        Retrieve for multiple queries in parallel.
        
        Args:
            queries: List of query strings
            top_k: Results per query
        
        Returns:
            Dictionary mapping query → results
        """
        results = {}
        
        for query in queries:
            retrieved = await self.retrieve(query, top_k=top_k)
            results[query] = retrieved
        
        self.logger.log_metric(
            component='vector_retriever',
            event='batch_retrieve',
            wall_time_ms=0,
            tokens_used=0,
            metadata={'queries': len(queries), 'top_k': top_k}
        )
        
        return results
    
    async def get_retriever_stats(self) -> Dict[str, Any]:
        """Get retrieval statistics."""
        chroma_stats = self.chroma_mgr.get_stats()
        
        return {
            'chroma_stats': chroma_stats,
            'queried_at': datetime.utcnow().isoformat(),
        }


# Singleton getter for easy import
_retriever_instance = None

async def get_vector_retriever() -> VectorRetriever:
    """Get or create the global vector retriever singleton."""
    global _retriever_instance
    if _retriever_instance is None:
        _retriever_instance = VectorRetriever()
    return _retriever_instance