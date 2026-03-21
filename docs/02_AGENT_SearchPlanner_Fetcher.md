LAST UPDATED: 2026-03-20 14:40 IST  
PROJECT PHASE: Planning / LangGraph Phase 3  

---

# AGENTS 2–3: SearchPlanner & MultiSiteFetcher – Complete Specification

## PURPOSE

**SearchPlanner:** Rank & plan URLs (5–10 sites) based on intent, decide parallelism.  
**MultiSiteFetcher:** Parallel async stealth fetches with bot-detection & fallback handling.

---

## AGENT 2: SEARCHPLANNER (LangGraph)

### Input
```json
{
  "intent_result": {
    "query_type": "product_compare",
    "entities": {"primary": ["iPhone 16", "Pixel 9"], "implicit_sources": [...]},
    "constraints": {"location": "USA", "currency": "USD"}
  }
}
```

### Output (Search Plan)
```json
{
  "search_queries": [
    "iPhone 16 Pro price USA 2026",
    "Google Pixel 9 price USA 2026",
    "iPhone 16 vs Pixel 9 comparison"
  ],
  "ranked_urls": [
    {
      "url": "https://www.apple.com/iphone-16-pro/specs/",
      "rank": 1,
      "source_type": "official",
      "authority_score": 0.99,
      "expected_freshness": "daily"
    },
    {
      "url": "https://www.amazon.com/Apple-iPhone-Unlocked-Smartphone/...",
      "rank": 2,
      "source_type": "retailer",
      "authority_score": 0.85,
      "expected_freshness": "real-time"
    },
    ...
  ],
  "parallelism_level": 6,  // max concurrent fetches
  "fallback_apis": [
    "google_shopping",
    "duckduckgo"
  ],
  "fetch_strategy": "official_then_retail_then_review"
}
```

### Ranking Algorithm

**Factors (weighted):**

```
Score = 0.3 * domain_authority 
       + 0.25 * content_type_relevance 
       + 0.2 * freshness_expectation 
       + 0.15 * language_match 
       + 0.1 * user_location_relevance
```

**Domain Authority Mapping:**

| Domain Type | Authority | Examples |
|-------------|-----------|----------|
| Official brand | 0.99 | apple.com, google.com, samsung.com |
| Major retailer | 0.85 | amazon.com, bestbuy.com, walmart.com |
| Tech review | 0.75 | gsmarena.com, anandtech.com |
| Aggregator | 0.65 | phonearena.com, tomsguide.com |
| General news | 0.60 | reuters.com, wsj.com |
| Blog | 0.40 | random blogs |

### Node Function (LangGraph)

```python
async def node_search_planner(state: AgenticResearchState) → AgenticResearchState:
    """LangGraph node for search planning."""
    intent = state['intent_result']
    
    # Build search queries from intent
    queries = build_search_queries(intent)
    
    # Search using SearchTool (Google + fallback APIs)
    search_results = await search_tool.invoke(
        queries=queries,
        num_results=20  # Get 20 per query, rank top 5–10
    )
    
    # Rank URLs
    ranked = rank_urls(search_results, intent)
    
    # Decide parallelism
    parallelism = min(6, len(ranked['urls']))  # Max 6 parallel fetches
    
    state['search_results'] = ranked
    state['parallelism_level'] = parallelism
    
    return state
```

### SearchTool (Shared Core)

```python
# tools/search.py

class SearchTool:
    async def invoke(queries: List[str], num_results: int = 10):
        """Search using Google (primary), DuckDuckGo (fallback)."""
        results = []
        for query in queries:
            try:
                google_results = search_google(query, num_results)
                results.extend(google_results)
            except RateLimitError:
                # Fallback to DuckDuckGo
                ddg_results = search_duckduckgo(query, num_results)
                results.extend(ddg_results)
        return consolidate_results(results)
```

---

## AGENT 3: MULTISITEFETCHER (LangGraph)

### Input
```json
{
  "search_results": {
    "ranked_urls": [
      {"url": "https://...", "rank": 1, ...},
      ...
    ],
    "parallelism_level": 6
  }
}
```

### Output
```json
{
  "fetch_results": {
    "https://apple.com/...": {
      "status": "success",
      "html": "<html>...</html>",
      "metadata": {
        "title": "iPhone 16 Pro Specs",
        "content_length": 45000,
        "http_status": 200,
        "fetch_time_ms": 2300
      }
    },
    "https://amazon.com/...": {
      "status": "success",
      "html": "...",
      "metadata": {...}
    },
    "https://blocked.com/...": {
      "status": "bot_blocked",
      "http_status": 429,
      "retry_count": 3,
      "fallback_attempted": true,
      "error": "Rate limited after 3 retries"
    }
  },
  "total_fetches": 6,
  "successful_fetches": 5,
  "blocked_count": 1
}
```

### Stealth Strategy

**Headers:**
```python
STEALTH_HEADERS = {
    "User-Agent": rotate_user_agents(),  # Rotate between 10+ real UAs
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
}
```

**Playwright Configuration:**
```python
browser = await playwright.chromium.launch(
    headless=True,
    args=[
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
        "--no-sandbox"
    ]
)

page = await browser.new_page(
    user_agent=rotate_user_agents(),
    viewport={"width": 1920, "height": 1080},
    locale="en-US",
    timezone_id="America/New_York"
)

# Stealth plugins
await page.add_init_script("""
    Object.defineProperty(navigator, 'webdriver', {
        get: () => false,
    });
    Object.defineProperty(navigator, 'plugins', {
        get: () => [1, 2, 3, 4, 5],
    });
""")

html = await page.content()
```

### Retry & Fallback Strategy

```python
async def fetch_with_fallback(url: str, max_retries: int = 3):
    """Fetch with exponential backoff + fallback methods."""
    
    for attempt in range(max_retries):
        try:
            # Method 1: Direct Playwright fetch
            if attempt == 0:
                html = await fetch_playwright(url, stealth=True)
                return {"status": "success", "html": html}
            
            # Method 2: Retry with longer delay
            elif attempt == 1:
                await asyncio.sleep(5)  # Wait 5 seconds
                html = await fetch_playwright(url, stealth=True)
                return {"status": "success", "html": html}
            
            # Method 3: Fallback API (ScraperAPI, BrightData-lite)
            elif attempt == 2:
                html = await fetch_via_fallback_api(url)
                return {"status": "success", "html": html}
        
        except (RateLimitError, TimeoutError) as e:
            if attempt == max_retries - 1:
                return {"status": "bot_blocked", "error": str(e)}
            continue
```

### Node Function (LangGraph)

```python
async def node_multi_fetcher(state: AgenticResearchState) → AgenticResearchState:
    """LangGraph node for parallel stealth fetching."""
    
    ranked_urls = state['search_results']['ranked_urls']
    parallelism = state['parallelism_level']
    
    # Batch URLs into parallel chunks (max 6 concurrent)
    fetch_tasks = [
        fetch_tool.invoke(url) 
        for url in ranked_urls[:parallelism]
    ]
    
    # Await all fetches concurrently
    results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
    
    # Consolidate results
    fetch_results = {}
    for url, result in zip(ranked_urls[:parallelism], results):
        fetch_results[url['url']] = result
    
    state['fetch_results'] = fetch_results
    state['bot_detection_risk'] = calculate_bot_risk(fetch_results)
    
    return state
```

### StealthFetchTool (Shared Core)

```python
# tools/fetch.py

class StealthFetchTool:
    async def invoke(url: str, stealth_level: int = 3):
        """
        Fetch with stealth measures.
        stealth_level: 1=minimal, 3=maximum
        """
        return await fetch_with_fallback(url, max_retries=3)
```

---

## ERROR HANDLING

**Timeout:** 30 seconds per fetch  
**HTTP Errors:**
- 429 (Rate limited) → Retry with backoff
- 403 (Forbidden) → Try fallback API
- 404 (Not found) → Skip, continue with next URL
- 500+ (Server error) → Retry once, then skip

**Bot Detection Signs:**
- Missing content (< 1000 chars)
- Captcha detected (regex match)
- JavaScript-only content (need Playwright, already handled)

---

## TESTING

### Mock Fetch Results
```python
# fixtures/html_samples.json
{
  "apple_iphone": "<html>...</html>",  # Real HTML snippet
  "amazon_iphone": "<html>...</html>"
}
```

### Unit Test
```python
def test_search_planner_ranking():
    intent = {"query_type": "product_compare", ...}
    plan = search_planner(intent)
    assert len(plan['ranked_urls']) >= 5
    assert plan['ranked_urls'][0]['rank'] == 1
    
def test_multi_fetcher_parallelism():
    urls = [url1, url2, url3, url4, url5, url6]
    results = await multi_fetcher(urls)
    assert len(results) == 6
    assert all(r['status'] in ['success', 'bot_blocked'] for r in results.values())
```

---

## PERFORMANCE TARGETS

| Metric | Target |
|--------|--------|
| Search planner latency | <500ms |
| Per-URL fetch latency | 2–5 seconds (with stealth) |
| Total parallelism time | <15 seconds (6 simultaneous) |
| Successful fetch rate | >80% |
| Bot-blocking bypass rate | >70% |

---

## DEPENDENCIES (Shared Core)

```python
import asyncio
import playwright
from playwright.async_api import async_playwright
import httpx  # For HTTP requests
import requests  # Fallback
from urllib.parse import urlparse
import random  # User-Agent rotation
```

---

## NEXT STEPS

1. ✅ Define search ranking algorithm
2. ✅ Implement SearchTool (SearchPlanner)
3. ✅ Implement StealthFetchTool (MultiSiteFetcher)
4. ⏳ Test with 10 real URLs
5. ⏳ Integrate into LangGraph nodes
6. ⏳ Measure bot-detection rate

---

**STATUS:** Ready for implementation  
**ASSIGNED:** Phase 1 (Shared Core)  
**DRIVER:** Stealth + parallelism + resilience
