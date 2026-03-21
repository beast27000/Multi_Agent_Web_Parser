LAST UPDATED: 2026-03-20 14:30 IST  
PROJECT PHASE: Planning / Shared Core Phase Starting  

---

# MAIN PROJECT PLAN – Agentic Web Research Comparison Study

## PROJECT GOAL

Build a **publishable, reproducible research project** comparing three open-source multi-agent frameworks (**LangGraph**, **CrewAI**, **AutoGen**) on their ability to **gather real-time web information** using small local vision-language models (~27k context max).

**Primary Research Question:** How do agent frameworks differ in:
- **Accuracy** of multi-site synthesis
- **Token efficiency** (max 8k per LLM call)
- **Latency** (wall clock time per query)
- **Bot-detection resilience** (stealth + fallbacks)
- **Code maintainability** (SLOC, complexity, chaining flexibility)

**Expected Output:** Comparison paper + benchmark tables + open-source repo with reproducible pipeline.

---

## HARD CONSTRAINTS (Non-Negotiable)

| Constraint | Reason | Enforcement |
|-----------|--------|-------------|
| Max ~8,000 tokens/LLM call | Local 4B-7B model context limit (27k total) | Chunking pipeline + schema validation |
| Max ~1,800 tokens/chunk | Preserve context for agent reasoning | Semantic heading-based splitting |
| Agents see 2–3 chunks max per query | Reduce hallucination, focus on retrieval | Chroma vector DB + BM25 hybrid |
| No cloud LLM calls | Keep local/stealth + reproducible | Use Ollama/vLLM + local Qwen-3-4B-VL |
| Extract-Transform-Load first | Clean data before agents | ETL pipeline runs before any agent |
| Logging at every step | Evaluation metrics collection | Structured JSON logs + RSS memory tracking |

---

## ARCHITECTURE OVERVIEW

### High-Level Flow

```
[User Query]
     ↓
[CLI / Future Chat]
     ↓
[Orchestrator: Pick framework + inject shared services]
     ↓
┌─────────────────────────────────────────────────┐
│           SHARED CORE (Reusable Once)           │
├─────────────────────────────────────────────────┤
│ • Config (Pydantic + YAML)                      │
│ • ETL Pipeline (Extract → Transform → Load)     │
│ • Tools (Search, Fetch, Chunk, Rank, etc)     │
│ • Logger (Wall time, RSS, tokens, handoffs)     │
│ • Memory (Redis hot + Chroma long-term + MD)   │
│ • Observability (Langfuse + JSON logs)          │
└─────────────────────────────────────────────────┘
     ↓ (parallel branches)
┌──────────────┬──────────────┬──────────────┐
│  LangGraph   │   CrewAI     │   AutoGen    │
│  (Phase 3)   │   (Phase 4)  │   (Phase 5)  │
└──────────────┴──────────────┴──────────────┘
     ↓ (all converge)
[6-Agent Chain: Intent → Search → Fetch → Process → Rank → Synthesize]
     ↓
[Markdown Response + Metrics]
     ↓
[Evaluation Harness: Batch 40–60 queries, compare frameworks]
```

### Agent Roles (6 Modular Agents)

**Agent 1: IntentExtractor**
- **Input:** Raw user query (e.g., "compare iPhone 16 vs Pixel 9 price")
- **Job:** Normalize query → extract entities, aspects, implicit sources
- **Output:** Structured JSON (query_type, entities, aspects, dynamic_schema)
- **Technologies:** Rule-based + optional small LLM

**Agent 2: SearchPlanner**
- **Input:** Intent JSON
- **Job:** Build search strategy: top 5–10 URLs, fallback APIs, parallelism level
- **Output:** Ranked URL list with metadata (domain authority, source type)
- **Technologies:** SearchTool (Google, DuckDuckGo, API fallbacks)

**Agent 3: MultiSiteFetcher**
- **Input:** Ranked URLs (max 6 parallel)
- **Job:** Stealth fetch HTML + metadata, detect bot-blocking, retry with fallback
- **Output:** {url: {status, raw_html, metadata, error?}}
- **Technologies:** Playwright + stealth headers, timeout handling

**Agent 4: ChunkProcessor**
- **Input:** Raw HTML per site
- **Job:** Clean (BeautifulSoup) → split into labeled chunks (≤1800 tok each)
- **Output:** CleanedChunks[] with labels (price/review/fact/policy/etc)
- **Technologies:** ETL pipeline, token counter, semantic chunking

**Agent 5: CrossSiteRanker**
- **Input:** All cleaned chunks across sites
- **Job:** Retrieve contextual chunks → rank by price/recency/consensus/rating
- **Output:** Comparison data (table-ready, pros/cons per site)
- **Technologies:** Chroma vector retrieval, ranking algorithm

**Agent 6: FinalSynthesizer**
- **Input:** Ranked comparison data
- **Job:** Build markdown response with tables, summaries, direct links, confidence
- **Output:** Clean markdown + metadata (tokens used, wall time, bot risk)
- **Technologies:** Markdown builder, confidence scoring

**Memory Sharing (Cross-Agent):**
- Redis short-term: Query cache (TTL 45 min), agent whiteboard (pub/sub)
- Chroma long-term: Semantic index (dynamic per query + persistent for repeated domains)
- Markdown archive: Persistent chunked data for replay/debugging

---

## ROADMAP (Strict Execution Order)

### Phase 1: Shared Core Infrastructure (Est. 1–2 days)
**Deliverables:**
- [ ] Folder structure: config/, etl/, logger/, tools/, memory/, models/, utils/
- [ ] Config mgmt (settings.py + config.yaml)
- [ ] ETL pipeline (extract → transform → load)
- [ ] Structured logger (wall_time, RSS delta, tokens per step)
- [ ] Tool definitions (Search, Fetch, ChunkETL, VectorRetrieve, RankCompare)
- [ ] Memory managers (Redis, Chroma, markdown)
- [ ] Pydantic schemas (Intent, SearchPlan, Chunk, Ranking)
- [ ] Unit tests for all components

**Success Criteria:**
- All imports work without circular dependencies
- Config loads from YAML + environment override
- ETL pipeline processes sample HTML → chunks (verified by token count)
- Logger exports JSON metrics
- Tools are callable as LangGraph/CrewAI-compatible objects

**Location:** `Shared_core/` (ONE copy, imported by all 3 frameworks)

---

### Phase 2: Simple Read-Only Flow (Est. 0.5–1 day)
**Deliverables:**
- [ ] Minimal orchestrator (no framework, no LLM)
- [ ] Rule-based intent extraction
- [ ] Hardcoded search + fetch + ETL + rank + markdown
- [ ] End-to-end test with example query
- [ ] Baseline metrics (tokens, wall_time, RSS)

**Success Criteria:**
- Script runs: `python simple_flow.py --query "..."`
- Output: Multi-site markdown with 3+ sources
- No external LLM call, all logic is deterministic

**Purpose:** Validate Shared Core works before adding framework/LLM complexity.

**Location:** `simple_flow/` (optional, for validation only)

---

### Phase 3: LangGraph Implementation (Est. 1–2 days)
**Deliverables:**
- [ ] State definition (AgenticResearchState)
- [ ] 6 node functions (intent → synthesizer)
- [ ] Edge routing logic
- [ ] Orchestrator (StateGraph compilation)
- [ ] CLI: `python -m langraph_agent run --framework langgraph --query "..."`
- [ ] Unit tests per node
- [ ] Full graph integration test
- [ ] Update tracking file: 01_AGENT_IntentExtractor (LangGraph subsection)

**Success Criteria:**
- Graph compiles without errors
- Single example query completes end-to-end
- Output matches simple flow format
- Metrics logged correctly
- CLI works with `--query`, `--framework` args

**Location:** `Langraph_Agent/`

---

### Phase 4: CrewAI Implementation (Est. 1–2 days)
**Deliverables:**
- [ ] 6 agents with tools (inherit Shared Core)
- [ ] Crew definition + task ordering
- [ ] CLI: `python -m crewai_agent run --query "..."`
- [ ] Tests mirroring LangGraph tests
- [ ] Update tracking file: 02_AGENT_SearchPlanner_Fetcher (CrewAI subsection)

**Success Criteria:**
- Output format identical to LangGraph
- Metrics comparable (tokens, time, accuracy)

**Location:** `CrewAI_Agent/`

---

### Phase 5: AutoGen Implementation (Est. 1–2 days)
**Deliverables:**
- [ ] Conversable agents (6 agents)
- [ ] Agent interaction loop + tool registration
- [ ] CLI: `python -m autogen_agent run --query "..."`
- [ ] Tests
- [ ] Update tracking file: 03_AGENT_ChunkProcessor_Ranker_Synthesizer (AutoGen subsection)

**Success Criteria:**
- Same output format + metrics

**Location:** `AutoGen_Agent/`

---

### Phase 6: Evaluation Harness (Est. 1–2 days)
**Deliverables:**
- [ ] 40–60 gold queries (gold.jsonl): {query, expected_sites, entities, aspects}
- [ ] Metrics framework: accuracy, precision@3, token efficiency, wall_time, bot_detection_rate
- [ ] Batch eval runner: `python -m agentic_research eval --queries gold.jsonl --frameworks langgraph,crewai,autogen --runs 3`
- [ ] Comparison tables (markdown + CSV)
- [ ] Statistical analysis (mean, std, ranking)

**Location:** `evals/`

---

### Phase 7: UI + Advanced Features (Est. 2–3 days, optional)
**Deliverables:**
- [ ] Minimal Streamlit chat UI
- [ ] Form fill/click interaction (Playwright, phase 2+)
- [ ] Results persistence + history
- [ ] Visualization of evaluation metrics

**Location:** `ui/`

---

## TechWithTim Inspiration: Adaptation Table

| Aspect | Original Strength | Limitation | Our Generalization |
|--------|------|-----------|-----|
| Dual assistants | Role separation, memory sharing | Only 2 roles, travel-specific | 6 modular agents, any domain |
| Structured output + schema | Clean parsing, reproducible | Hard-coded TravelSchema | Dynamic JSON schema per query type |
| Conversation memory | Context retrieval | No long-term storage | Hybrid: buffer + Chroma + Redis |
| Background/async tasks | Async feel, polling | In-memory, no persistence | Redis/Celery queue, markdown archive |
| BrightData scraper | Structured data extraction | Paid API, vendor lock-in | Playwright + BeautifulSoup + fallbacks |
| Playwright + browser ops | Form filling, interactions | Google Flights specific | General FormFillerTool, observation-action loop |
| Chroma vector store | Semantic search | Static index | Dynamic per-query + persistent domains |
| Streamlit UI | Quick demo | Domain-locked | CLI first + optional Streamlit later |

---

## CONFIGURATION & LOGGING

### config.yaml (Shared Core)
```yaml
llm:
  url: "http://localhost:8000/v1"
  model: "qwen-3-4b-vl"
  max_tokens: 8000
chunking:
  max_tokens: 1800
  strategy: "heading_based"
fetching:
  max_sites: 8
  stealth_level: 3
memory:
  redis:
    ttl_sec: 2700
  chroma:
    db_path: "./data/chroma"
logging:
  track: [wall_time, rss_delta, tokens_per_step, bot_detection_risk]
```

### JSON Metrics Output
```json
{
  "query": "compare iPhone 16 vs Pixel 9 price",
  "query_type": "product_compare",
  "framework": "langgraph",
  "timestamp": "2026-03-20T14:30:00Z",
  "wall_time_ms": 45000,
  "rss_delta_mb": 120,
  "tokens_total": 6500,
  "tokens_per_step": [200, 450, 1200, 2100, 1500, 1050],
  "bot_detection_risk": 0.15,
  "sites_fetched": 5,
  "chunks_processed": 28,
  "output_tokens": 350
}
```

---

## ONE-COMMAND GOALS

### Run a single query
```bash
python -m agentic_research run \
  --framework langgraph \
  --query "compare iPhone 16 vs Pixel 9 price India"
```

### Evaluate all frameworks
```bash
python -m agentic_research eval \
  --queries evals/gold.jsonl \
  --frameworks langgraph,crewai,autogen \
  --runs 3 \
  --output-dir ./results/
```

---

## DESIRED OUTCOMES (By End of Phase 6)

1. ✅ **Publishable** research paper comparing frameworks
2. ✅ **Reproducible** pipeline (all code open-source, no proprietary APIs)
3. ✅ **Modular** agent roles usable across any domain
4. ✅ **Efficient** (8k token ceiling respected, <60s per query)
5. ✅ **Stealth** (Playwright + headers, detect detection)
6. ✅ **Ranked** multi-site synthesis (tables + pro/con summaries)
7. ✅ **Logged** (metrics collected for benchmarking)
8. ✅ **Generalizable** (3 frameworks compared side-by-side)

---

## FOLDER STRUCTURE (Final)

```
Multi_Agent_Web_Parsser_Proejct/
├── Shared_core/                  ← ONE copy (all frameworks import)
│   ├── config/
│   ├── etl/
│   ├── logger/
│   ├── tools/
│   ├── memory/
│   ├── models/
│   ├── utils/
│   └── pyproject.toml
├── Langraph_Agent/               ← Phase 3
├── CrewAI_Agent/                 ← Phase 4
├── AutoGen_Agent/                ← Phase 5
├── evals/                        ← Phase 6
├── simple_flow/                  ← Phase 2 (optional)
├── Plans/
│   └── LANGGRAPH_IMPLEMENTATION_PLAN.md
└── docs/
    ├── 00_MAIN_PLAN.md          (this file)
    ├── 01_AGENT_IntentExtractor.md
    ├── 02_AGENT_SearchPlanner_Fetcher.md
    └── 03_AGENT_ChunkProcessor_Ranker_Synthesizer.md
```

---

**THIS DOCUMENT IS THE SOURCE OF TRUTH.**  
Refer to it at every decision. Update it as the plan evolves.