#  Real URLFetcher with Playwright + Redis Caching

"""
Phase 2B: Real URL fetching with Playwright, stealth, caching via Redis.
"""

import asyncio
from typing import Optional, Dict
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib

try:
    from playwright.async_api import async_playwright, Page
except ImportError:
    async_playwright = None
    Page = None


@dataclass
class FetchedPage:
    """Fetched page data."""
    url: str
    html: str
    status_code: int = 200
    title: str = ""
    fetched_at: str = ""
    source: str = "playwright"


class RealURLFetcher:
    """Fetch URLs with Playwright, cache in Redis."""
    
    def __init__(self, redis_client=None, cache_ttl_minutes: int = 45):
        self.redis_client = redis_client
        self.cache_ttl = cache_ttl_minutes * 60  # Convert to seconds
        self.playwright_available = async_playwright is not None
        
        if not self.playwright_available:
            print("⚠️  playwright not installed. Run: pip install playwright")
    
    def _get_cache_key(self, url: str) -> str:
        """Generate cache key from URL."""
        url_hash = hashlib.md5(url.encode()).hexdigest()
        return f"fetched_page:{url_hash}"
    
    async def fetch_url(
        self,
        url: str,
        timeout: int = 30,
        use_cache: bool = True
    ) -> Optional[FetchedPage]:
        """
        Fetch URL with Playwright, cache result.
        
        Args:
            url: URL to fetch
            timeout: Timeout in seconds
            use_cache: Use Redis cache if available
        
        Returns:
            FetchedPage or None
        """
        # Try cache first
        if use_cache and self.redis_client:
            cached = await self._get_cached(url)
            if cached:
                print(f"✓ Cache hit: {url[:50]}...")
                return cached
        
        # Fetch with Playwright
        if self.playwright_available:
            try:
                page = await self._fetch_with_playwright(url, timeout)
                if page and self.redis_client:
                    await self._cache_page(url, page)
                return page
            except Exception as e:
                print(f"⚠️  Playwright fetch failed for {url}: {e}")
        
        # Fallback: simple requests
        try:
            page = await self._fetch_with_requests(url, timeout)
            if page and self.redis_client:
                await self._cache_page(url, page)
            return page
        except Exception as e:
            print(f"⚠️  Requests fetch failed for {url}: {e}")
            return None
    
    async def _fetch_with_playwright(self, url: str, timeout: int) -> Optional[FetchedPage]:
        """Fetch using Playwright with stealth."""
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",  # Prevent memory issues
                ]
            )
            
            # Create page with stealth headers
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            
            page = await context.new_page()
            page.set_default_timeout(timeout * 1000)
            
            try:
                # Navigate with timeout
                await page.goto(url, wait_until="domcontentloaded")
                
                # Wait for content to load
                await asyncio.sleep(1)
                
                # Get page content
                html = await page.content()
                title = await page.title()
                
                return FetchedPage(
                    url=url,
                    html=html,
                    status_code=200,
                    title=title,
                    fetched_at=datetime.utcnow().isoformat(),
                    source="playwright"
                )
            finally:
                await context.close()
                await browser.close()
    
    async def _fetch_with_requests(self, url: str, timeout: int) -> Optional[FetchedPage]:
        """Fallback: fetch using httpx."""
        try:
            import httpx
        except ImportError:
            print("⚠️  httpx not available")
            return None
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
            )
            
            return FetchedPage(
                url=url,
                html=response.text,
                status_code=response.status_code,
                title=url,
                fetched_at=datetime.utcnow().isoformat(),
                source="httpx"
            )
    
    async def _get_cached(self, url: str) -> Optional[FetchedPage]:
        """Get cached page from Redis."""
        if not self.redis_client:
            return None
        
        try:
            cache_key = self._get_cache_key(url)
            cached_data = await self.redis_client.get(cache_key)
            
            if cached_data:
                import json
                data = json.loads(cached_data)
                return FetchedPage(**data)
        except Exception as e:
            print(f"Cache retrieval error: {e}")
        
        return None
    
    async def _cache_page(self, url: str, page: FetchedPage):
        """Cache page in Redis."""
        if not self.redis_client:
            return
        
        try:
            cache_key = self._get_cache_key(url)
            import json
            
            page_dict = {
                "url": page.url,
                "html": page.html,
                "status_code": page.status_code,
                "title": page.title,
                "fetched_at": page.fetched_at,
                "source": page.source
            }
            
            await self.redis_client.setex(
                cache_key,
                self.cache_ttl,
                json.dumps(page_dict)
            )
        except Exception as e:
            print(f"Cache storage error: {e}")


# Singleton instance
_fetcher: Optional[RealURLFetcher] = None

async def get_url_fetcher(redis_client=None) -> RealURLFetcher:
    """Get or create URL fetcher."""
    global _fetcher
    if _fetcher is None:
        _fetcher = RealURLFetcher(redis_client=redis_client)
    return _fetcher
