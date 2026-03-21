# LangGraph Agent Implementation Plan (End-to-End)

**CREATED:** 2026-03-20  
**STATUS:** Planning Phase  
**FRAMEWORK:** LangGraph  
**BASE DIR:** `C:\Multi_Agent_Web_Parsser_Proejct\Langraph_Agent\`  

---

## EXECUTIVE SUMMARY

This document outlines the **complete, step-by-step implementation** of the LangGraph-based agentic web research system. It covers:
- Shared Core (reusable across all frameworks)
- LangGraph-specific orchestration & agent chains
- Testing & integration
- One-command CLI execution

**Total Phases:** 7 (Shared Core → Simple Flow → LangGraph → Evaluation → UI)  
**Current Focus:** Phases 1–3 (Shared Core + Simple Flow + LangGraph)

---

## PART 1: SHARED CORE ARCHITECTURE

**Location:** `C:\Multi_Agent_Web_Parsser_Proejct\Shared_core\`

The Shared Core is built **once** and imported by all 3 frameworks (LangGraph, CrewAI, AutoGen).

### 1.1 Folder Structure

```
Shared_core/
├── __init__.py
├── config/                    # Config management
│   ├── __init__.py
│   ├── settings.py            # Pydantic BaseSettings (YAML + env override)
│   └── constants.py           # Global constants (chunk size, max tokens, etc)
├── etl/                        # Extract-Transform-Load Pipeline
│   ├── __init__.py
│   ├── extractor.py           # extract(url) → RawHTML
│   ├── transformer.py         # transform(html) → CleanedChunks[]
│   ├── loader.py              # load(chunks) → {md, Chroma, Redis}
│   └── pipeline.py            # WebETLPipeline orchestrator
├── logger/                     # Observability
│   ├── __init__.py
│   ├── structured_logger.py   # Wall time, RSS delta, tokens, handoffs
│   └── json_exporter.py       # JSON logs for evaluation
├── tools/                      # Reusable Tool Definitions
│   ├── __init__.py
│   ├── search.py              # SearchTool (Google, DuckDuckGo fallback)
│   ├── fetch.py               # StealthFetchTool (Playwright + plugins)
│   ├── etl_processor.py       # ChunkETLTool
│   ├── vector_retrieve.py     # VectorRetrieveTool (Chroma)
│   └── rank_compare.py        # RankCompareTool
├── memory/                     # Hybrid Memory System
│   ├── __init__.py
│   ├── redis_manager.py       # Redis short-term cache (TTL 45 min)
│   ├── chroma_manager.py      # Chroma long-term vector store
│   └── markdown_archive.py    # Persistent markdown file storage
├── models/                     # Pydantic Models (Schemas)
│   ├── __init__.py
│   ├── intent.py              # IntentSchema JSON
│   ├── search_plan.py         # SearchPlanSchema
│   ├── chunk.py               # ChunkSchema (labeled chunks)
│   └── ranking.py             # RankingSchema (comparison results)
├── utils/                      # Utilities
│   ├── __init__.py
│   ├── token_counter.py       # Token counting (tiktoken)
│   ├── stealth_headers.py     # Browser stealth headers
│   └── markdown_builder.py    # Clean markdown table/summary builders
└── pyproject.toml             # Shared dependencies
```

### 1.2 Key Shared Components

#### `config/settings.py`
```
- Pydantic BaseSettings
- Loads from YAML + env override
- Fields: llm_url, llm_model, chunk_max_tokens=1800, 
  max_sites=8, stealth_level, redis_ttl=2700, chroma_path, etc.
```

#### `etl/pipeline.py`
```
class WebETLPipeline:
    async def extract(url: str) → RawHTML
    async def transform(raw: RawHTML) → CleanedChunks[]
    async def load(chunks: CleanedChunks[]) → {md_path, chunk_ids, redis_keys}
```

#### `logger/structured_logger.py`
```
class StructuredLogger:
    - log_step(step, duration_ms, tokens_in, tokens_out, context)
    - log_handoff(from_agent, to_agent, payload)
    - export_metrics() → JSON report
    - tracks: wall_time, RSS delta (psutil), tokens/step, bot-detection risk
```

#### `memory/redis_manager.py` & `chroma_manager.py`
```
- RedisManager: cache query results (TTL 45 min), pub/sub for agent whiteboard
- ChromaManager: semantic search (embed title + first 300 tokens)
- Fallback: markdown file archive if Redis/Chroma unavailable
```

#### `tools/` - Tool Definitions (LangGraph-compatible)
```
- Each tool: name, description, input_schema (Pydantic), invoke(args)
- SearchTool: queries Google/DuckDuckGo, returns top 5–10 URLs
- StealthFetchTool: Playwright + stealth plugins, detects bot-blocking
- ChunkETLTool: feeds raw HTML through transform → chunks
- VectorRetrieveTool: queries Chroma, returns similar chunks
- RankCompareTool: compares chunks across sites (price, recency, consensus)
```

---

## PART 2: LANGRAPH-SPECIFIC ARCHITECTURE

**Location:** `C:\Multi_Agent_Web_Parsser_Proejct\Langraph_Agent\`

### 2.1 LangGraph Folder Structure

```
Langraph_Agent/
├── __init__.py
├── __main__.py                # CLI entry point: `python -m langraph_agent run --query "..."`
├── config.yaml                # Framework-specific config (LangGraph state size limits, etc)
├── requirements.txt           # LangGraph, Pydantic, Playwright, etc.
├── orchestrator.py            # Main LangGraph graph builder
├── agents/
│   ├── __init__.py
│   ├── intent_extractor.py   # Agent 1: parse query → JSON schema
│   ├── search_planner.py     # Agent 2: rank URLs + fallbacks
│   ├── multi_fetcher.py      # Agent 3: parallel async fetches
│   ├── chunk_processor.py    # Agent 4: ETL transform + labeling
│   ├── cross_ranker.py       # Agent 5: compare across sites
│   └── synthesizer.py        # Agent 6: build final markdown response
├── nodes/                     # LangGraph node functions
│   ├── __init__.py
│   ├── node_intent.py        # Node wrapping intent_extractor
│   ├── node_search.py        # Node wrapping search_planner
│   ├── node_fetch.py         # Node wrapping multi_fetcher
│   ├── node_process.py       # Node wrapping chunk_processor
│   ├── node_rank.py          # Node wrapping cross_ranker
│   └── node_synthesize.py    # Node wrapping synthesizer
├── state.py                   # LangGraph State definition
├── edges.py                   # LangGraph edge logic (routing)
├── tests/
│   ├── __init__.py
│   ├── test_intent.py
│   ├── test_flow.py
│   └── test_e2e.py
├── examples/
│   ├── query_samples.json     # Example queries for testing
│   └── expected_outputs/      # Gold standard outputs for evaluation
└── README.md                  # Quick start guide
```

### 2.2 LangGraph State Definition (`state.py`)

```python
class AgenticResearchState(TypedDict):
    """Global flow state carried through all nodes."""
    # Input
    query: str
    query_type: Literal["product_compare", "news", "policy", "fact_check"]
    
    # Intent extraction
    intent_result: dict  # {entities, aspects, sources}
    
    # Search planning
    search_results: list  # [{url, rank, source_type}]
    
    # Fetching
    fetch_results: dict  # {url: {status, chunks_ids, error?}}
    
    # Processing
    processed_chunks: list  # [ChunkSchema]
    
    # Ranking
    ranked_summary: dict  # {sites: [...], table_data: [...]}
    
    # Synthesis
    final_response: str  # Markdown
    metadata: dict  # {tokens_total, time_ms, bot_risk_score}
```

### 2.3 LangGraph Nodes (6 Agent Roles)

Each node is a pure function that reads state, processes, and returns updated state.

#### Node 1: Intent Extractor
```python
async def node_intent_extractor(state: AgenticResearchState) → AgenticResearchState:
    - Input: state.query
    - Call intent_extractor agent (LLM-based or rule-based)
    - Output: intent_result = {query_type, entities, aspects, dynamic_schema}
    - Return updated state
```

#### Node 2: Search Planner
```python
async def node_search_planner(state: AgenticResearchState) → AgenticResearchState:
    - Input: state.intent_result
    - Call search_planner agent → SearchTool (5–10 URLs)
    - Rank by domain authority, recency, language
    - Output: search_results = [{url, rank, type}]
    - Return updated state
```

#### Node 3: Multi-Site Fetcher
```python
async def node_multi_fetcher(state: AgenticResearchState) → AgenticResearchState:
    - Input: state.search_results (top 6 URLs max)
    - Parallel async calls: StealthFetchTool(url)
    - Detect bot-blocking, retry with fallback
    - Output: fetch_results = {url: {status, raw_html, metadata}}
    - Return updated state
```

#### Node 4: Chunk Processor
```python
async def node_chunk_processor(state: AgenticResearchState) → AgenticResearchState:
    - Input: state.fetch_results
    - For each raw_html:
      - Call WebETLPipeline.transform() → CleanedChunks[]
      - Label each chunk (price/review/fact/policy/etc)
      - Ensure ≤1800 tokens per chunk
    - Load into Chroma + Redis + markdown
    - Output: processed_chunks = [ChunkSchema]
    - Return updated state
```

#### Node 5: Cross-Site Ranker
```python
async def node_cross_ranker(state: AgenticResearchState) → AgenticResearchState:
    - Input: state.processed_chunks
    - Retrieve 2–3 chunks per site (via Chroma + query)
    - Rank by: price consistency, recency, consensus across sites, avg rating
    - Build comparison table (markdown-ready)
    - Output: ranked_summary = {sites: [...], table_data: [...]}
    - Return updated state
```

#### Node 6: Synthesizer
```python
async def node_synthesizer(state: AgenticResearchState) → AgenticResearchState:
    - Input: state.ranked_summary
    - Build final markdown:
      - Header with query + query_type
      - Comparison table (if 3+ sites)
      - Per-site summaries + pros/cons
      - Direct source links + timestamps
      - Confidence scores
    - Output: final_response (markdown string)
    - Attach metadata (tokens used, wall time, bot risk)
    - Return updated state
```

### 2.4 LangGraph Edge Logic (`edges.py`)

```python
def route_after_intent(state: AgenticResearchState) → str:
    """Decide next node after intent extraction."""
    if state.intent_result["query_type"] == "error":
        return "END"  # Invalid query
    return "search_planner"

def route_after_search(state: AgenticResearchState) → str:
    """Decide next node after search planning."""
    if not state.search_results:
        return "END"  # No results found
    return "multi_fetcher"

def route_after_fetch(state: AgenticResearchState) → str:
    """Decide next node after fetching."""
    if all(status == "error" for status in state.fetch_results.values()):
        return "END"  # All fetches failed
    return "chunk_processor"

# Remaining routes: processor → ranker → synthesizer → END
```

### 2.5 Orchestrator (`orchestrator.py`)

```python
def build_langgraph() → StateGraph:
    """Construct the complete LangGraph workflow."""
    graph = StateGraph(AgenticResearchState)
    
    # Add nodes
    graph.add_node("intent", node_intent_extractor)
    graph.add_node("search", node_search_planner)
    graph.add_node("fetch", node_multi_fetcher)
    graph.add_node("process", node_chunk_processor)
    graph.add_node("rank", node_cross_ranker)
    graph.add_node("synthesize", node_synthesizer)
    
    # Add conditional edges (routing)
    graph.add_conditional_edges(
        "intent",
        route_after_intent,
        {
            "search_planner": "search",
            "END": END
        }
    )
    ... (similar for other nodes)
    
    # Set entry & compile
    graph.set_entry_point("intent")
    return graph.compile()
```

---

## PART 3: SIMPLE FLOW (Before LangGraph)

**Location:** `C:\Multi_Agent_Web_Parsser_Proejct\simple_flow\` (optional, Phase 2)

A minimal read-only version to validate the Shared Core works:

```python
# simple_flow.py
async def main(query: str):
    # 1. Intent extraction (rule-based, no LLM)
    intent = parse_intent(query)
    
    # 2. Search planning (hardcoded sources)
    urls = search_plan(intent)
    
    # 3. Fetch (serial, no parallelism)
    raw_htmls = [await fetch(url) for url in urls]
    
    # 4. ETL + chunk
    chunks = []
    for html in raw_htmls:
        c = await etl_pipeline.transform(html)
        chunks.extend(c)
    
    # 5. Simple ranking (no ML)
    ranked = simple_rank(chunks)
    
    # 6. Markdown output
    md = build_markdown(ranked)
    print(md)
```

**Purpose:** Verify Shared Core (tools, ETL, logger, memory) without framework complexity.

---

## PART 4: BUILD PHASES (Timeline)

### Phase 1: Shared Core (1–2 days)
- [ ] Create folder structure
- [ ] Implement Config (settings.py + YAML)
- [ ] Implement ETL Pipeline (extract → transform → load)
- [ ] Implement Logger (wall time, RSS, tokens)
- [ ] Implement Tools (Search, Fetch, etc)
- [ ] Implement Memory (Redis, Chroma, markdown)
- [ ] Implement Models (Pydantic schemas)
- [ ] Write unit tests for each component

### Phase 2: Simple Flow (0.5–1 day)
- [ ] Build simple_flow.py (rule-based, no LLM)
- [ ] Test end-to-end with hardcoded queries
- [ ] Validate Shared Core works
- [ ] Log output for baseline metrics

### Phase 3: LangGraph Implementation (1–2 days)
- [ ] Define AgenticResearchState
- [ ] Implement 6 agent nodes (intent → synthesizer)
- [ ] Define edge routing logic
- [ ] Build orchestrator.py
- [ ] Test single-node at a time
- [ ] Full graph test with example query
- [ ] Implement CLI: `python -m langraph_agent run --query "..."`

### Phase 4: CrewAI Implementation (1–2 days)
- [ ] Replicate 6 agents as CrewAI agents
- [ ] Define CrewAI tasks + tools
- [ ] Build CrewAI crew
- [ ] CLI: `python -m crewai_agent run --query "..."`

### Phase 5: AutoGen Implementation (1–2 days)
- [ ] Define conversable agents (6 agents)
- [ ] Register Shared Core tools
- [ ] Build agent interaction loop
- [ ] CLI: `python -m autogen_agent run --query "..."`

### Phase 6: Evaluation Harness (1–2 days)
- [ ] Create 40–60 gold queries (gold.jsonl)
- [ ] Metrics: accuracy, token efficiency, wall time, bot-detection rate
- [ ] Batch eval: `python -m agentic_research eval --frameworks langgraph,crewai,autogen --runs 3`
- [ ] Generate comparison tables

### Phase 7: UI + Advanced Features (2–3 days, optional)
- [ ] Minimal Streamlit chat interface
- [ ] Form interaction (Playwright phase 2+)
- [ ] Persist evaluation results

---

## PART 5: DEPENDENCIES

### Shared Core Requirements
```
pydantic>=2.0
pyyaml
redis
chromadb
playwright
beautifulsoup4
requests
tiktoken
psutil
langfuse
python-dotenv
```

### LangGraph-Specific
```
langgraph
langchain
langchain-core
anthropic (or OpenAI, ollama, etc)
```

### CrewAI-Specific (Phase 4)
```
crewai
crewai-tools
```

### AutoGen-Specific (Phase 5)
```
pyautogen
```

---

## PART 6: CONFIGURATION (YAML)

**File:** `Shared_core/config_default.yaml`

```yaml
# LLM
llm:
  url: "http://localhost:8000/v1"  # Local Ollama or Qwen endpoint
  model: "qwen-3-4b-vl"
  max_tokens: 8000
  temperature: 0.3

# Chunking
chunking:
  max_tokens: 1800
  overlap: 300
  strategy: "heading_based"  # or "sliding_window"

# Fetching
fetching:
  max_sites: 8
  timeout_sec: 30
  stealth_level: 3  # 1=minimal, 3=maximum (detect detection)
  retry_count: 3

# Memory
memory:
  redis:
    host: "localhost"
    port: 6379
    ttl_sec: 2700  # 45 min
  chroma:
    db_path: "./data/chroma"
    embed_model: "all-MiniLM-L6-v2"
  markdown:
    output_dir: "./data/markdown_archive"

# Logging
logging:
  level: "INFO"
  json_export_dir: "./logs/json"
  track_metrics:
    - wall_time
    - rss_delta
    - tokens_per_step
    - bot_detection_risk
    
# Observability
observability:
  langfuse_enabled: false  # Set true if Langfuse is available
  langfuse_key: ""
```

---

## PART 7: Testing Strategy

### Unit Tests (Shared Core)
```
tests/
├── test_config.py        # YAML loading, validation
├── test_etl.py          # Extract, transform, load separately
├── test_logger.py       # Metrics tracking
├── test_tools.py        # Individual tools (Search, Fetch, etc)
├── test_memory.py       # Redis, Chroma, markdown
└── test_models.py       # Pydantic schema validation
```

### Integration Tests (Simple Flow)
```
tests/
├── test_simple_flow.py  # End-to-end without framework
└── fixtures/
    ├── sample_queries.json
    └── sample_htmls/     # Cached HTML for repeatability
```

### LangGraph Tests
```
tests/
├── test_nodes.py        # Each node in isolation
├── test_edges.py        # Routing logic
├── test_full_graph.py   # Complete flow
└── test_cli.py          # CLI argument parsing
```

---

## PART 8: Metrics & Success Criteria

By end of LangGraph implementation (Phase 3), we should have:

- ✅ Shared Core tested and modular (0 copies for other frameworks)
- ✅ LangGraph graph compiles and runs locally
- ✅ Example query produces markdown output (multi-site comparison)
- ✅ Metrics logged: wall_time < 60s, tokens < 8k total, no crashes on bot detection
- ✅ CLI works: `python -m langraph_agent run --query "compare iPhone 16 vs Pixel 9 price India"`
- ✅ Full tracking files updated with decisions

---

## PART 9: Known Constraints & Trade-offs

| Constraint | Impact | Mitigation |
|-----------|--------|-----------|
| ~8k tokens/LLM call | Reduce model size to 4B-7B | Qwen-3-4B-VL, use chunking |
| 1.8k tokens/chunk | More ETL steps | Semantic heading-based split |
| 2–3 chunks visible | Need good retrieval | Chroma embedding + BM25 hybrid |
| Stealth headers needed | Detection risk | Playwright plugin + rotating UA |
| Local model (no cloud) | Speed trade-off | Accept 30–60s per query |
| Redis dependency | One more service | Optional: fallback to dict cache |

---

## PART 10: Next Steps (Immediate)

1. **Confirm permission** with user to create file stubs (ask questions if needed)
2. **Create folder structure** (all directories listed above)
3. **Implement Shared Core** in priority order:
   - config/settings.py
   - models/ (Pydantic schemas)
   - etl/pipeline.py
   - logger/structured_logger.py
   - tools/
   - memory/
4. **Test Shared Core** with unit tests
5. **Build Simple Flow** to validate
6. **Begin LangGraph** orchestrator + 6 nodes

---

**END OF PLAN**

This document is the source of truth for LangGraph implementation. Refer to it at every step. Update it as decisions change.
