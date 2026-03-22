#SearchTool

"""
The Concept
The Loader is the final stage of ETL. It takes the semantic chunks from the Transformer and orchestrates saving them to three memory systems simultaneously:

Redis (fast cache, 45-min TTL, for recent queries)
Chroma (vector embeddings, semantic search)
Markdown Archive (persistent disk storage, human-readable)
Think of it as: "Take chunks, embed them, deduplicate, cache, and archive — all at once."
"""


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