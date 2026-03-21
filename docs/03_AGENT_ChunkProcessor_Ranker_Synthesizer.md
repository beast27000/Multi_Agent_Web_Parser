LAST UPDATED: 2026-03-20 14:45 IST  
PROJECT PHASE: Planning / LangGraph Phase 3  

---

# AGENTS 4–6: ChunkProcessor, CrossSiteRanker & FinalSynthesizer – Complete Specification

## PURPOSE

**ChunkProcessor:** ETL transform (HTML → cleaned chunks with labels)  
**CrossSiteRanker:** Rank & compare chunks across sites  
**FinalSynthesizer:** Build final markdown response with tables + summaries  

---

## AGENT 4: CHUNKPROCESSOR (LangGraph)

### Input
```json
{
  "fetch_results": {
    "https://apple.com/...": {
      "status": "success",
      "html": "<html>...</html>",
      "metadata": {...}
    }
  }
}
```

### Output (Processed Chunks)
```json
{
  "processed_chunks": [
    {
      "chunk_id": "apple.com__chunk_0001",
      "source_url": "https://apple.com/iphone-16",
      "source_title": "iPhone 16 Pro Specs",
      "text": "iPhone 16 Pro features a 6.3-inch display...",
      "label": "specs",  // specs, price, review, comparison, etc.
      "token_count": 1240,
      "metadata": {
        "heading": "Technical Specifications",
        "section": 1,
        "dom_depth": 3
      }
    },
    {
      "chunk_id": "apple.com__chunk_0002",
      "source_url": "https://apple.com/iphone-16",
      "source_title": "iPhone 16 Pro Specs",
      "text": "Starting price: $999 for 128GB model...",
      "label": "price",
      "token_count": 180,
      "metadata": {...}
    }
  ],
  "total_chunks": 28,
  "total_tokens": 35420,
  "metadata": {
    "chunk_distribution": {"specs": 12, "price": 5, "review": 8, "other": 3}
  }
}
```

### Chunking Strategy (Semantic + Heading-Based)

**Algorithm:**
1. Parse HTML with BeautifulSoup
2. Extract main content (remove nav, footer, ads)
3. Identify heading hierarchy (h1, h2, h3)
4. Split on heading boundaries
5. Within each section, split if token count > 1800
6. Label each chunk based on content + heading

**Label Types:**
- `specs` → Technical specifications
- `price` → Pricing information
- `review` → User reviews / ratings
- `comparison` → Product comparisons
- `policy` → Terms, policies
- `news` → News blurb
- `other` → Miscellaneous

### Labeling Logic

```python
def label_chunk(text: str, heading: str) -> str:
    """Infer label from text + heading."""
    
    keywords = {
        "price": ["$", "price", "cost", "usd", "eur", "rupee"],
        "specs": ["specification", "feature", "technical", "processor", "ram"],
        "review": ["review", "rating", "pros", "cons", "verdict"],
        "comparison": ["vs", "compare", "better", "faster"],
        "policy": ["terms", "privacy", "policy", "agreement"]
    }
    
    text_lower = text.lower()
    
    for label, kws in keywords.items():
        if any(kw in text_lower or heading.lower() for kw in kws):
            return label
    
    return "other"
```

### Node Function (LangGraph)

```python
async def node_chunk_processor(state: AgenticResearchState) → AgenticResearchState:
    """LangGraph node for ETL processing."""
    
    fetch_results = state['fetch_results']
    chunks = []
    
    for url, fetch_data in fetch_results.items():
        if fetch_data['status'] != 'success':
            continue
        
        html = fetch_data['html']
        
        # Run ETL pipeline
        processed = await etl_pipeline.transform(
            raw_html=html,
            source_url=url,
            source_title=fetch_data['metadata'].get('title', '')
        )
        
        chunks.extend(processed)
    
    # Log token usage
    total_tokens = sum(c['token_count'] for c in chunks)
    logger.log_step(
        step="chunk_processor",
        duration_ms=elapsed_ms,
        tokens_in=0,
        tokens_out=total_tokens
    )
    
    state['processed_chunks'] = chunks
    state['tokens_per_step'].append(total_tokens)
    
    return state
```

### ETL Pipeline (Shared Core)

```python
# etl/pipeline.py

class WebETLPipeline:
    async def extract(self, url: str) → RawHTML:
        """Return raw HTML (already done in MultiSiteFetcher)."""
        pass
    
    async def transform(self, raw_html: str, source_url: str) → List[ChunkSchema]:
        """
        Clean HTML → labeled chunks.
        
        Steps:
        1. Parse with BeautifulSoup
        2. Remove nav, footer, scripts, ads
        3. Identify main content div
        4. Extract text + structure
        5. Split on headings + token limit
        6. Label each chunk
        """
        soup = BeautifulSoup(raw_html, 'html.parser')
        
        # Remove noise
        for tag in soup(['script', 'style', 'nav', 'footer', 'noscript']):
            tag.decompose()
        
        # Extract main content
        main = soup.find('main') or soup.find('article') or soup.body
        
        # Split into sections (headings)
        sections = split_by_headings(main)
        
        chunks = []
        for section in sections:
            text = clean_text(section.get_text())
            heading = extract_heading(section)
            
            # Further split by token limit
            sub_chunks = recursive_split(text, max_tokens=1800)
            
            for sub_text in sub_chunks:
                chunk = ChunkSchema(
                    text=sub_text,
                    label=label_chunk(sub_text, heading),
                    token_count=count_tokens(sub_text),
                    source_url=source_url,
                    heading=heading
                )
                chunks.append(chunk)
        
        # Load to storage
        await self.load(chunks)
        
        return chunks
    
    async def load(self, chunks: List[ChunkSchema]):
        """Load chunks to Chroma + Redis + markdown."""
        for chunk in chunks:
            # Markdown file
            save_markdown(chunk)
            
            # Chroma (embedding)
            embedding = embed_model.encode(chunk.text[:300])
            chroma_manager.add(
                ids=[chunk.chunk_id],
                embeddings=[embedding],
                documents=[chunk.text],
                metadatas=[chunk.metadata]
            )
            
            # Redis cache
            redis_manager.set(
                key=f"chunk:{chunk.chunk_id}",
                value=chunk.to_json(),
                ttl=2700  # 45 min
            )
```

---

## AGENT 5: CROSSSITERANKER (LangGraph)

### Input
```json
{
  "processed_chunks": [...]  // All chunks from all sites
}
```

### Output (Ranked Comparison)
```json
{
  "ranked_summary": {
    "sites": [
      {
        "url": "https://apple.com/iphone-16",
        "domain": "apple.com",
        "rank": 1,
        "authority": 0.99,
        "price": 999,
        "rating": 4.7,
        "key_specs": "6.3-inch OLED, A18 Pro, 8GB RAM",
        "pros": ["Excellent camera", "Fast performance"],
        "cons": ["High price", "No charger in box"],
        "best_for": "Professional photography + gaming"
      },
      {
        "url": "https://google.com/pixel-9",
        "domain": "google.com",
        "rank": 2,
        "authority": 0.99,
        "price": 799,
        "rating": 4.5,
        "key_specs": "6.3-inch OLED, Tensor G4, 12GB RAM",
        "pros": ["AI features", "Lower price"],
        "cons": ["Average battery", "Slower in gaming"],
        "best_for": "AI enthusiasts + general users"
      }
    ],
    "comparison_table": [
      {
        "feature": "Display",
        "apple_iphone": "6.3-inch OLED, 120Hz, ProMotion",
        "google_pixel": "6.3-inch OLED, 120Hz",
        "winner": "Apple (ProMotion)"
      },
      {
        "feature": "Price (USD)",
        "apple_iphone": "$999",
        "google_pixel": "$799",
        "winner": "Google (lower)"
      }
    ],
    "consensus": {
      "best_value": "Google Pixel 9 ($799)",
      "best_overall": "Apple iPhone 16 Pro ($999)",
      "recommendation": "Choose iPhone for photography, Pixel for AI features"
    }
  }
}
```

### Ranking Algorithm

**For each site:**
```
Score = 0.3 * price_competitiveness 
       + 0.25 * avg_rating 
       + 0.2 * recency_score 
       + 0.15 * consensus_agreement 
       + 0.1 * authority_score
```

**Price Competitiveness:** (min_price - site_price) / min_price
- Lower price = higher score
- If site offers best value, score = 1.0

**Avg Rating:** User review ratings (0–5 → 0–1 scale)

**Recency:** Based on last_updated metadata

**Consensus:** How often this site appears in comparison summaries (web search)

### Node Function (LangGraph)

```python
async def node_cross_ranker(state: AgenticResearchState) → AgenticResearchState:
    """LangGraph node for ranking + comparison."""
    
    chunks = state['processed_chunks']
    intent = state['intent_result']
    
    # Group chunks by source
    by_source = group_chunks_by_source(chunks)
    
    # Retrieve best chunks per source using Chroma
    best_chunks_per_source = {}
    for source, source_chunks in by_source.items():
        # Vector search for relevant chunks
        query_embedding = embed_model.encode(state['query'][:300])
        results = chroma_manager.query(
            query_embeddings=[query_embedding],
            n_results=3,
            where={"source_url": source}
        )
        best_chunks_per_source[source] = results
    
    # Rank sites using ranking algorithm
    ranked_sites = rank_sites(best_chunks_per_source, intent)
    
    # Build comparison table
    table_data = build_comparison_table(ranked_sites, intent)
    
    state['ranked_summary'] = {
        'sites': ranked_sites,
        'comparison_table': table_data
    }
    
    return state
```

### RankCompareTool (Shared Core)

```python
# tools/rank_compare.py

class RankCompareTool:
    def invoke(chunks: List[ChunkSchema], intent: dict):
        """Rank chunks + build comparison data."""
        return rank_and_compare(chunks, intent)
```

---

## AGENT 6: FINALSYNTHESIZER (LangGraph)

### Input
```json
{
  "ranked_summary": {...}
}
```

### Output (Markdown Response)
```markdown
# iPhone 16 Pro vs Google Pixel 9 – 2026 Price Comparison

**Query Date:** 2026-03-20  
**Sources:** 5 (official + retailers + reviews)  
**Data Freshness:** Current prices (updated today)

---

## Quick Verdict

🏆 **Best Overall:** Apple iPhone 16 Pro ($999)  
💰 **Best Value:** Google Pixel 9 ($799)  
⭐ **Top Rating:** iPhone 16 Pro (4.7/5)

---

## Detailed Comparison

| Feature | iPhone 16 Pro | Pixel 9 | Winner |
|---------|---------------|--------|--------|
| Display | 6.3" OLED 120Hz ProMotion | 6.3" OLED 120Hz | Apple |
| Price (USD) | $999 | $799 | Google |
| Processor | A18 Pro | Tensor G4 | Apple (gaming) |
| Camera | 48MP Main + 12MP Tele + 12MP Ultra | 50MP Main + 42MP Tele | Apple (telephoto) |
| Battery | ~28 hours | ~24 hours | Apple |

---

## Site Rankings

### 🥇 Rank 1: Apple iPhone 16 Pro ($999)
**Source:** apple.com | Authority: 0.99 | Rating: 4.7/5

**Key Specs:**
- 6.3-inch Dynamic Island OLED, 120Hz ProMotion
- A18 Pro chip, 8GB RAM
- Camera: Triple 48MP + 12MP + 12MP
- Battery: Up to 28 hours

**Pros:**
✅ Excellent camera system (47MP effective with zoom)  
✅ Fastest processor (A18 Pro beats Tensor G4)  
✅ Best display (ProMotion 120Hz)  

**Cons:**
❌ Highest price ($999)  
❌ No charger in box  
❌ Limited AI features vs. Pixel

**Best For:** Professional photographers, gamers, performance enthusiasts

**Source Link:** https://www.apple.com/iphone-16-pro/specs/

---

### 🥈 Rank 2: Google Pixel 9 ($799)
**Source:** google.com | Authority: 0.99 | Rating: 4.5/5

**Key Specs:**
- 6.3-inch OLED, 120Hz
- Tensor G4, 12GB RAM
- Camera: Dual 50MP + 42MP
- Battery: Up to 24 hours

**Pros:**
✅ $200 cheaper than iPhone  
✅ Best AI features (Magic Eraser, Expert)  
✅ Great value for money

**Cons:**
❌ Slower in gaming vs. iPhone  
❌ Lower battery life  
❌ Weaker telephoto camera

**Best For:** AI enthusiasts, budget-conscious buyers, software lovers

**Source Link:** https://store.google.com/product/pixel_9_specs/

---

## Where to Buy

| Retailer | iPhone 16 Pro | Pixel 9 | Free Shipping |
|----------|---------------|---------|---------------|
| Amazon | $999 | $799 | ✅ Yes |
| Best Buy | $999 | $799 | ✅ Yes (2-day) |
| Official Store | $999 | $799 | ✅ Yes |

---

## Final Recommendation

**If budget is not a concern:** Choose **iPhone 16 Pro**  
- Superior camera (especially telephoto)
- Fastest processor
- Best display
- Longer battery life

**If you want great value:** Choose **Google Pixel 9**  
- $200 cheaper
- Excellent AI features
- Clean Android experience
- Still flagship-tier performance

---

## Data Freshness & Confidence

🟢 **High Confidence (0.92/1.0)**  
✓ Official prices verified (Apple.com, Google.com)  
✓ 5 independent sources consulted  
✓ Last updated: 2026-03-20

---

## Methodology

This comparison was generated by analyzing 28 chunks from 5 sources (official + retailers + reviews). Prices are current as of today. Specs verified against official sources.

**Agent Framework:** LangGraph  
**Execution Time:** 45 seconds  
**Tokens Used:** 6,500 / 8,000  
**Bot Detection Risk:** Low (0.15/1.0)

---

*Generated by Agentic Research System (v1.0)*
```

### Node Function (LangGraph)

```python
async def node_synthesizer(state: AgenticResearchState) → AgenticResearchState:
    """LangGraph node for final synthesis."""
    
    intent = state['intent_result']
    ranked = state['ranked_summary']
    query = state['query']
    
    # Build markdown parts
    md_header = build_header(query, intent)
    md_verdict = build_verdict(ranked['sites'])
    md_table = build_comparison_table_markdown(ranked['comparison_table'])
    md_rankings = build_site_rankings_markdown(ranked['sites'])
    md_footer = build_footer(state)
    
    # Combine all parts
    final_md = "\n\n".join([
        md_header,
        md_verdict,
        md_table,
        md_rankings,
        md_footer
    ])
    
    # Attach metadata
    metadata = {
        "wall_time_ms": elapsed_ms,
        "rss_delta_mb": measure_rss_delta(),
        "tokens_total": sum(state['tokens_per_step']),
        "tokens_per_step": state['tokens_per_step'],
        "bot_detection_risk": state.get('bot_detection_risk', 0),
        "execution_time": elapsed_ms / 1000
    }
    
    state['final_response'] = final_md
    state['metadata'] = metadata
    
    logger.log_step(
        step="synthesizer",
        duration_ms=elapsed_ms,
        tokens_in=0,
        tokens_out=count_tokens(final_md)
    )
    
    return state
```

### Markdown Builder (Shared Core)

```python
# utils/markdown_builder.py

def build_header(query: str, intent: dict) -> str:
    """Build markdown header with query + context."""
    ...

def build_verdict(sites: List[dict]) -> str:
    """Build quick verdict section."""
    ...

def build_comparison_table_markdown(table_data: List[dict]) -> str:
    """Build markdown table."""
    ...

def build_site_rankings_markdown(sites: List[dict]) -> str:
    """Build detailed site rankings."""
    ...

def build_footer(state: dict) -> str:
    """Build footer with metadata + confidence."""
    ...
```

---

## ERROR HANDLING

**If all sites fail to rank:**
- Return "Unable to rank sites" message
- Provide raw chunk summary as fallback

**If chunks have conflicting data:**
- Flag inconsistency in Comment
- Let user manually resolve

**If markdown generation fails:**
- Return structural error explanation
- Return raw data as JSON backup

---

## TESTING

### Mock Ranked Summary
```json
{
  "sites": [{...}, {...}],
  "comparison_table": [{...}]
}
```

### Unit Test
```python
def test_final_synthesizer():
    result = synthesizer(ranked_summary)
    assert "# " in result  # Has header
    assert "| Feature |" in result  # Has table
    assert "https://" in result  # Has links
    assert result.count("##") >= 2  # Has sections
```

---

## PERFORMANCE TARGETS

| Metric | Target |
|--------|--------|
| Chunk processor latency | <3 seconds (for 50 chunks) |
| Cross-ranker latency | <2 seconds (vector search + ranking) |
| Synthesizer latency | <1 second (markdown generation) |
| Final markdown size | 2–8 KB |
| Total end-to-end time | <45 seconds |

---

## DEPENDENCIES (Shared Core)

```python
from bs4 import BeautifulSoup
import chromadb
from redis import Redis
import tiktoken
import json
```

---

## NEXT STEPS

1. ✅ Define chunk labeling strategy
2. ✅ Implement ETL pipeline (transform + load)
3. ✅ Implement CrossSiteRanker
4. ✅ Implement markdown builders
5. ⏳ Test with real queries
6. ⏳ Integrate all 3 agents into LangGraph

---

**STATUS:** Ready for implementation  
**ASSIGNED:** Phase 1 (Shared Core) + Phase 3 (LangGraph nodes)  
**DRIVER:** ETL + semantic chunking + markdown synthesis
