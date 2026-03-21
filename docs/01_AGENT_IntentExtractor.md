LAST UPDATED: 2026-03-20 14:35 IST  
PROJECT PHASE: Planning / LangGraph Phase 3  

---

# AGENT 1: IntentExtractor – Complete Specification

## PURPOSE

Extract structured intent from raw user queries. Transform ambiguous natural language into a normalized JSON schema that guides downstream agents (SearchPlanner, MultiSiteFetcher, etc.).

---

## AGENT 1: LANGGRAPH (Framework-Specific)

### Input to IntentExtractor
```
{
  "query": "compare iPhone 16 pro vs Galaxy S25 price USA 2026",
  "context": "user_preferences: {country: 'USA'}"  (optional)
}
```

### Output (JSON Schema)
```json
{
  "query_type": "product_compare",
  "entities": {
    "primary": ["iPhone 16 Pro", "Galaxy S25"],
    "implicit_sources": ["apple.com", "samsung.com", "amazon.com", "best_buy.com"]
  },
  "aspects": {
    "price": 0.9,        // relevance score 0–1
    "performance": 0.6,
    "design": 0.4,
    "camera": 0.5,
    "battery": 0.3
  },
  "constraints": {
    "location": "USA",
    "currency": "USD",
    "language": "en",
    "freshness": "current_prices"  // how recent data should be
  },
  "dynamic_schema": {
    "output_format": "comparison_table",
    "min_sources": 3,
    "sources_strategy": "official + retailers + reviews"
  },
  "confidence": 0.95,
  "error": null
}
```

### Query Types (Dynamic Schemas)

#### Type 1: `product_compare`
```json
{
  "entities": {product_names: [...], implicit_sources: [...]},
  "aspects": {price, performance, design, ...},
  "output_format": "comparison_table"
}
```

#### Type 2: `news_search`
```json
{
  "topic": "...",
  "time_window": "last 7 days",
  "sources_strategy": "news + blogs",
  "output_format": "chronological_summary"
}
```

#### Type 3: `price_tracking`
```json
{
  "product": "...",
  "enable_alerts": true,
  "price_range": {min, max},
  "sources": "ecommerce"
}
```

#### Type 4: `policy_research`
```json
{
  "policy_name": "...",
  "jurisdiction": "...",
  "sources_strategy": "official + legal + news"
}
```

#### Type 5: `fact_check`
```json
{
  "claim": "...",
  "entities": [...],
  "sources_strategy": "reliable_sources + snopes_like"
}
```

### Implementation Approach (No LLM Yet)

**Phase 1 (rule-based, deterministic):**
1. Regex + keyword matching to infer `query_type`
2. Named entity extraction (spacy or simple regex)
3. Domain mapping (iPhone → apple.com, samsung.com, etc.)
4. Hardcoded aspect scores per query type

**Phase 2 (optional LLM-enhanced):**
- Use small LLM (Qwen-3-4B-VL) to refine schema
- Max ~500 tokens (small enough to fit)
- Validate output against Pydantic schema

### Node Function (LangGraph)

```python
async def node_intent_extractor(state: AgenticResearchState) → AgenticResearchState:
    """
    LangGraph node for intent extraction.
    
    Updates state.intent_result with structured JSON.
    """
    query = state.query
    
    # Rule-based extraction
    intent = extract_intent_rules(query)
    
    # Optional LLM refinement (Phase 2)
    # intent = await llm_refine_intent(query, intent)
    
    # Validate against Pydantic
    validated_intent = IntentSchema(**intent)
    
    state['intent_result'] = validated_intent.dict()
    state['query_type'] = validated_intent.query_type
    
    return state
```

### Pydantic Schema (Shared Core)

```python
# models/intent.py

from pydantic import BaseModel, Field
from typing import Literal, Dict, List

class IntentSchema(BaseModel):
    query_type: Literal[
        "product_compare",
        "news_search",
        "price_tracking",
        "policy_research",
        "fact_check"
    ]
    entities: Dict[str, List[str]]  # primary, implicit_sources, etc.
    aspects: Dict[str, float]  # aspect_name → relevance 0–1
    constraints: Dict[str, str]  # location, currency, language, freshness
    dynamic_schema: Dict  # Flexible per query_type
    confidence: float = Field(ge=0, le=1)
    error: Optional[str] = None
```

---

## FALLBACK BEHAVIOR

**If query is too ambiguous:**
```json
{
  "query_type": "unknown",
  "error": "Could not infer intent. Please clarify: product comparison, news, or price?",
  "confidence": 0.2
}
```

**SearchPlanner downstream decision:** Skip if confidence < 0.3, ask user to rephrase.

---

## EXAMPLES

### Example 1: Product Compare Query
```
INPUT: "best budget gaming laptop under $1500 2026"

OUTPUT:
{
  "query_type": "product_compare",
  "entities": {
    "primary": ["budget gaming laptop"],
    "implicit_sources": ["amazon.com", "bestbuy.com", "newegg.com", "dell.com", "asus.com"]
  },
  "aspects": {"price": 1.0, "performance": 0.8, "design": 0.4, "battery": 0.6},
  "constraints": {"currency": "USD", "max_price": 1500, "device_type": "laptop"},
  "dynamic_schema": {"output_format": "ranked_table", "min_sources": 4},
  "confidence": 0.92
}
```

### Example 2: News Query
```
INPUT: "latest news on AI regulation Europe"

OUTPUT:
{
  "query_type": "news_search",
  "entities": {"topic": "AI regulation", "region": "Europe"},
  "aspects": {"recency": 1.0, "credibility": 0.8},
  "constraints": {"time_window": "last 7 days", "language": "en"},
  "dynamic_schema": {"output_format": "timeline"},
  "confidence": 0.88
}
```

---

## ERROR HANDLING

**Cases:**
1. **Empty query** → error: "Empty query provided"
2. **Gibberish** → error: "Query too unclear, confidence < 0.2"
3. **Ambiguous type** → confidence: 0.5, suggest user to rephrase

**SearchPlanner decision:** If confidence < 0.3, return error to user before fetching.

---

## TESTING

### Test Cases (fixtures/intent_samples.json)
```json
[
  {
    "input": "compare iPhone 16 vs Pixel 9 price",
    "expected_type": "product_compare",
    "expected_confidence": ">0.85"
  },
  {
    "input": "latest AI news this week",
    "expected_type": "news_search",
    "expected_confidence": ">0.80"
  }
]
```

### Unit Test (`tests/test_intent.py`)
```python
def test_product_compare_intent():
    result = extract_intent_rules("compare iPhone 16 vs Pixel 9 price")
    assert result['query_type'] == "product_compare"
    assert result['confidence'] > 0.85
    assert "iPhone 16" in result['entities']['primary']
```

---

## PERFORMANCE TARGETS

- **Latency:** <100ms (rule-based, no network calls)
- **Accuracy:** >90% confidence on typical queries
- **Failure rate:** <5% (queries that need rephrase)

---

## DEPENDENCIES (Shared Core)

```python
import re
import spacy  # For NER (Name Entity Recognition)
from pydantic import BaseModel, ValidationError
from typing import Optional, Dict, List, Literal
```

---

## NEXT STEPS

1. ✅ Define Pydantic schema (IntentSchema)
2. ✅ Implement rule-based extraction logic
3. ⏳ Test with 20+ sample queries
4. ⏳ Integrate into LangGraph node
5. ⏳ (Phase 2) Add optional LLM refinement

---

**STATUS:** Ready for implementation  
**ASSIGNED:** Phase 1 (Shared Core)  
**DRIVER:** Rule-based extraction (deterministic, no LLM)
