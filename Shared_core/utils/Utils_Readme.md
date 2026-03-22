### File 1: token_counter.py — Count LLM Tokens

This file estimates how many tokens a string uses (important for enforcing MAX_TOKENS_PER_CALL = 8000).

# Shared_core/utils/token_counter.py

import tiktoken
from typing import Union

class TokenCounter:
    """Estimate token counts for text using tiktoken (OpenAI's tokenizer)."""
    
    def __init__(self, model_name: str = "gpt-3.5-turbo"):
        """
        Args:
            model_name: Model to use for tokenization.
                       Default: "gpt-3.5-turbo" (close to Qwen token density).
        """
        self.encoding = tiktoken.encoding_for_model(model_name)
    
    def count_tokens(self, text: Union[str, list]) -> int:
        """
        Count tokens in text or list of strings.
        
        Args:
            text: String or list of strings
        
        Returns:
            Token count
        """
        if isinstance(text, list):
            text = " ".join(text)
        
        return len(self.encoding.encode(text))
    
    def truncate_to_max_tokens(self, text: str, max_tokens: int) -> str:
        """
        Truncate text to fit within max_tokens.
        Ensures text never exceeds token limit.
        
        Args:
            text: Text to truncate
            max_tokens: Maximum allowed tokens
        
        Returns:
            Truncated text
        """
        tokens = self.encoding.encode(text)
        if len(tokens) <= max_tokens:
            return text
        
        # Trim to max_tokens and decode back to text
        truncated_tokens = tokens[:max_tokens]
        return self.encoding.decode(truncated_tokens)
    
    def estimate_chunk_fit(self, chunks: list, max_tokens_per_chunk: int) -> dict:
        """
        Check if a list of chunks fits within token limits.
        Useful for multi-chunk context windows.
        
        Args:
            chunks: List of chunk strings
            max_tokens_per_chunk: Token limit per chunk
        
        Returns:
            {
                "total_tokens": int,
                "chunks_that_fit": int,
                "chunks_exceeding_limit": int,
                "needs_truncation": bool
            }
        """
        fitting_count = 0
        exceeding_count = 0
        total_tokens = 0
        
        for chunk in chunks:
            token_count = self.count_tokens(chunk)
            total_tokens += token_count
            
            if token_count <= max_tokens_per_chunk:
                fitting_count += 1
            else:
                exceeding_count += 1
        
        return {
            "total_tokens": total_tokens,
            "chunks_that_fit": fitting_count,
            "chunks_exceeding_limit": exceeding_count,
            "needs_truncation": exceeding_count > 0
        }


# Singleton instance for easy reuse
_counter = None

def get_token_counter() -> TokenCounter:
    """Get or create the global TokenCounter instance."""
    global _counter
    if _counter is None:
        _counter = TokenCounter()
    return _counter

    Key Concepts:

Concept	Purpose	Used By
count_tokens()	Measure text size before sending to LLM	ChunkProcessor, LLM interface, ranker
truncate_to_max_tokens()	Ensure no chunk exceeds token limit	ChunkProcessor, MultiSiteFetcher
estimate_chunk_fit()	Check if chunks fit in context window	SearchPlanner (multi-chunk validation)
tiktoken library	OpenAI's official tokenizer (close to Qwen)	Token counting backbone
Singleton pattern	Reuse same tokenizer instance globally	Performance (encoding loads once)
How It Connects:

constants.py defines MAX_TOKENS_PER_CALL (8000) + MAX_CHUNK_SIZE (1800) → TokenCounter enforces them
ChunkProcessor calls count_tokens() on each chunk before storing in Chroma
LLM interface calls truncate_to_max_tokens() before sending to Qwen model

Example usage:

from Shared_core.utils import get_token_counter

counter = get_token_counter()
token_count = counter.count_tokens("What is the capital of France?")
print(f"Tokens: {token_count}")  # ~9 tokens

truncated = counter.truncate_to_max_tokens(long_text, max_tokens=1800)


### File 2: stealth_headers.py — Browser Headers to Avoid Bot Detection

When Playwright fetches websites, servers can detect it as a bot. This file generates realistic browser headers to look human.

CODE:

# Shared_core/utils/stealth_headers.py

import random
from typing import Dict

class StealthHeadersManager:
    """Generate realistic browser headers to avoid bot detection."""
    
    # Popular user agents (rotated to appear as different browsers)
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.2) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1.1 Safari/605.1.15",
    ]
    
    # Realistic accept-language headers (common locales)
    ACCEPT_LANGUAGES = [
        "en-US,en;q=0.9",
        "en-GB,en;q=0.8",
        "en-US,en;q=0.9,es;q=0.8",
        "en-US,en;q=0.9,fr;q=0.8",
    ]
    
    @staticmethod
    def get_random_headers() -> Dict[str, str]:
        """
        Generate a random set of realistic browser headers.
        Call this before every request to appear as a different client.
        
        Returns:
            Dict of HTTP headers
        """
        return {
            "User-Agent": random.choice(StealthHeadersManager.USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": random.choice(StealthHeadersManager.ACCEPT_LANGUAGES),
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        }
    
    @staticmethod
    def get_headers_for_domain(domain: str) -> Dict[str, str]:
        """
        Get headers customized for a specific domain (add domain-specific referrer).
        
        Args:
            domain: Target domain (e.g., "amazon.com")
        
        Returns:
            Dict of HTTP headers with domain-specific referer
        """
        headers = StealthHeadersManager.get_random_headers()
        headers["Referer"] = f"https://www.google.com/search?q={domain}"
        return headers
    
    @staticmethod
    def get_headers_with_custom_ua(user_agent: str) -> Dict[str, str]:
        """
        Get headers with a specific user agent override.
        
        Args:
            user_agent: Custom user agent string
        
        Returns:
            Dict of HTTP headers with custom UA
        """
        headers = StealthHeadersManager.get_random_headers()
        headers["User-Agent"] = user_agent
        return headers


# Convenience functions for quick usage
def get_random_headers() -> Dict[str, str]:
    """Get random stealth headers."""
    return StealthHeadersManager.get_random_headers()


def get_headers_for_domain(domain: str) -> Dict[str, str]:
    """Get headers for a specific domain."""
    return StealthHeadersManager.get_headers_for_domain(domain)

Key Concepts:

Concept	Purpose	Used By
USER_AGENTS list	Rotate browser identities per request	Each fetch looks different
ACCEPT_LANGUAGES	Realistic locale headers	Bot detection evasion
get_random_headers()	Generate full header dict per request	MultiSiteFetcher
get_headers_for_domain()	Add referrer = Google search result	Realistic session flow
DNT, Sec-Fetch-*	Modern privacy/security headers (legit browsers send these)	Detection bypass
Class + static methods	Easy to import and use everywhere	All fetch operations
How It Connects:

MultiSiteFetcher calls get_random_headers() before each Playwright fetch
SearchPlanner can call get_headers_for_domain() when clicking on URLs

Example usage:

from Shared_core.utils import get_random_headers

headers = get_random_headers()
# headers now has realistic User-Agent, Accept-Language, etc.
# Pass to Playwright: page.goto(url, headers=headers)

Rotating user agents prevents IP-based rate limiting
Referrer header makes requests look like they came from a Google search


### File 3: markdown_builder.py — Format Output as Markdown Tables

This file builds human-readable markdown tables from agent results (for the final output).

# Shared_core/utils/markdown_builder.py

from typing import List, Dict, Optional
from datetime import datetime

class MarkdownBuilder:
    """Build formatted markdown tables and documents from structured data."""
    
    @staticmethod
    def create_results_table(
        results: List[Dict],
        title: str = "Search Results",
        columns: Optional[List[str]] = None
    ) -> str:
        """
        Create a markdown table from list of result dicts.
        
        Args:
            results: List of dicts (each dict = one row)
            title: Table title
            columns: Column names to include (if None, use all keys from first result)
        
        Returns:
            Markdown table string
        """
        if not results:
            return f"## {title}\n\nNo results found.\n"
        
        # Determine columns
        if columns is None:
            columns = list(results[0].keys())
        
        # Build markdown table
        markdown = f"## {title}\n\n"
        markdown += "| " + " | ".join(columns) + " |\n"
        markdown += "| " + " | ".join(["---"] * len(columns)) + " |\n"
        
        for result in results:
            row_values = []
            for col in columns:
                value = result.get(col, "")
                # Escape pipes in cell values
                value = str(value).replace("|", "\\|")
                row_values.append(value)
            markdown += "| " + " | ".join(row_values) + " |\n"
        
        return markdown
    
    @staticmethod
    def create_comparison_section(
        comparisons: List[Dict],
        metric_name: str = "Comparison Metrics"
    ) -> str:
        """
        Create markdown section for cross-site comparisons.
        
        Args:
            comparisons: List of comparison dicts with 'source', 'metric', 'value'
            metric_name: Section title
        
        Returns:
            Markdown section string
        """
        markdown = f"## {metric_name}\n\n"
        
        for comp in comparisons:
            source = comp.get("source", "Unknown")
            metric = comp.get("metric", "")
            value = comp.get("value", "")
            markdown += f"- **{source}**: {metric} = {value}\n"
        
        return markdown
    
    @staticmethod
    def create_summary_section(
        query: str,
        total_sources: int,
        total_chunks_processed: int,
        top_insight: str
    ) -> str:
        """
        Create markdown summary section at top of doc.
        
        Args:
            query: Original user query
            total_sources: Number of websites fetched
            total_chunks_processed: Total chunks analyzed
            top_insight: Key finding/summary
        
        Returns:
            Markdown section string
        """
        timestamp = datetime.utcnow().isoformat()
        
        markdown = f"""# {query}

**Generated:** {timestamp}

## Summary
{top_insight}

## Metrics
- **Sources:** {total_sources}
- **Chunks Processed:** {total_chunks_processed}
- **Timestamp:** {timestamp}

---

"""
        return markdown
    
    @staticmethod
    def create_full_document(
        query: str,
        summary_insight: str,
        results_table: str,
        comparisons_section: str,
        sources: List[Dict],
        total_chunks: int
    ) -> str:
        """
        Combine all sections into one complete markdown document.
        
        Args:
            query: User query
            summary_insight: Key finding
            results_table: Markdown table from create_results_table()
            comparisons_section: Markdown from create_comparison_section()
            sources: List of source dicts with 'url', 'domain', 'chunks_count'
            total_chunks: Total chunks analyzed
        
        Returns:
            Complete markdown document string
        """
        doc = MarkdownBuilder.create_summary_section(
            query=query,
            total_sources=len(sources),
            total_chunks_processed=total_chunks,
            top_insight=summary_insight
        )
        
        doc += results_table + "\n"
        doc += comparisons_section + "\n"
        
        # Sources section
        doc += "## Sources\n\n"
        for source in sources:
            url = source.get("url", "")
            domain = source.get("domain", "")
            chunks = source.get("chunks_count", 0)
            doc += f"- [{domain}]({url}) — {chunks} chunks\n"
        
        return doc
    
    @staticmethod
    def save_to_file(content: str, output_path: str) -> None:
        """
        Write markdown content to file.
        
        Args:
            content: Markdown string
            output_path: Path to output file (e.g., "./output/result.md")
        """
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

Key Concepts:

Concept	Purpose	Used By
create_results_table()	Convert list of dicts → markdown table	FinalSynthesizer
create_comparison_section()	Format ranking/comparison results	CrossSiteRanker output
create_summary_section()	Header with timestamp + metrics	Document top section
create_full_document()	Combine all sections into one doc	End-to-end output builder
save_to_file()	Write markdown to disk	Persistent output storage
Escaping |	Prevent markdown table breaks in cell values	Data integrity
How It Connects:

FinalSynthesizer calls create_full_document() after all ranking done
Example output file: ./output/query_result.md (human-readable table)
Used by: demo scripts, evaluation harness, user-facing results

Example usage:

from Shared_core.utils import MarkdownBuilder

table = MarkdownBuilder.create_results_table(
    results=[
        {"source": "Amazon", "price": "$99.99", "rating": "4.5"},
        {"source": "Walmart", "price": "$89.99", "rating": "4.2"}
    ],
    title="Price Comparison"
)
MarkdownBuilder.save_to_file(table, "./output/comparison.md")
