#ChunkETLTool

# Shared_core/tools/etl_processor.py

from typing import List, Dict, Optional, Any
from datetime import datetime
from ..models.intent import IntentSchema
from ..models.chunk import ChunkSchema
from ..logger.structured_logger import StructuredLogger
from .search import SearchTool
from .fetch import FetchToolWithETL
from ..etl.pipeline import get_pipeline


class ETLProcessorTool:
    """
    High-level tool for agents: Query → Search → Fetch → ETL → Return chunks.
    
    Single entry point: process_query()
    Handles: Search, Fetch, Extract, Transform, Load
    """
    
    def __init__(self):
        """Initialize all tool components."""
        self.search_tool = SearchTool()
        self.fetcher_etl = FetchToolWithETL()
        self.pipeline = get_pipeline()
        self.logger = StructuredLogger()
    
    async def process_query(
        self,
        query: str,
        intent: IntentSchema,
        top_urls: int = 5,
        top_chunks: int = 10,
    ) -> Dict[str, Any]:
        """
        Full pipeline: Search → Fetch → ETL → Return chunks.
        
        Args:
            query: User query string
            intent: Extracted IntentSchema with query type
            top_urls: Number of URLs to search for
            top_chunks: Number of chunks to return
        
        Returns:
            Results with chunks, metadata, timing
        """
        process_start = datetime.utcnow()
        results = {
            'query': query,
            'intent': intent.query_type.value,
            'started_at': process_start.isoformat(),
            'stages': {},
        }
        
        try:
            # STAGE 1: SEARCH
            search_start = datetime.utcnow()
            search_results = await self.search_tool.search(
                query, top_k=top_urls
            )
            search_ms = (datetime.utcnow() - search_start).total_seconds() * 1000
            
            results['stages']['search'] = {
                'status': 'success',
                'time_ms': search_ms,
                'urls_found': len(search_results),
            }
            
            if not search_results:
                results['status'] = 'error'
                results['error'] = 'No search results'
                return results
            
            urls = [r.url for r in search_results]
            
            self.logger.log_metric(
                component='etl_processor',
                event='search_complete',
                wall_time_ms=search_ms,
                tokens_used=len(query.split()),
                metadata={'query': query, 'urls_found': len(urls)}
            )
            
            # STAGE 2: FETCH & ETL
            fetch_start = datetime.utcnow()
            batch_results = await self.fetcher_etl.fetch_and_process_batch(
                urls, query_intent=intent.query_type.value, max_concurrent_fetch=3
            )
            fetch_ms = (datetime.utcnow() - fetch_start).total_seconds() * 1000
            
            results['stages']['fetch_etl'] = {
                'status': 'success',
                'time_ms': fetch_ms,
                'urls_fetched': batch_results['successful_fetches'],
                'chunks_created': batch_results['processed_chunks'],
            }
            
            self.logger.log_metric(
                component='etl_processor',
                event='fetch_etl_complete',
                wall_time_ms=fetch_ms,
                tokens_used=0,
                metadata={
                    'query': query,
                    'urls_fetched': batch_results['successful_fetches'],
                    'chunks': batch_results['processed_chunks'],
                }
            )
            
            # STAGE 3: RETRIEVE TOP CHUNKS
            retrieval_start = datetime.utcnow()
            top_chunks_result = self.pipeline.search_by_query(
                query, intent, top_k=top_chunks
            )
            retrieval_ms = (datetime.utcnow() - retrieval_start).total_seconds() * 1000
            
            results['stages']['retrieval'] = {
                'status': 'success',
                'time_ms': retrieval_ms,
                'chunks_retrieved': len(top_chunks_result),
            }
            
            self.logger.log_metric(
                component='etl_processor',
                event='retrieval_complete',
                wall_time_ms=retrieval_ms,
                tokens_used=len(query.split()),
                metadata={'query': query, 'chunks': len(top_chunks_result)}
            )
            
            process_ms = (datetime.utcnow() - process_start).total_seconds() * 1000
            
            results.update({
                'status': 'success',
                'chunks': top_chunks_result,
                'chunk_count': len(top_chunks_result),
                'total_time_ms': process_ms,
                'completed_at': datetime.utcnow().isoformat(),
            })
        
        except Exception as e:
            process_ms = (datetime.utcnow() - process_start).total_seconds() * 1000
            results['status'] = 'error'
            results['error'] = str(e)
            results['total_time_ms'] = process_ms
            
            self.logger.log_metric(
                component='etl_processor',
                event='process_error',
                wall_time_ms=process_ms,
                tokens_used=0,
                metadata={'query': query, 'error': str(e)}
            )
        
        return results
    
    async def process_urls_only(
        self,
        urls: List[str],
        query_intent: Optional[str] = None,
        top_chunks: int = 10,
    ) -> Dict[str, Any]:
        """
        Skip search, go straight to Fetch → ETL → Retrieve.
        
        Useful when agent already has URLs (e.g., from knowledge base).
        
        Args:
            urls: List of URLs to process
            query_intent: Optional intent context
            top_chunks: Number of chunks to return
        
        Returns:
            Results with chunks
        """
        process_start = datetime.utcnow()
        results = {
            'urls_input': len(urls),
            'query_intent': query_intent,
            'started_at': process_start.isoformat(),
            'stages': {},
        }
        
        try:
            # FETCH & ETL
            fetch_start = datetime.utcnow()
            batch_results = await self.fetcher_etl.fetch_and_process_batch(
                urls, query_intent=query_intent, max_concurrent_fetch=3
            )
            fetch_ms = (datetime.utcnow() - fetch_start).total_seconds() * 1000
            
            results['stages']['fetch_etl'] = {
                'status': 'success',
                'time_ms': fetch_ms,
                'urls_fetched': batch_results['successful_fetches'],
                'chunks_created': batch_results['processed_chunks'],
            }
            
            # RETRIEVE TOP CHUNKS
            retrieval_start = datetime.utcnow()
            if query_intent:
                top_chunks_result = self.pipeline.search_by_label(
                    label=None, top_k=top_chunks  # Generic search
                )
            else:
                top_chunks_result = self.pipeline.search_by_label(
                    label=None, top_k=top_chunks
                )
            retrieval_ms = (datetime.utcnow() - retrieval_start).total_seconds() * 1000
            
            results['stages']['retrieval'] = {
                'status': 'success',
                'time_ms': retrieval_ms,
                'chunks_retrieved': len(top_chunks_result),
            }
            
            process_ms = (datetime.utcnow() - process_start).total_seconds() * 1000
            
            results.update({
                'status': 'success',
                'chunks': top_chunks_result,
                'chunk_count': len(top_chunks_result),
                'total_time_ms': process_ms,
                'completed_at': datetime.utcnow().isoformat(),
            })
        
        except Exception as e:
            process_ms = (datetime.utcnow() - process_start).total_seconds() * 1000
            results['status'] = 'error'
            results['error'] = str(e)
            results['total_time_ms'] = process_ms
            
            self.logger.log_metric(
                component='etl_processor',
                event='process_urls_error',
                wall_time_ms=process_ms,
                tokens_used=0,
                metadata={'url_count': len(urls), 'error': str(e)}
            )
        
        return results
    
    async def process_with_fallback(
        self,
        query: str,
        intent: IntentSchema,
        fallback_urls: Optional[List[str]] = None,
        top_chunks: int = 10,
    ) -> Dict[str, Any]:
        """
        Smart fallback: Try search first, if few results use fallback URLs.
        
        Args:
            query: User query
            intent: Extracted intent
            fallback_urls: URLs to use if search yields <2 results
            top_chunks: Chunks to return
        
        Returns:
            Results with chunks
        """
        # Try search first
        search_results = await self.search_tool.search(query, top_k=5)
        
        if len(search_results) >= 2:
            # Good results from search
            urls_to_use = [r.url for r in search_results]
        elif fallback_urls:
            # Not enough search results, use fallback
            urls_to_use = fallback_urls
        else:
            # Nothing to work with
            return {
                'status': 'error',
                'error': 'No search results and no fallback URLs provided',
                'query': query,
            }
        
        # Process whatever URLs we have
        return await self.process_urls_only(
            urls_to_use, query_intent=intent.query_type.value, top_chunks=top_chunks
        )
    
    async def get_processor_stats(self) -> Dict[str, Any]:
        """Get aggregate stats from all sub-components."""
        return {
            'pipeline_stats': self.pipeline.get_pipeline_stats(),
            'queried_at': datetime.utcnow().isoformat(),
        }
    
    async def close(self):
        """Cleanup resources (close browser, sessions)."""
        try:
            await self.search_tool.close()
            await self.fetcher_etl.fetcher.close()
            
            self.logger.log_metric(
                component='etl_processor',
                event='closed',
                wall_time_ms=0,
                tokens_used=0,
                metadata={}
            )
        except Exception as e:
            self.logger.log_metric(
                component='etl_processor',
                event='close_error',
                wall_time_ms=0,
                tokens_used=0,
                metadata={'error': str(e)}
            )


# Singleton getter for easy import by agents
_processor_instance = None

async def get_etl_processor() -> ETLProcessorTool:
    """Get or create the global ETL processor singleton."""
    global _processor_instance
    if _processor_instance is None:
        _processor_instance = ETLProcessorTool()
    return _processor_instance