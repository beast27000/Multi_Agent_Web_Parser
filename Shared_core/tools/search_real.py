import asyncio
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from duckduckgo_search import DDGS

@dataclass
class SearchResult:
    url: str
    title: str
    snippet: str
    source: str = "duckduckgo"

class RealSearchTool:
    """Real search using DuckDuckGo. No mocks allowed."""
    
    async def search(self, query: str, top_k: int = 5) -> List[SearchResult]:
        """Real search using DuckDuckGo. No mocks allowed."""
        try:
            print(f"Starting Search: {query}")
            from duckduckgo_search import DDGS
            
            ddgs = DDGS()
            # Try text search first
            results = list(ddgs.text(query, max_results=top_k))
            
            # If text search fails, fallback to news to get live context
            if not results:
                print(f"Text search returned 0. Trying news fallback for: {query}")
                results = list(ddgs.news(query, max_results=top_k))
            
            if not results:
                print(f"No results found for: {query}")
                return []
            
            output = []
            for r in results:
                # Handle both text and news return formats
                url = r.get('href') or r.get('url')
                title = r.get('title', 'No Title')
                snippet = r.get('body', '')
                
                if url:
                    output.append(SearchResult(url=url, title=title, snippet=snippet))
            
            print(f"Found {len(output)} search results.")
            return output
        except Exception as e:
            print(f"Search Error: {e}")
            return []
