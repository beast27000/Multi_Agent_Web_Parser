# Langraph_Agent/agent_orchestrator.py
from typing import Any, Dict, List, TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command
import json
import asyncio
from dataclasses import dataclass
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Import from Shared_core
from sys import path
path.insert(0, "../")
from Shared_core.models.intent import IntentSchema
from Shared_core.models.search_plan import SearchPlanSchema
from Shared_core.models.chunk import ChunkSchema
from Shared_core.models.ranking import RankingResultSchema
from Shared_core.etl.pipeline import ETLPipeline
from Shared_core.tools.search import SearchTool
from Shared_core.tools.fetch import URLFetcher, FetchToolWithETL
from Shared_core.tools.etl_processor import ETLProcessorTool
from Shared_core.tools.vector_retrieve import VectorRetriever
from Shared_core.tools.rank_compare import RankCompareTool
from Shared_core.logger.structured_logger import StructuredLogger
from Shared_core.memory.redis_manager import RedisManager
from Shared_core.config.constants import (
    MAX_CHUNKS_PER_AGENT, 
    DOMAIN_AUTHORITY, 
    DEFAULT_SEARCH_RESULTS
)


# ============================================================================
# STATE SCHEMA
# ============================================================================

class AgentState(TypedDict):
    """
    Unified state that flows through all 6 agent roles.
    Each agent reads from state, processes, and updates it.
    """
    # User input
    query: str
    
    # Output from IntentExtractor
    intent: IntentSchema | None
    
    # Output from SearchPlanner
    search_plan: SearchPlanSchema | None
    search_results: List[Dict[str, Any]]  # URLs, titles, snippets
    
    # Output from MultiSiteFetcher
    fetched_html: Dict[str, str]  # {url: html}
    fetch_errors: Dict[str, str]  # {url: error_msg}
    
    # Output from ChunkProcessor
    chunks: List[ChunkSchema]
    chunk_count: int
    
    # Output from CrossSiteRanker
    ranked_chunks: List[tuple]  # [(chunk, score), ...]
    deduped_chunks: List[ChunkSchema]
    
    # Output from FinalSynthesizer
    final_answer: str
    provenance: List[Dict[str, Any]]  # source, domain, authority, chunk_id
    
    # Metadata
    agent_logs: List[str]
    error_log: List[str]


# ============================================================================
# AGENT 1: INTENT EXTRACTOR
# ============================================================================

async def agent_intent_extractor(state: AgentState) -> Command:
    """
    Role: Parse query, extract intent type, identify search keywords, domain filters.
    Input: raw query string
    Output: IntentSchema with intent_type, keywords, preferred_domains
    """
    logger = StructuredLogger(__name__)
    query = state["query"]
    
    try:
        # Simple heuristic-based intent extraction (can be LLM-based for production)
        keywords = query.lower().split()
        
        # Detect intent type
        intent_type = "research"  # default
        if any(word in query.lower() for word in ["latest", "news", "recent", "trending"]):
            intent_type = "news"
        elif any(word in query.lower() for word in ["how", "tutorial", "guide", "learn"]):
            intent_type = "tutorial"
        elif any(word in query.lower() for word in ["compare", "vs", "difference", "better"]):
            intent_type = "comparison"
        
        # Extract domain preferences
        preferred_domains = []
        if "github" in query.lower():
            preferred_domains.append("github.com")
        if "stackoverflow" in query.lower():
            preferred_domains.append("stackoverflow.com")
        
        intent = IntentSchema(
            query=query,
            intent_type=intent_type,
            keywords=keywords,
            preferred_domains=preferred_domains or None,
            created_at="now"
        )
        
        log_msg = f"[IntentExtractor] Parsed query '{query[:50]}...' as {intent_type}"
        logger.log_metric("intent_extraction", 1.0, {"intent_type": intent_type})
        
        return Command(update={
            "intent": intent,
            "agent_logs": state["agent_logs"] + [log_msg]
        }, goto="search_planner")
        
    except Exception as e:
        error_msg = f"[IntentExtractor] Error: {str(e)}"
        logger.log_metric("intent_extraction_error", 1.0, {"error": str(e)})
        return Command(update={
            "error_log": state["error_log"] + [error_msg]
        }, goto=END)


# ============================================================================
# AGENT 2: SEARCH PLANNER
# ============================================================================

async def agent_search_planner(state: AgentState) -> Command:
    """
    Role: Plan search strategy — decide which APIs to hit (DuckDuckGo/Bing), 
           number of results, focus areas.
    Input: IntentSchema
    Output: SearchPlanSchema, search_results
    """
    logger = StructuredLogger(__name__)
    intent = state["intent"]
    
    if not intent:
        return Command(update={
            "error_log": state["error_log"] + ["[SearchPlanner] No intent provided"]
        }, goto=END)
    
    try:
        # Create search plan
        search_plan = SearchPlanSchema(
            intent_type=intent.intent_type,
            search_apis=["duckduckgo", "bing"],  # Try both
            num_results=DEFAULT_SEARCH_RESULTS,  # 10
            keywords=intent.keywords,
            preferred_domains=intent.preferred_domains,
            target_sources=None
        )
        
        # Execute search
        search_tool = SearchTool()
        search_results = asyncio.run(search_tool.search(
            query=intent.query,
            top_k=search_plan.num_results
        ))
        
        results_list = [
            {
                "url": sr.url,
                "title": sr.title,
                "snippet": sr.snippet,
                "source": sr.source,
                "rank": sr.rank
            }
            for sr in search_results
        ]
        
        log_msg = f"[SearchPlanner] Found {len(results_list)} results for '{intent.query[:30]}...'"
        logger.log_metric("search_plan_execution", len(results_list), {"query": intent.query})
        
        return Command(update={
            "search_plan": search_plan,
            "search_results": results_list,
            "agent_logs": state["agent_logs"] + [log_msg]
        }, goto="fetcher")
        
    except Exception as e:
        error_msg = f"[SearchPlanner] Error: {str(e)}"
        logger.log_metric("search_plan_error", 1.0, {"error": str(e)})
        return Command(update={
            "error_log": state["error_log"] + [error_msg]
        }, goto=END)


# ============================================================================
# AGENT 3: MULTI-SITE FETCHER
# ============================================================================

async def agent_multi_site_fetcher(state: AgentState) -> Command:
    """
    Role: Fetch URLs from search results using Playwright + stealth headers.
    Input: search_results (list of URLs)
    Output: fetched_html (dict of url -> html), fetch_errors
    """
    logger = StructuredLogger(__name__)
    search_results = state["search_results"]
    
    if not search_results:
        return Command(update={
            "error_log": state["error_log"] + ["[MultiSiteFetcher] No search results"]
        }, goto=END)
    
    try:
        # Extract URLs
        urls = [sr["url"] for sr in search_results[:5]]  # Top 5 to avoid overload
        
        # Fetch all URLs with rate limiting
        fetcher = URLFetcher()
        fetched_html = {}
        fetch_errors = {}
        
        for url in urls:
            try:
                html = asyncio.run(fetcher.fetch_url(url, timeout=15))
                if html:
                    fetched_html[url] = html
                else:
                    fetch_errors[url] = "Empty response"
            except Exception as e:
                fetch_errors[url] = str(e)
        
        log_msg = f"[MultiSiteFetcher] Fetched {len(fetched_html)}/{len(urls)} URLs"
        logger.log_metric("multi_site_fetch", len(fetched_html), {"total_urls": len(urls)})
        
        return Command(update={
            "fetched_html": fetched_html,
            "fetch_errors": fetch_errors,
            "agent_logs": state["agent_logs"] + [log_msg]
        }, goto="processor")
        
    except Exception as e:
        error_msg = f"[MultiSiteFetcher] Error: {str(e)}"
        logger.log_metric("multi_site_fetch_error", 1.0, {"error": str(e)})
        return Command(update={
            "error_log": state["error_log"] + [error_msg]
        }, goto=END)


# ============================================================================
# AGENT 4: CHUNK PROCESSOR (ETL)
# ============================================================================

async def agent_chunk_processor(state: AgentState) -> Command:
    """
    Role: Run full ETL pipeline on fetched HTML.
    Input: fetched_html
    Output: chunks (list of ChunkSchema), chunk_count
    """
    logger = StructuredLogger(__name__)
    fetched_html = state["fetched_html"]
    intent = state["intent"]
    
    if not fetched_html:
        return Command(update={
            "chunks": [],
            "chunk_count": 0,
            "agent_logs": state["agent_logs"] + ["[ChunkProcessor] No HTML to process"]
        }, goto="ranker")
    
    try:
        etl_processor = ETLProcessorTool()
        all_chunks = []
        
        # Process each URL's HTML through ETL
        for url, html in fetched_html.items():
            try:
                # Use process_urls_only with pre-fetched HTML
                # (In production, might use a custom ETL method)
                chunks = []  # Placeholder; would extract, transform, load
                
                # Simple extraction simulation
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "html.parser")
                text = soup.get_text(separator=" ", strip=True)
                
                # Create raw chunk
                chunk = ChunkSchema(
                    content=text[:1000],  # First 1000 chars
                    source_id=url,
                    chunk_id=f"{url}#0",
                    label="raw_extraction",
                    tokens=100,  # estimated
                    extracted_at="now",
                    url=url,
                    title=soup.title.string if soup.title else url
                )
                all_chunks.append(chunk)
            except Exception as e:
                logger.log_metric("chunk_process_url_error", 1.0, {"url": url, "error": str(e)})
        
        log_msg = f"[ChunkProcessor] Processed {len(all_chunks)} chunks from {len(fetched_html)} URLs"
        logger.log_metric("chunk_processing", len(all_chunks), {"input_urls": len(fetched_html)})
        
        return Command(update={
            "chunks": all_chunks,
            "chunk_count": len(all_chunks),
            "agent_logs": state["agent_logs"] + [log_msg]
        }, goto="ranker")
        
    except Exception as e:
        error_msg = f"[ChunkProcessor] Error: {str(e)}"
        logger.log_metric("chunk_processing_error", 1.0, {"error": str(e)})
        return Command(update={
            "error_log": state["error_log"] + [error_msg]
        }, goto=END)


# ============================================================================
# AGENT 5: CROSS-SITE RANKER
# ============================================================================

async def agent_cross_site_ranker(state: AgentState) -> Command:
    """
    Role: Rank/deduplicate chunks using multi-criteria scoring.
    Input: chunks
    Output: ranked_chunks, deduped_chunks
    """
    logger = StructuredLogger(__name__)
    chunks = state["chunks"]
    intent = state["intent"]
    
    if not chunks:
        return Command(update={
            "ranked_chunks": [],
            "deduped_chunks": [],
            "agent_logs": state["agent_logs"] + ["[CrossSiteRanker] No chunks to rank"]
        }, goto="synthesizer")
    
    try:
        ranker = RankCompareTool()
        
        # Score all chunks
        ranked = []
        for chunk in chunks:
            score = ranker.score_chunk(
                chunk=chunk,
                query=intent.query,
                strategy="weighted"  # 40% semantic, 25% authority, etc.
            )
            ranked.append((chunk, score))
        
        # Sort by score descending
        ranked.sort(key=lambda x: x[1], reverse=True)
        
        # Deduplicate (>85% similarity)
        deduped = ranker.deduplicate_chunks(chunks, threshold=0.85)
        
        log_msg = f"[CrossSiteRanker] Ranked {len(ranked)} chunks, deduped to {len(deduped)}"
        logger.log_metric("ranking", len(ranked), {"deduped": len(deduped)})
        
        return Command(update={
            "ranked_chunks": ranked[:MAX_CHUNKS_PER_AGENT],  # Top N
            "deduped_chunks": deduped,
            "agent_logs": state["agent_logs"] + [log_msg]
        }, goto="synthesizer")
        
    except Exception as e:
        error_msg = f"[CrossSiteRanker] Error: {str(e)}"
        logger.log_metric("ranking_error", 1.0, {"error": str(e)})
        return Command(update={
            "error_log": state["error_log"] + [error_msg]
        }, goto=END)


# ============================================================================
# AGENT 6: FINAL SYNTHESIZER
# ============================================================================

async def agent_final_synthesizer(state: AgentState) -> Command:
    """
    Role: Create final answer from top chunks; cite sources.
    Input: ranked_chunks (top chunk+score pairs), intent
    Output: final_answer, provenance
    """
    logger = StructuredLogger(__name__)
    ranked_chunks = state["ranked_chunks"]
    intent = state["intent"]
    
    if not ranked_chunks:
        return Command(update={
            "final_answer": "No relevant information found.",
            "provenance": []
        }, goto=END)
    
    try:
        # Build answer from top chunks
        top_chunks = [chunk for chunk, score in ranked_chunks[:3]]  # Top 3
        
        answer_parts = [f"Query: {intent.query}\n"]
        provenance = []
        
        for i, chunk in enumerate(top_chunks, 1):
            # Simulate LLM synthesis (in production, call LLM here)
            answer_parts.append(f"\n[Source {i}] {chunk.title or chunk.source_id}\n")
            answer_parts.append(f"{chunk.content[:500]}...\n")
            
            provenance.append({
                "chunk_id": chunk.chunk_id,
                "source": chunk.source_id,
                "title": chunk.title,
                "label": chunk.label,
                "url": chunk.url
            })
        
        final_answer = "".join(answer_parts)
        
        log_msg = f"[FinalSynthesizer] Generated answer with {len(provenance)} sources"
        logger.log_metric("synthesis", len(provenance), {"top_chunks": len(top_chunks)})
        
        return Command(update={
            "final_answer": final_answer,
            "provenance": provenance,
            "agent_logs": state["agent_logs"] + [log_msg]
        }, goto=END)
        
    except Exception as e:
        error_msg = f"[FinalSynthesizer] Error: {str(e)}"
        logger.log_metric("synthesis_error", 1.0, {"error": str(e)})
        return Command(update={
            "error_log": state["error_log"] + [error_msg]
        }, goto=END)


# ============================================================================
# LANGGRAPH ORCHESTRATOR
# ============================================================================

class LangGraphOrchestrator:
    """
    LangGraph state machine with 6 agent nodes.
    Flows: START → IntentExtractor → SearchPlanner → MultiSiteFetcher → 
           ChunkProcessor → CrossSiteRanker → FinalSynthesizer → END
    """
    
    def __init__(self):
        self.graph = self._build_graph()
        self.logger = StructuredLogger(__name__)
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state graph with all 6 agents."""
        graph = StateGraph(AgentState)
        
        # Add nodes
        graph.add_node("intent_extractor", agent_intent_extractor)
        graph.add_node("search_planner", agent_search_planner)
        graph.add_node("fetcher", agent_multi_site_fetcher)
        graph.add_node("processor", agent_chunk_processor)
        graph.add_node("ranker", agent_cross_site_ranker)
        graph.add_node("synthesizer", agent_final_synthesizer)
        
        # Add edges
        graph.add_edge(START, "intent_extractor")
        graph.add_edge("intent_extractor", "search_planner")
        graph.add_edge("search_planner", "fetcher")
        graph.add_edge("fetcher", "processor")
        graph.add_edge("processor", "ranker")
        graph.add_edge("ranker", "synthesizer")
        graph.add_edge("synthesizer", END)
        
        return graph.compile()
    
    async def run(self, query: str) -> Dict[str, Any]:
        """
        Execute the 6-agent pipeline synchronously.
        """
        initial_state = AgentState(
            query=query,
            intent=None,
            search_plan=None,
            search_results=[],
            fetched_html={},
            fetch_errors={},
            chunks=[],
            chunk_count=0,
            ranked_chunks=[],
            deduped_chunks=[],
            final_answer="",
            provenance=[],
            agent_logs=[],
            error_log=[]
        )
        
        # Stream events
        result = None
        async for event in self.graph.astream(initial_state):
            print(f"Event: {list(event.keys())}")
            if event and isinstance(event, dict):
                result = list(event.values())[0] if event else None
        
        self.logger.log_metric("orchestrator_run", 1.0)
        return result or initial_state
    
    def run_sync(self, query: str) -> Dict[str, Any]:
        """Synchronous wrapper."""
        return asyncio.run(self.run(query))


# ============================================================================
# USAGE
# ============================================================================

if __name__ == "__main__":
    orchestrator = LangGraphOrchestrator()
    result = orchestrator.run_sync("What are the latest AI advancements in 2026?")
    
    print("\n" + "="*80)
    print("LANGGRAPH AGENT RESULT")
    print("="*80)
    print(f"\nFinal Answer:\n{result.get('final_answer', 'N/A')}")
    print(f"\nProvenance: {len(result.get('provenance', []))} sources")
    print(f"\nAgent Logs:")
    for log in result.get('agent_logs', []):
        print(f"  {log}")