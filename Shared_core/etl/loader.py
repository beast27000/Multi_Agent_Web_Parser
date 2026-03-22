# Save to memory backends

"""
The Concept
The Loader is the final stage of ETL. It takes the semantic chunks from the Transformer and orchestrates saving them to three memory systems simultaneously:

Redis (fast cache, 45-min TTL, for recent queries)
Chroma (vector embeddings, semantic search)
Markdown Archive (persistent disk storage, human-readable)
Think of it as: "Take chunks, embed them, deduplicate, cache, and archive — all at once."
"""

# Shared_core/etl/loader.py

import asyncio
from typing import List, Dict, Optional
from ..models.chunk import ChunkSchema
from ..memory.redis_manager import RedisManager
from ..memory.chroma_manager import ChromaManager
from ..memory.markdown_archive import MarkdownArchive
from ..logger.structured_logger import StructuredLogger
from datetime import datetime


class ChunkLoader:
    """Load transformed chunks into memory systems (Redis, Chroma, Markdown)."""
    
    def __init__(self):
        """Initialize all memory managers and logger."""
        self.redis_mgr = RedisManager()
        self.chroma_mgr = ChromaManager()
        self.archive_mgr = MarkdownArchive()
        self.logger = StructuredLogger()
    
    def load_chunks(
        self,
        chunks: List[ChunkSchema],
        query_intent: Optional[str] = None,
    ) -> Dict[str, any]:
        """
        Load a list of chunks into all memory systems.
        
        Args:
            chunks: List of ChunkSchema objects from Transformer
            query_intent: Optional intent string for logging context
        
        Returns:
            Dictionary with load results (counts, errors, timestamps)
        """
        load_start = datetime.utcnow()
        results = {
            'query_intent': query_intent,
            'chunks_received': len(chunks),
            'redis_saved': 0,
            'chroma_added': 0,
            'archive_saved': 0,
            'errors': [],
            'started_at': load_start.isoformat(),
        }
        
        if not chunks:
            self.logger.log_metric(
                component='loader',
                event='load_chunks',
                wall_time_ms=0,
                tokens_used=0,
                metadata={'chunks': 0, 'status': 'no_chunks'}
            )
            return results
        
        # Process each chunk
        for i, chunk in enumerate(chunks):
            try:
                # 1. Add to Chroma (vector DB) — this creates embeddings
                self.chroma_mgr.add_chunk(chunk)
                results['chroma_added'] += 1
                
                # 2. Cache to Redis (fast lookup, prevents duplicate work)
                self.redis_mgr.cache_chunk(chunk)
                results['redis_saved'] += 1
                
                # 3. Archive to Markdown (persistent storage)
                self.archive_mgr.save_chunk(chunk)
                results['archive_saved'] += 1
                
                self.logger.log_metric(
                    component='loader',
                    event='chunk_loaded',
                    wall_time_ms=0,
                    tokens_used=len(chunk.content.split()),
                    metadata={
                        'chunk_index': i,
                        'label': chunk.label.value,
                        'url': chunk.url,
                    }
                )
            
            except Exception as e:
                error_msg = f"Failed to load chunk {i}: {str(e)}"
                results['errors'].append(error_msg)
                self.logger.log_metric(
                    component='loader',
                    event='chunk_load_error',
                    wall_time_ms=0,
                    tokens_used=0,
                    metadata={'chunk_index': i, 'error': str(e)}
                )
        
        load_end = datetime.utcnow()
        load_ms = (load_end - load_start).total_seconds() * 1000
        
        results.update({
            'completed_at': load_end.isoformat(),
            'total_load_time_ms': load_ms,
            'error_count': len(results['errors']),
        })
        
        self.logger.log_metric(
            component='loader',
            event='load_session_complete',
            wall_time_ms=load_ms,
            tokens_used=sum(len(c.content.split()) for c in chunks),
            metadata={
                'chunks': len(chunks),
                'redis_saved': results['redis_saved'],
                'chroma_added': results['chroma_added'],
                'archive_saved': results['archive_saved'],
                'errors': len(results['errors']),
            }
        )
        
        return results
    
    def load_query_session(
        self,
        chunks: List[ChunkSchema],
        query: str,
        intent: str,
        source_urls: List[str],
    ) -> Dict[str, any]:
        """
        Load chunks as part of a query session (for archival).
        
        Args:
            chunks: Processed chunks
            query: Original user query
            intent: Extracted intent
            source_urls: List of source URLs
        
        Returns:
            Session metadata
        """
        session_id = self.archive_mgr.save_query_session(
            chunks=chunks,
            query=query,
            intent=intent,
            source_urls=source_urls
        )
        
        # Also load into fast access layers
        load_results = self.load_chunks(chunks, query_intent=intent)
        
        load_results['session_id'] = session_id
        
        self.logger.log_metric(
            component='loader',
            event='query_session_loaded',
            wall_time_ms=0,
            tokens_used=sum(len(c.content.split()) for c in chunks),
            metadata={'session_id': session_id, 'query': query}
        )
        
        return load_results
    
    def get_load_stats(self) -> Dict[str, any]:
        """Get aggregate statistics from all memory systems."""
        redis_stats = self.redis_mgr.get_stats()
        chroma_stats = self.chroma_mgr.get_stats()
        archive_stats = self.archive_mgr.get_archive_stats()
        
        stats = {
            'redis': redis_stats,
            'chroma': chroma_stats,
            'archive': archive_stats,
            'aggregated_at': datetime.utcnow().isoformat(),
        }
        
        self.logger.log_metric(
            component='loader',
            event='stats_retrieved',
            wall_time_ms=0,
            tokens_used=0,
            metadata=stats
        )
        
        return stats
    
    def cleanup_old_archives(self, days: int = 30) -> Dict[str, any]:
        """
        Clean up old archives (older than N days).
        
        Args:
            days: Keep archives newer than this many days
        
        Returns:
            Cleanup results
        """
        cleaned = self.archive_mgr.cleanup_old_archives(days=days)
        
        self.logger.log_metric(
            component='loader',
            event='cleanup_archives',
            wall_time_ms=0,
            tokens_used=0,
            metadata={'days': days, 'removed': cleaned}
        )
        
        return {'removed': cleaned, 'cleaned_at': datetime.utcnow().isoformat()}


class LoaderPipeline:
    """Orchestrate full ETL pipeline: Extract → Transform → Load."""
    
    def __init__(self):
        """Initialize ETL components."""
        from .extractor import HTMLExtractor
        from .transformer import TextTransformer
        
        self.extractor = HTMLExtractor()
        self.transformer = TextTransformer()
        self.loader = ChunkLoader()
    
    def process_url(
        self,
        html: str,
        url: str,
        source_id: Optional[str] = None,
        query_intent: Optional[str] = None,
    ) -> Dict[str, any]:
        """
        Full ETL: Extract HTML → Transform to chunks → Load to memory.
        
        Args:
            html: Raw HTML from fetch
            url: Source URL
            source_id: Optional source identifier
            query_intent: Optional query context
        
        Returns:
            Full pipeline results
        """
        pipeline_start = datetime.utcnow()
        results = {'url': url, 'stages': {}}
        
        try:
            # EXTRACT
            extract_start = datetime.utcnow()
            raw_chunk = self.extractor.extract_with_schema(html, url, source_id)
            extract_ms = (datetime.utcnow() - extract_start).total_seconds() * 1000
            results['stages']['extract'] = {
                'status': 'success',
                'time_ms': extract_ms,
                'content_length': len(raw_chunk.content),
            }
            
            # TRANSFORM
            transform_start = datetime.utcnow()
            semantic_chunks = self.transformer.transform_to_chunks(
                raw_chunk, url, source_id or url
            )
            transform_ms = (datetime.utcnow() - transform_start).total_seconds() * 1000
            results['stages']['transform'] = {
                'status': 'success',
                'time_ms': transform_ms,
                'chunks_created': len(semantic_chunks),
            }
            
            # LOAD
            load_start = datetime.utcnow()
            load_results = self.loader.load_chunks(semantic_chunks, query_intent)
            load_ms = (datetime.utcnow() - load_start).total_seconds() * 1000
            results['stages']['load'] = {
                'status': 'success',
                'time_ms': load_ms,
                **load_results
            }
            
            pipeline_ms = (datetime.utcnow() - pipeline_start).total_seconds() * 1000
            results['total_time_ms'] = pipeline_ms
            results['status'] = 'success'
        
        except Exception as e:
            results['status'] = 'error'
            results['error'] = str(e)
            results['total_time_ms'] = (
                datetime.utcnow() - pipeline_start
            ).total_seconds() * 1000
        
        return results