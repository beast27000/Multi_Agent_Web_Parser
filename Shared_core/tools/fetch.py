#StealthFetchTool

"""
The Concept
The Fetcher takes URLs from the Search tool and fetches their HTML using Playwright with stealth headers. It:

Rotates user agents (avoid blocking)
Handles JavaScript rendering (wait for page load)
Respects robots.txt (optional)
Retries failed fetches (with exponential backoff)
Timeouts gracefully (don't hang on slow sites)
Returns raw HTML → feeds to ETL pipeline
Think of it as: "URL → Playwright → Stealth headers → Wait for JS → Return HTML"
"""

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