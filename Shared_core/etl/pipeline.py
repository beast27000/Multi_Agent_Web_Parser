# Orchestrate all 3

"""
The Concept
The Pipeline is the orchestrator and API for the full ETL system. It ties Extract → Transform → Load into one clean interface. Think of it as:

"One method call: pipeline.process_html(html, url) and everything happens."

Plus, it provides utility methods for agents to:

Retrieve cached/embedded chunks for a query
Search by intent, label, or similarity
Export results as markdown or JSON
Log everything for evaluation
"""

# Shared_core/etl/pipeline.py

from typing import List, Dict, Optional, Any
from datetime import datetime
from ..models.chunk import ChunkSchema, ChunkLabel
from ..models.intent import IntentSchema
from ..models.search_plan import SearchPlanSchema
from ..memory.redis_manager import RedisManager
from ..memory.chroma_manager import ChromaManager
from ..memory.markdown_archive import MarkdownArchive
from ..logger.structured_logger import StructuredLogger
from .extractor import HTMLExtractor
from .transformer import TextTransformer
from .loader import ChunkLoader, LoaderPipeline


class ETLPipeline:
    """
    High-level ETL API for agents.
    
    Single entry point: process_html() or process_url()
    Orchestrates: Extract → Transform → Load
    Provides: Search, retrieval, export functions
    """
    
    def __init__(self):
        """Initialize all ETL components."""
        self.extractor = HTMLExtractor()
        self.transformer = TextTransformer()
        self.loader = ChunkLoader()
        self.redis_mgr = RedisManager()
        self.chroma_mgr = ChromaManager()
        self.archive_mgr = MarkdownArchive()
        self.logger = StructuredLogger()
    
    def process_html(
        self,
        html: str,
        url: str,
        source_id: Optional[str] = None,
        query_intent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Full ETL pipeline: Extract HTML → Transform → Load.
        
        Args:
            html: Raw HTML from fetcher
            url: Source URL
            source_id: Optional source identifier (defaults to domain)
            query_intent: Optional query context for logging
        
        Returns:
            Pipeline results: {status, chunks_created, saved_to: {redis, chroma, archive}}
        """
        pipeline_start = datetime.utcnow()
        results = {
            'url': url,
            'source_id': source_id,
            'query_intent': query_intent,
            'started_at': pipeline_start.isoformat(),
        }
        
        try:
            # EXTRACT: HTML → Raw chunk
            raw_chunk = self.extractor.extract_with_schema(html, url, source_id)
            self.logger.log_metric(
                component='pipeline',
                event='extract_complete',
                wall_time_ms=0,
                tokens_used=len(raw_chunk.content.split()),
                metadata={'url': url, 'char_count': len(raw_chunk.content)}
            )
            
            # TRANSFORM: Raw chunk → Semantic chunks
            semantic_chunks = self.transformer.transform_to_chunks(
                raw_chunk, url, source_id or url
            )
            self.logger.log_metric(
                component='pipeline',
                event='transform_complete',
                wall_time_ms=0,
                tokens_used=sum(len(c.content.split()) for c in semantic_chunks),
                metadata={'chunks_created': len(semantic_chunks)}
            )
            
            # LOAD: Save to Redis + Chroma + Markdown
            load_results = self.loader.load_chunks(semantic_chunks, query_intent)
            
            pipeline_end = datetime.utcnow()
            pipeline_ms = (pipeline_end - pipeline_start).total_seconds() * 1000
            
            results.update({
                'status': 'success',
                'chunks_created': len(semantic_chunks),
                'saved_to': {
                    'redis': load_results['redis_saved'],
                    'chroma': load_results['chroma_added'],
                    'archive': load_results['archive_saved'],
                },
                'errors': load_results.get('errors', []),
                'total_time_ms': pipeline_ms,
                'completed_at': pipeline_end.isoformat(),
            })
            
            self.logger.log_metric(
                component='pipeline',
                event='etl_complete',
                wall_time_ms=pipeline_ms,
                tokens_used=sum(len(c.content.split()) for c in semantic_chunks),
                metadata={
                    'url': url,
                    'chunks': len(semantic_chunks),
                    'redis': load_results['redis_saved'],
                    'chroma': load_results['chroma_added'],
                }
            )
        
        except Exception as e:
            pipeline_end = datetime.utcnow()
            results['status'] = 'error'
            results['error'] = str(e)
            results['total_time_ms'] = (pipeline_end - pipeline_start).total_seconds() * 1000
            
            self.logger.log_metric(
                component='pipeline',
                event='etl_error',
                wall_time_ms=results['total_time_ms'],
                tokens_used=0,
                metadata={'url': url, 'error': str(e)}
            )
        
        return results
    
    def search_by_query(
        self,
        query: str,
        intent: IntentSchema,
        top_k: int = 5,
    ) -> List[ChunkSchema]:
        """
        Semantic search: Find top-k most similar chunks to query.
        
        Args:
            query: User question/search string
            intent: Extracted IntentSchema with QueryType
            top_k: Number of results to return (default 5)
        
        Returns:
            List of most relevant ChunkSchema objects
        """
        try:
            # Search Chroma vector DB by similarity
            results = self.chroma_mgr.search(query, top_k=top_k)
            
            self.logger.log_metric(
                component='pipeline',
                event='search_complete',
                wall_time_ms=0,
                tokens_used=len(query.split()),
                metadata={'query': query, 'intent': intent.query_type.value, 'results': len(results)}
            )
            
            return results
        
        except Exception as e:
            self.logger.log_metric(
                component='pipeline',
                event='search_error',
                wall_time_ms=0,
                tokens_used=0,
                metadata={'query': query, 'error': str(e)}
            )
            return []
    
    def search_by_label(
        self,
        label: ChunkLabel,
        top_k: int = 10,
    ) -> List[ChunkSchema]:
        """
        Find all chunks with a specific label (HEADING, PARAGRAPH, CODE_BLOCK, etc).
        
        Args:
            label: ChunkLabel enum value (e.g., HEADING, PARAGRAPH)
            top_k: Max number to return
        
        Returns:
            List of chunks with matching label
        """
        try:
            results = self.chroma_mgr.search_by_label(label, top_k=top_k)
            
            self.logger.log_metric(
                component='pipeline',
                event='search_by_label',
                wall_time_ms=0,
                tokens_used=0,
                metadata={'label': label.value, 'results': len(results)}
            )
            
            return results
        
        except Exception as e:
            self.logger.log_metric(
                component='pipeline',
                event='search_by_label_error',
                wall_time_ms=0,
                tokens_used=0,
                metadata={'label': label.value if label else 'unknown', 'error': str(e)}
            )
            return []
    
    def get_cached_results(
        self,
        query_hash: str,
    ) -> Optional[List[ChunkSchema]]:
        """
        Retrieve cached results for a query (from Redis).
        
        Args:
            query_hash: MD5 hash of query (created by RedisManager)
        
        Returns:
            List of cached ChunkSchema objects, or None if not found/expired
        """
        try:
            cached = self.redis_mgr.get_cached_query_result(query_hash)
            
            if cached:
                self.logger.log_metric(
                    component='pipeline',
                    event='cache_hit',
                    wall_time_ms=0,
                    tokens_used=0,
                    metadata={'query_hash': query_hash, 'chunks': len(cached)}
                )
            
            return cached
        
        except Exception as e:
            self.logger.log_metric(
                component='pipeline',
                event='cache_read_error',
                wall_time_ms=0,
                tokens_used=0,
                metadata={'query_hash': query_hash, 'error': str(e)}
            )
            return None
    
    def cache_results(
        self,
        query_hash: str,
        chunks: List[ChunkSchema],
        ttl_seconds: int = 2700,  # Default 45 mins
    ) -> bool:
        """
        Cache search results for future reuse.
        
        Args:
            query_hash: MD5 hash of query
            chunks: List of ChunkSchema to cache
            ttl_seconds: Time-to-live in seconds (default 45 min)
        
        Returns:
            True if cached successfully
        """
        try:
            self.redis_mgr.cache_query_result(query_hash, chunks, ttl_seconds=ttl_seconds)
            
            self.logger.log_metric(
                component='pipeline',
                event='cache_write',
                wall_time_ms=0,
                tokens_used=0,
                metadata={'query_hash': query_hash, 'chunks': len(chunks)}
            )
            
            return True
        
        except Exception as e:
            self.logger.log_metric(
                component='pipeline',
                event='cache_write_error',
                wall_time_ms=0,
                tokens_used=0,
                metadata={'query_hash': query_hash, 'error': str(e)}
            )
            return False
    
    def export_chunks_as_markdown(
        self,
        chunks: List[ChunkSchema],
        output_file: str,
        title: str = "Search Results",
    ) -> bool:
        """
        Export chunks to a markdown file.
        
        Args:
            chunks: List of ChunkSchema to export
            output_file: Path to write markdown file
            title: Markdown document title
        
        Returns:
            True if export successful
        """
        try:
            from ..utils.markdown_builder import MarkdownBuilder
            
            builder = MarkdownBuilder()
            
            # Create table of chunks
            table_md = builder.create_results_table(chunks)
            
            # Create summary section
            summary_md = builder.create_summary_section(len(chunks), title)
            
            # Combine
            full_doc = f"# {title}\n\n{summary_md}\n\n{table_md}"
            
            # Save to file
            builder.save_to_file(full_doc, output_file)
            
            self.logger.log_metric(
                component='pipeline',
                event='export_markdown',
                wall_time_ms=0,
                tokens_used=sum(len(c.content.split()) for c in chunks),
                metadata={'output_file': output_file, 'chunks': len(chunks)}
            )
            
            return True
        
        except Exception as e:
            self.logger.log_metric(
                component='pipeline',
                event='export_error',
                wall_time_ms=0,
                tokens_used=0,
                metadata={'output_file': output_file, 'error': str(e)}
            )
            return False
    
    def get_pipeline_stats(self) -> Dict[str, Any]:
        """Get aggregate statistics across all memory systems."""
        try:
            stats = {
                'redis': self.redis_mgr.get_stats(),
                'chroma': self.chroma_mgr.get_stats(),
                'archive': self.archive_mgr.get_archive_stats(),
                'queried_at': datetime.utcnow().isoformat(),
            }
            
            self.logger.log_metric(
                component='pipeline',
                event='stats_retrieved',
                wall_time_ms=0,
                tokens_used=0,
                metadata=stats
            )
            
            return stats
        
        except Exception as e:
            self.logger.log_metric(
                component='pipeline',
                event='stats_error',
                wall_time_ms=0,
                tokens_used=0,
                metadata={'error': str(e)}
            )
            return {}
    
    def cleanup(self, days: int = 30) -> Dict[str, Any]:
        """
        Clean up old data (archives older than N days).
        
        Args:
            days: Archive age threshold
        
        Returns:
            Cleanup results
        """
        try:
            removed = self.archive_mgr.cleanup_old_archives(days=days)
            
            results = {
                'status': 'success',
                'archives_removed': removed,
                'cleaned_at': datetime.utcnow().isoformat(),
            }
            
            self.logger.log_metric(
                component='pipeline',
                event='cleanup_complete',
                wall_time_ms=0,
                tokens_used=0,
                metadata={'days': days, 'removed': removed}
            )
            
            return results
        
        except Exception as e:
            results = {
                'status': 'error',
                'error': str(e),
            }
            
            self.logger.log_metric(
                component='pipeline',
                event='cleanup_error',
                wall_time_ms=0,
                tokens_used=0,
                metadata={'days': days, 'error': str(e)}
            )
            
            return results


# Singleton instance for easy import
_pipeline_instance = None

def get_pipeline() -> ETLPipeline:
    """Get or create the global ETL pipeline singleton."""
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = ETLPipeline()
    return _pipeline_instance