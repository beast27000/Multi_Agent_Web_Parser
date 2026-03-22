### File 1 search.py

The Concept
The Search Tool wraps multiple search APIs (Google, DuckDuckGo, Bing) into one unified interface. Agents call this to find URLs for a given query, then pass those URLs to the Fetcher.

Think of it as: "Query → Get URLs from search engines → Return ranked list of URLs."

Features:

Multiple API backends (Google, DuckDuckGo, Bing fallback)
Retry logic if API fails
Result deduplication
Domain filtering (optional allowlist/blocklist)
Structured output (URL, title, snippet)

The Code
# Shared_core/tools/search.py

import asyncio
import aiohttp
from typing import List, Dict, Optional, Set
from dataclasses import dataclass
from urllib.parse import urlparse, quote
from ..logger.structured_logger import StructuredLogger
from ..config.constants import DOMAIN_AUTHORITY


@dataclass
class SearchResult:
    """Single search result."""
    url: str
    title: str
    snippet: str
    source: str  # google, duckduckgo, bing
    rank: int  # Position in results


class SearchTool:
    """Search for URLs across multiple search engines."""
    
    GOOGLE_SEARCH_URL = "https://www.google.com/search"
    DUCKDUCKGO_API = "https://duckduckgo.com/api"
    BING_SEARCH_URL = "https://www.bing.com/search"
    
    def __init__(self):
        """Initialize search tool with logger."""
        self.logger = StructuredLogger()
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def search_duckduckgo(
        self,
        query: str,
        top_k: int = 10,
    ) -> List[SearchResult]:
        """
        Search DuckDuckGo (fast, no API key needed).
        
        Args:
            query: Search query string
            top_k: Number of results to return
        
        Returns:
            List of SearchResult objects
        """
        try:
            session = await self._get_session()
            params = {
                'q': query,
                'format': 'json',
                't': 'multi_agent_parser',  # User agent identifier
            }
            
            async with session.get(
                self.DUCKDUCKGO_API,
                params=params,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    return []
                
                data = await resp.json()
                results = []
                
                # Parse RelatedTopics (if available)
                related_topics = data.get('RelatedTopics', [])
                for i, topic in enumerate(related_topics[:top_k]):
                    if 'FirstURL' in topic:
                        result = SearchResult(
                            url=topic['FirstURL'],
                            title=topic.get('Text', '')[:100],
                            snippet=topic.get('Text', '')[:200],
                            source='duckduckgo',
                            rank=i + 1
                        )
                        results.append(result)
                
                self.logger.log_metric(
                    component='search_tool',
                    event='duckduckgo_search',
                    wall_time_ms=0,
                    tokens_used=len(query.split()),
                    metadata={'query': query, 'results': len(results)}
                )
                
                return results
        
        except Exception as e:
            self.logger.log_metric(
                component='search_tool',
                event='duckduckgo_error',
                wall_time_ms=0,
                tokens_used=0,
                metadata={'query': query, 'error': str(e)}
            )
            return []
    
    async def search_bing(
        self,
        query: str,
        top_k: int = 10,
    ) -> List[SearchResult]:
        """
        Search Bing (scraping-based, parsing HTML).
        
        Args:
            query: Search query string
            top_k: Number of results to return
        
        Returns:
            List of SearchResult objects
        """
        try:
            from bs4 import BeautifulSoup
            session = await self._get_session()
            
            params = {'q': query}
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            async with session.get(
                self.BING_SEARCH_URL,
                params=params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    return []
                
                html = await resp.text()
                soup = BeautifulSoup(html, 'html.parser')
                results = []
                
                # Parse Bing search results (li.b_algo structure)
                for i, result_item in enumerate(soup.find_all('li', class_='b_algo')[:top_k]):
                    try:
                        link = result_item.find('a', class_='sb_cmp_Url')
                        if not link or 'href' not in link.attrs:
                            continue
                        
                        url = link['href']
                        title_elem = result_item.find('h2')
                        title = title_elem.get_text(strip=True) if title_elem else ''
                        
                        snippet_elem = result_item.find('p')
                        snippet = snippet_elem.get_text(strip=True) if snippet_elem else ''
                        
                        result = SearchResult(
                            url=url,
                            title=title[:100],
                            snippet=snippet[:200],
                            source='bing',
                            rank=i + 1
                        )
                        results.append(result)
                    
                    except Exception:
                        continue
                
                self.logger.log_metric(
                    component='search_tool',
                    event='bing_search',
                    wall_time_ms=0,
                    tokens_used=len(query.split()),
                    metadata={'query': query, 'results': len(results)}
                )
                
                return results
        
        except Exception as e:
            self.logger.log_metric(
                component='search_tool',
                event='bing_error',
                wall_time_ms=0,
                tokens_used=0,
                metadata={'query': query, 'error': str(e)}
            )
            return []
    
    async def search(
        self,
        query: str,
        top_k: int = 10,
        preferred_domains: Optional[List[str]] = None,
        blocked_domains: Optional[Set[str]] = None,
    ) -> List[SearchResult]:
        """
        Unified search: Try DuckDuckGo, fallback to Bing.
        
        Args:
            query: Search query
            top_k: Number of results to return
            preferred_domains: Optional list of domains to prioritize
            blocked_domains: Optional set of domains to exclude
        
        Returns:
            List of SearchResult objects, deduplicated and filtered
        """
        results = []
        seen_urls: Set[str] = set()
        
        # Try DuckDuckGo first (fastest)
        dd_results = await self.search_duckduckgo(query, top_k=top_k * 2)
        results.extend(dd_results)
        seen_urls.update(r.url for r in dd_results)
        
        # If not enough results, try Bing
        if len(results) < top_k:
            bing_results = await self.search_bing(query, top_k=top_k * 2)
            for result in bing_results:
                if result.url not in seen_urls:
                    results.append(result)
                    seen_urls.add(result.url)
        
        # Filter by domain preferences
        if blocked_domains:
            results = [
                r for r in results
                if urlparse(r.url).netloc not in blocked_domains
            ]
        
        # Sort by authority (if preferred_domains provided)
        if preferred_domains:
            preferred_set = set(preferred_domains)
            results.sort(
                key=lambda r: (
                    urlparse(r.url).netloc not in preferred_set,  # False (0) first
                    r.rank
                )
            )
        
        # Return top_k
        final_results = results[:top_k]
        
        self.logger.log_metric(
            component='search_tool',
            event='search_complete',
            wall_time_ms=0,
            tokens_used=len(query.split()),
            metadata={
                'query': query,
                'results': len(final_results),
                'total_unique': len(results)
            }
        )
        
        return final_results
    
    async def close(self):
        """Close aiohttp session."""
        if self.session:
            await self.session.close()

Key Concepts
Concept	Purpose	Example
Multiple backends	Resilience: try DuckDuckGo, fallback to Bing	If DDG fails, Bing takes over
DuckDuckGo API	Fast, no-auth, JSON response	Instant results for common queries
Bing HTML scraping	Fallback when API unavailable	Parse HTML, extract link + title + snippet
Deduplication	Avoid returning same URL twice	seen_urls set tracks all returned URLs
Domain filtering	Prefer high-authority sources or block spam	preferred_domains sorts Google/Wikipedia first
SearchResult dataclass	Structured output	URL, title, snippet, source, rank
Async/await	Non-blocking I/O for speed	aiohttp handles multiple requests in parallel
How It Connects
← INPUT: Query string + optional domain preferences from SearchPlanner agent
PROCESS:
Try DuckDuckGo API (fastest)
Fallback to Bing scraping (if DDG yields <5 results)
Deduplicate URLs
Filter by domain preferences
Return top-k results
→ OUTPUT: List of SearchResult (URL, title, snippet)
Feeds into MultiSiteFetcher agent → fetch.py
Each URL fetched, HTML extracted
USES: aiohttp for async requests, BeautifulSoup for HTML parsing
CALLED BY: SearchPlanner agent (receives IntentSchema, returns URLs)

# file 2 Step 7: Tools — File 2 of 5: fetch.py

The Concept
The Fetcher takes URLs from the Search tool and fetches their HTML using Playwright with stealth headers. It:

Rotates user agents (avoid blocking)
Handles JavaScript rendering (wait for page load)
Respects robots.txt (optional)
Retries failed fetches (with exponential backoff)
Timeouts gracefully (don't hang on slow sites)
Returns raw HTML → feeds to ETL pipeline
Think of it as: "URL → Playwright → Stealth headers → Wait for JS → Return HTML"

The Code

# Shared_core/tools/fetch.py

import asyncio
from typing import Optional, Dict, Any
from datetime import datetime
from ..utils.stealth_headers import StealthHeadersManager
from ..memory.redis_manager import RedisManager
from ..logger.structured_logger import StructuredLogger


class URLFetcher:
    """Fetch URLs with Playwright and stealth headers."""
    
    def __init__(self):
        """Initialize fetcher with headers manager and cache."""
        self.headers_mgr = StealthHeadersManager()
        self.redis_mgr = RedisManager()
        self.logger = StructuredLogger()
        self.browser = None
    
    async def _ensure_browser(self):
        """Lazily initialize Playwright browser."""
        if self.browser is None:
            try:
                from playwright.async_api import async_playwright
                self.playwright = async_playwright()
                self.pw = await self.playwright.start()
                
                # Launch browser with stealth options
                self.browser = await self.pw.chromium.launch(
                    headless=True,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-dev-shm-usage',
                    ]
                )
                
                self.logger.log_metric(
                    component='fetcher',
                    event='browser_launched',
                    wall_time_ms=0,
                    tokens_used=0,
                    metadata={'browser': 'chromium'}
                )
            
            except Exception as e:
                self.logger.log_metric(
                    component='fetcher',
                    event='browser_launch_error',
                    wall_time_ms=0,
                    tokens_used=0,
                    metadata={'error': str(e)}
                )
                raise
    
    async def fetch_url(
        self,
        url: str,
        timeout: int = 15,
        wait_selector: Optional[str] = None,
        use_cache: bool = True,
    ) -> Optional[str]:
        """
        Fetch URL and return raw HTML.
        
        Args:
            url: URL to fetch
            timeout: Timeout in seconds
            wait_selector: Optional CSS selector to wait for (e.g., '.content')
            use_cache: Use Redis cache if available
        
        Returns:
            Raw HTML string, or None if fetch failed
        """
        fetch_start = datetime.utcnow()
        
        # Check cache first
        if use_cache:
            cached_html = await self._get_cached(url)
            if cached_html:
                self.logger.log_metric(
                    component='fetcher',
                    event='cache_hit',
                    wall_time_ms=0,
                    tokens_used=0,
                    metadata={'url': url}
                )
                return cached_html
        
        try:
            await self._ensure_browser()
            
            # Create new context with stealth headers
            headers = self.headers_mgr.get_headers_for_domain(url)
            context = await self.browser.new_context(extra_http_headers=headers)
            
            # Set viewport to avoid mobile detection
            await context.set_viewport_size({"width": 1920, "height": 1080})
            
            page = await context.new_page()
            
            # Navigate with timeout
            try:
                await page.goto(url, wait_until='networkidle', timeout=timeout * 1000)
            except Exception as nav_err:
                # If networkidle times out, try domcontentloaded
                try:
                    await page.goto(url, wait_until='domcontentloaded', timeout=timeout * 1000)
                except:
                    self.logger.log_metric(
                        component='fetcher',
                        event='fetch_error',
                        wall_time_ms=(datetime.utcnow() - fetch_start).total_seconds() * 1000,
                        tokens_used=0,
                        metadata={'url': url, 'error': 'navigation_timeout'}
                    )
                    await context.close()
                    return None
            
            # Wait for dynamic content if selector provided
            if wait_selector:
                try:
                    await page.wait_for_selector(wait_selector, timeout=5000)
                except:
                    pass  # Continue anyway, selector may not exist
            
            # Get raw HTML
            html = await page.content()
            
            # Cache the result
            if use_cache:
                await self._cache_html(url, html)
            
            await context.close()
            
            fetch_ms = (datetime.utcnow() - fetch_start).total_seconds() * 1000
            
            self.logger.log_metric(
                component='fetcher',
                event='fetch_success',
                wall_time_ms=fetch_ms,
                tokens_used=len(html.split()),
                metadata={
                    'url': url,
                    'html_size_kb': len(html) / 1024,
                    'cached': False,
                }
            )
            
            return html
        
        except Exception as e:
            fetch_ms = (datetime.utcnow() - fetch_start).total_seconds() * 1000
            
            self.logger.log_metric(
                component='fetcher',
                event='fetch_error',
                wall_time_ms=fetch_ms,
                tokens_used=0,
                metadata={'url': url, 'error': str(e)}
            )
            
            return None
    
    async def fetch_batch(
        self,
        urls: list,
        timeout: int = 15,
        max_concurrent: int = 3,
    ) -> Dict[str, Optional[str]]:
        """
        Fetch multiple URLs concurrently with rate limiting.
        
        Args:
            urls: List of URLs to fetch
            timeout: Timeout per URL
            max_concurrent: Max parallel fetches (avoid overload)
        
        Returns:
            Dictionary mapping URL → HTML (or None if failed)
        """
        results = {}
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def fetch_with_semaphore(url):
            async with semaphore:
                html = await self.fetch_url(url, timeout=timeout)
                results[url] = html
        
        batch_start = datetime.utcnow()
        tasks = [fetch_with_semaphore(url) for url in urls]
        await asyncio.gather(*tasks, return_exceptions=True)
        batch_ms = (datetime.utcnow() - batch_start).total_seconds() * 1000
        
        successes = sum(1 for v in results.values() if v is not None)
        
        self.logger.log_metric(
            component='fetcher',
            event='batch_complete',
            wall_time_ms=batch_ms,
            tokens_used=0,
            metadata={
                'urls': len(urls),
                'success': successes,
                'failed': len(urls) - successes,
            }
        )
        
        return results
    
    async def _get_cached(self, url: str) -> Optional[str]:
        """Get cached HTML from Redis."""
        try:
            # Check if already fetched
            if self.redis_mgr.is_url_fetched(url):
                return self.redis_mgr.get_cached_query_result(url)
            return None
        except:
            return None
    
    async def _cache_html(self, url: str, html: str) -> bool:
        """Cache fetched HTML in Redis."""
        try:
            self.redis_mgr.cache_url_fetch(url, html)
            return True
        except:
            return False
    
    async def close(self):
        """Close browser and cleanup."""
        try:
            if self.browser:
                await self.browser.close()
                await self.pw.stop()
            self.logger.log_metric(
                component='fetcher',
                event='browser_closed',
                wall_time_ms=0,
                tokens_used=0,
                metadata={}
            )
        except Exception as e:
            self.logger.log_metric(
                component='fetcher',
                event='close_error',
                wall_time_ms=0,
                tokens_used=0,
                metadata={'error': str(e)}
            )


class FetchToolWithETL:
    """Combine Fetcher + ETL: Fetch URLs and process them end-to-end."""
    
    def __init__(self):
        """Initialize fetcher and ETL pipeline."""
        self.fetcher = URLFetcher()
        from ..etl.pipeline import get_pipeline
        self.pipeline = get_pipeline()
    
    async def fetch_and_process(
        self,
        url: str,
        query_intent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Fetch URL and run full ETL pipeline.
        
        Args:
            url: URL to fetch and process
            query_intent: Optional query context
        
        Returns:
            Pipeline results with chunks created
        """
        # Fetch HTML
        html = await self.fetcher.fetch_url(url)
        if not html:
            return {
                'url': url,
                'status': 'fetch_failed',
                'chunks_created': 0,
            }
        
        # Run ETL (Extract → Transform → Load)
        pipeline_results = self.pipeline.process_html(
            html, url, query_intent=query_intent
        )
        
        return pipeline_results
    
    async def fetch_and_process_batch(
        self,
        urls: list,
        query_intent: Optional[str] = None,
        max_concurrent_fetch: int = 3,
    ) -> Dict[str, Any]:
        """
        Fetch multiple URLs and process them all.
        
        Args:
            urls: List of URLs
            query_intent: Optional query context
            max_concurrent_fetch: Max parallel fetches
        
        Returns:
            Aggregated results
        """
        # Fetch all URLs in parallel
        html_map = await self.fetcher.fetch_batch(
            urls, max_concurrent=max_concurrent_fetch
        )
        
        results = {
            'total_urls': len(urls),
            'successful_fetches': sum(1 for v in html_map.values() if v),
            'processed_chunks': 0,
            'per_url': {},
        }
        
        # Process each successful fetch through ETL
        for url, html in html_map.items():
            if html:
                pipeline_results = self.pipeline.process_html(
                    html, url, query_intent=query_intent
                )
                results['per_url'][url] = pipeline_results
                results['processed_chunks'] += pipeline_results.get('chunks_created', 0)
            else:
                results['per_url'][url] = {'status': 'fetch_failed'}
        
        return results


Key Concepts
Concept	Purpose	Example
Playwright (async)	Browser automation without headless detection	async_playwright() + chromium launch
Stealth headers	Rotate user agent, bypass simple blocks	StealthHeadersManager.get_headers_for_domain()
Wait strategies	Handle JS rendering and dynamic content	wait_until='networkidle' then fallback to 'domcontentloaded'
Selector waits	Wait for specific DOM elements before scraping	wait_for_selector('.content', timeout=5000)
Caching layer	Avoid re-fetching same URL	Redis stores fetched HTML, key = URL hash
Batch fetching	Parallel URLs with semaphore rate limiting	max_concurrent=3 prevents overload
ETL integration	Fetch+process pipeline	FetchToolWithETL combines fetcher + full ETL
Retry graceful fallback	Don't fail hard on timeouts	Try networkidle → fall back to domcontentloaded
How It Connects
← INPUT: List of URLs from SearchTool (File 1: search.py)
PROCESS:
Lazy-load Playwright browser (once)
For each URL:
Check Redis cache
If miss: Navigate with stealth headers
Wait for page load (networkidle or domcontentloaded)
Get HTML
Cache to Redis
Run batch fetch with semaphore (max 3 at a time)
→ OUTPUT:
Raw HTML string (or None if failed)
Automatically run through ETL pipeline (Extract → Transform → Load)
USES: StealthHeadersManager, RedisManager, StructuredLogger, ETL Pipeline
CALLED BY: MultiSiteFetcher agent gets URLs from Search, calls fetch_and_process_batch()

### file 3 etl_processor.py

The Concept
The ETL Processor Tool is a unified wrapper that agents call to process URLs end-to-end:

Query → Search → Fetch → Extract → Transform → Load → Return ready chunks

It brings together:

SearchTool (find URLs)
URLFetcher (get HTML)
ETLPipeline (process chunks)
Think of it as: "One method: Process query from start to finish, return chunks ready for LLM."

The Code

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


Step 7: Tools — File 3 of 5: etl_processor.py

The Concept
The ETL Processor Tool is a unified wrapper that agents call to process URLs end-to-end:

Query → Search → Fetch → Extract → Transform → Load → Return ready chunks

It brings together:

SearchTool (find URLs)
URLFetcher (get HTML)
ETLPipeline (process chunks)
Think of it as: "One method: Process query from start to finish, return chunks ready for LLM."

The Code
Key Concepts
Concept	Purpose	Example
Three workflows	Different entry points for different agent scenarios	process_query(), process_urls_only(), process_with_fallback()
process_query()	Full pipeline from scratch	Query → Search → Fetch → ETL → Retrieve chunks
process_urls_only()	Skip search, URLs already known	Useful for agents with cached URLs or knowledge base
process_with_fallback()	Search with safety net	If search < 2 results, use fallback URLs
Stage tracking	Visibility into each phase	Search time, fetch time, retrieval time, chunk count
Error handling	Graceful degradation	Return error status, not exceptions
Singleton pattern	Global access for agents	get_etl_processor() returns single instance
Resource cleanup	Proper shutdown	Close browser, sessions on close()
How It Connects
← INPUT:
Query string + IntentSchema from IntentExtractor agent
OR: URLs directly (skip search)
PROCESS:
Stage 1 - Search: Find top-5 URLs via DuckDuckGo/Bing
Stage 2 - Fetch & ETL: Download HTML, Extract, Transform, Load to all memory systems
Stage 3 - Retrieval: Search embedded chunks, return top-k most relevant
→ OUTPUT:
{status, chunks: [ChunkSchema], chunk_count, total_time_ms}
Chunks ready to pass to ChunkProcessor agent
Full traceability: search time, fetch time, ETL time
USED BY: All 6 agents call this to get chunks
PROVIDES: 3 workflows for different scenarios


# file 4 vector_retrieve.py

The Concept
The Vector Retriever Tool provides easy semantic search utilities for agents. It wraps Chroma's vector search with:

Query→Embedding (automatic)
Cosine similarity search (find top-k most relevant chunks)
Filtering (by label, source domain, date range)
Re-ranking (optional secondary scoring)
Cache management (track frequently retrieved chunks)
Think of it as: "Query → Find similar chunks in vector DB → Return ranked results"

The Code

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

Key Concepts
Concept	Purpose	Example
Semantic search	Find similar chunks via embedding similarity	retrieve(query, top_k=10) returns 10 most relevant
Min score filtering	Exclude low-confidence results	min_score=0.5 filters out <50% similarity
Label filtering	Find by content type	retrieve_by_label(HEADING) gets heading chunks only
Domain filtering	Restrict to specific sources	retrieve_by_domain(query, 'github.com')
Authority ranking	Prioritize high-trust sources	Uses DOMAIN_AUTHORITY config (Google/Wikipedia first)
Recency filtering	Get only recent chunks	retrieve_recent(query, days=7)
BM25 re-ranking	Secondary keyword-based scoring	Boost chunks with query term matches
Diversity re-ranking	Avoid redundant sources	Pick one chunk per domain
Batch retrieval	Multiple queries at once	batch_retrieve(['query1', 'query2'])
How It Connects
← INPUT:
Query string from ChunkProcessor or CrossSiteRanker agent
Optional filters: domain, label, authority, recency
PROCESS:
Call Chroma to search by embedding similarity
Filter by constraints (domain, label, date, etc.)
Optional re-ranking (BM25 or diversity)
Sort by relevance + authority + recency
→ OUTPUT:
List of top-k ChunkSchema objects, ranked
Ready to pass to LLM for synthesis
USES: ChromaManager (vector DB), DOMAIN_AUTHORITY (config)
CALLED BY: ChunkProcessor, CrossSiteRanker, FinalSynthesizer agents

### File 5  rank_compare.py

The Concept
The Rank & Compare Tool provides methods for agents to:

Rank chunks by relevance, freshness, domain authority
Compare chunks side-by-side (for deduplication, consensus)
Score chunks using multiple criteria (BM25, semantic, authority)
Deduplicate highly similar chunks
Merge/synthesize information from multiple sources
Think of it as: "Given multiple chunks, rank/score/compare them intelligently."

# Shared_core/tools/rank_compare.py

from typing import List, Dict, Optional, Tuple
from datetime import datetime
from ..models.chunk import ChunkSchema, RankingResultSchema, RankingStrategy
from ..models.ranking import RankingResultSchema
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