Step 8, File 2: CrewAI Agent Crew
Concept
CrewAI uses Agent objects (role + goal + backstory) coordinated by a Crew. Each agent has tools bound to it. CrewAI handles task sequencing automatically. Agents are declarative (roles/goals as strings) vs LangGraph's programmatic nodes. Perfect for sequential workflows where Agent 1 outputs data for Agent 2.

Code

# CrewAI_Agent/crew_orchestrator.py
from crewai import Agent, Task, Crew, Process
from crewai_tools import tool
from typing import Any, Dict, List
import asyncio
import json

# Import from Shared_core
import sys
sys.path.insert(0, "../")
from Shared_core.models.intent import IntentSchema
from Shared_core.models.search_plan import SearchPlanSchema
from Shared_core.models.chunk import ChunkSchema
from Shared_core.tools.search import SearchTool
from Shared_core.tools.fetch import URLFetcher
from Shared_core.tools.etl_processor import ETLProcessorTool
from Shared_core.tools.vector_retrieve import VectorRetriever
from Shared_core.tools.rank_compare import RankCompareTool
from Shared_core.logger.structured_logger import StructuredLogger
from Shared_core.config.constants import MAX_CHUNKS_PER_AGENT, DEFAULT_SEARCH_RESULTS


# ============================================================================
# CUSTOM TOOLS (CrewAI-compatible)
# ============================================================================

class CrewAIToolsAdapter:
    """Adapter to wrap Shared_core tools as CrewAI @tool decorators."""
    
    def __init__(self):
        self.logger = StructuredLogger(__name__)
        self.search_tool = SearchTool()
        self.fetcher = URLFetcher()
        self.etl_processor = ETLProcessorTool()
        self.retriever = VectorRetriever()
        self.ranker = RankCompareTool()
    
    @tool("Search Web")
    def search_web(self, query: str, top_k: int = DEFAULT_SEARCH_RESULTS) -> str:
        """Search the web using DuckDuckGo/Bing. Returns JSON of top results."""
        try:
            results = asyncio.run(self.search_tool.search(query, top_k))
            results_list = [
                {
                    "url": sr.url,
                    "title": sr.title,
                    "snippet": sr.snippet,
                    "source": sr.source,
                    "rank": sr.rank
                }
                for sr in results
            ]
            self.logger.log_metric("crewai_search", len(results_list), {"query": query})
            return json.dumps(results_list)
        except Exception as e:
            self.logger.log_metric("crewai_search_error", 1.0, {"error": str(e)})
            return json.dumps({"error": str(e)})
    
    @tool("Fetch URLs")
    def fetch_urls(self, urls: List[str]) -> str:
        """Fetch HTML from multiple URLs. Returns dict of url->html."""
        try:
            fetched = {}
            for url in urls[:5]:  # Limit to 5
                html = asyncio.run(self.fetcher.fetch_url(url, timeout=15))
                if html:
                    fetched[url] = html[:2000]  # First 2000 chars
            self.logger.log_metric("crewai_fetch", len(fetched), {"urls": len(urls)})
            return json.dumps(fetched)
        except Exception as e:
            self.logger.log_metric("crewai_fetch_error", 1.0, {"error": str(e)})
            return json.dumps({"error": str(e)})
    
    @tool("Process ETL")
    def process_etl(self, urls: List[str]) -> str:
        """Run ETL pipeline on URLs. Returns JSON of chunks."""
        try:
            chunks = asyncio.run(self.etl_processor.process_urls_only(urls))
            chunks_json = [
                {
                    "content": c.content[:500],
                    "source_id": c.source_id,
                    "label": c.label,
                    "title": c.title
                }
                for c in chunks
            ]
            self.logger.log_metric("crewai_etl", len(chunks_json), {"urls": len(urls)})
            return json.dumps(chunks_json)
        except Exception as e:
            self.logger.log_metric("crewai_etl_error", 1.0, {"error": str(e)})
            return json.dumps({"error": str(e)})
    
    @tool("Retrieve Vectors")
    def retrieve_vectors(self, query: str, top_k: int = 10) -> str:
        """Retrieve semantically similar chunks from vector DB."""
        try:
            chunks = asyncio.run(self.retriever.retrieve(query, top_k))
            chunks_json = [
                {
                    "content": c.content[:300],
                    "source_id": c.source_id,
                    "title": c.title
                }
                for c in chunks
            ]
            self.logger.log_metric("crewai_retrieve", len(chunks_json), {"query": query})
            return json.dumps(chunks_json)
        except Exception as e:
            self.logger.log_metric("crewai_retrieve_error", 1.0, {"error": str(e)})
            return json.dumps({"error": str(e)})
    
    @tool("Rank Chunks")
    def rank_chunks_tool(self, chunks_json: str, query: str) -> str:
        """Rank and deduplicate chunks. Returns top-ranked."""
        try:
            chunks_list = json.loads(chunks_json)
            # In production, deserialize back to ChunkSchema objects
            # For now, just return top chunks
            top_chunks = chunks_list[:3]
            self.logger.log_metric("crewai_rank", len(top_chunks), {"query": query})
            return json.dumps(top_chunks)
        except Exception as e:
            self.logger.log_metric("crewai_rank_error", 1.0, {"error": str(e)})
            return json.dumps({"error": str(e)})


# ============================================================================
# CREATE CREWAI AGENTS (6 roles)
# ============================================================================

class CrewAIOrchestrator:
    """CrewAI crew with 6 sequential agents."""
    
    def __init__(self):
        self.logger = StructuredLogger(__name__)
        self.tools_adapter = CrewAIToolsAdapter()
        self.crew = self._build_crew()
    
    def _build_crew(self) -> Crew:
        """Build the 6-agent crew."""
        
        # ====================================================================
        # AGENT 1: INTENT EXTRACTOR
        # ====================================================================
        intent_extractor = Agent(
            role="Intent Extractor",
            goal="Parse user query and extract intent type (news/research/tutorial/comparison). "
                 "Identify keywords and preferred domains (e.g., github.com, stackoverflow.com).",
            backstory="You are an expert at understanding user intent. You break down complex queries "
                      "into structured intent schemas. You identify if the user wants latest news, "
                      "tutorials, comparisons, or general research.",
            verbose=True,
            allow_delegation=False
        )
        
        # ====================================================================
        # AGENT 2: SEARCH PLANNER
        # ====================================================================
        search_planner = Agent(
            role="Search Planner",
            goal="Plan search strategy and execute web search using the search_web tool. "
                 "Return top results with URLs, titles, and snippets.",
            backstory="You are a search strategist. Given an intent schema, you decide which "
                      "keywords to use, how many results to fetch, and which APIs to prioritize. "
                      "You use the search_web tool to fetch results.",
            tools=[self.tools_adapter.search_web],
            verbose=True,
            allow_delegation=False
        )
        
        # ====================================================================
        # AGENT 3: MULTI-SITE FETCHER
        # ====================================================================
        multi_site_fetcher = Agent(
            role="Multi-Site Fetcher",
            goal="Fetch HTML from search result URLs using the fetch_urls tool. "
                 "Return clean HTML for each URL.",
            backstory="You are a web scraper expert. You fetch content from URLs while "
                      "handling rate limiting, timeouts, and stealth headers. You use the "
                      "fetch_urls tool to retrieve HTML efficiently.",
            tools=[self.tools_adapter.fetch_urls],
            verbose=True,
            allow_delegation=False
        )
        
        # ====================================================================
        # AGENT 4: CHUNK PROCESSOR (ETL)
        # ====================================================================
        chunk_processor = Agent(
            role="Chunk Processor",
            goal="Run ETL pipeline on fetched HTML using process_etl tool. "
                 "Extract text, transform into semantic chunks, load to vector DB.",
            backstory="You are an ETL specialist. You take raw HTML and transform it into "
                      "semantic chunks respecting token limits (1800 tokens max). You use "
                      "the process_etl tool to orchestrate extraction, transformation, loading.",
            tools=[self.tools_adapter.process_etl],
            verbose=True,
            allow_delegation=False
        )
        
        # ====================================================================
        # AGENT 5: CROSS-SITE RANKER
        # ====================================================================
        cross_site_ranker = Agent(
            role="Cross-Site Ranker",
            goal="Retrieve relevant chunks from vector DB using retrieve_vectors, "
                 "then rank/deduplicate using rank_chunks_tool.",
            backstory="You are a ranking expert. You retrieve semantically similar chunks "
                      "using retrieve_vectors, then apply multi-criteria scoring (semantic, "
                      "authority, keyword match, freshness). You deduplicate >85% similar chunks.",
            tools=[self.tools_adapter.retrieve_vectors, self.tools_adapter.rank_chunks_tool],
            verbose=True,
            allow_delegation=False
        )
        
        # ====================================================================
        # AGENT 6: FINAL SYNTHESIZER
        # ====================================================================
        final_synthesizer = Agent(
            role="Final Synthesizer",
            goal="Create final answer from top-ranked chunks. Cite sources properly.",
            backstory="You are a research synthesizer. You take top-ranked chunks and create "
                      "a comprehensive answer. You cite sources (URL, domain authority, chunk ID). "
                      "You ensure the answer is coherent and directly addresses the original query.",
            verbose=True,
            allow_delegation=False
        )
        
        # ====================================================================
        # DEFINE TASKS (1:1 with agents)
        # ====================================================================
        
        task_intent = Task(
            description="Extract intent from the query: {query}. "
                       "Return intent_type, keywords, preferred_domains.",
            agent=intent_extractor,
            expected_output="IntentSchema as JSON: "
                           "{'intent_type': 'news'|'research'|'tutorial'|'comparison', "
                           "'keywords': [...], 'preferred_domains': [...]}"
        )
        
        task_search = Task(
            description="Search the web for: {query}. Use search_web tool. "
                       "Return top 10 results with URLs, titles, snippets.",
            agent=search_planner,
            expected_output="JSON array of search results: "
                           "[{'url': '...', 'title': '...', 'snippet': '...', 'rank': 1}, ...]",
            context=[task_intent]
        )
        
        task_fetch = Task(
            description="Fetch HTML from these URLs: {urls}. Use fetch_urls tool. "
                       "Return clean HTML for each.",
            agent=multi_site_fetcher,
            expected_output="JSON dict of URL -> HTML: "
                           "{'http://...': '<html>...</html>', ...}",
            context=[task_search]
        )
        
        task_etl = Task(
            description="Process fetched HTML through ETL pipeline. Use process_etl tool. "
                       "Return chunks with content, source, label.",
            agent=chunk_processor,
            expected_output="JSON array of chunks: "
                           "[{'content': '...', 'source_id': 'url', 'label': 'paragraph', ...}, ...]",
            context=[task_fetch]
        )
        
        task_rank = Task(
            description="Retrieve and rank chunks for query: {query}. "
                       "Use retrieve_vectors and rank_chunks_tool. Return top 3.",
            agent=cross_site_ranker,
            expected_output="JSON array of top 3 ranked chunks: "
                           "[{'content': '...', 'source_id': 'url', 'score': 0.95}, ...]",
            context=[task_etl]
        )
        
        task_synthesize = Task(
            description="Create final answer from these top chunks: {ranked_chunks}. "
                       "Cite sources. Answer the original query: {query}",
            agent=final_synthesizer,
            expected_output="Final answer with sources: "
                           "{'answer': '...', 'provenance': [{'source': 'url', 'title': '...'}]}",
            context=[task_rank]
        )
        
        # ====================================================================
        # BUILD CREW (Sequential process)
        # ====================================================================
        crew = Crew(
            agents=[
                intent_extractor,
                search_planner,
                multi_site_fetcher,
                chunk_processor,
                cross_site_ranker,
                final_synthesizer
            ],
            tasks=[
                task_intent,
                task_search,
                task_fetch,
                task_etl,
                task_rank,
                task_synthesize
            ],
            process=Process.sequential,  # Run agents one by one
            verbose=True
        )
        
        return crew
    
    def run(self, query: str) -> Dict[str, Any]:
        """
        Execute the 6-agent crew synchronously.
        """
        self.logger.log_metric("crewai_run_start", 1.0, {"query": query})
        
        try:
            result = self.crew.kickoff(
                inputs={
                    "query": query,
                    "urls": [],  # Will be filled by SearchPlanner
                    "ranked_chunks": []  # Will be filled by Ranker
                }
            )
            
            self.logger.log_metric("crewai_run_success", 1.0, {"query": query})
            
            return {
                "status": "success",
                "final_answer": result.raw if hasattr(result, 'raw') else str(result),
                "query": query
            }
        except Exception as e:
            self.logger.log_metric("crewai_run_error", 1.0, {"error": str(e)})
            return {
                "status": "error",
                "error": str(e),
                "query": query
            }


# ============================================================================
# USAGE
# ============================================================================

if __name__ == "__main__":
    orchestrator = CrewAIOrchestrator()
    result = orchestrator.run("What are the latest AI advancements in 2026?")
    
    print("\n" + "="*80)
    print("CREWAI AGENT RESULT")
    print("="*80)
    print(f"\nStatus: {result['status']}")
    print(f"\nFinal Answer:\n{result.get('final_answer', 'N/A')}")

    Key Concepts
Concept	Description
Agent	CrewAI primitive; has role, goal, backstory, tools, LLM
Task	Unit of work; executed by one agent; has context (dependencies)
Crew	Orchestrates agents+tasks; controls execution process (sequential/hierarchical/async)
@tool	Decorator to wrap functions as CrewAI tools; auto-exposed to agents
Process.sequential	Agents execute one after another; Task N reads context from Task N-1
context=[task_X]	Declares task dependency; output of task_X passed to next task
Declarative Config	Agents defined by strings (role/goal/backstory) vs LangGraph's programmatic nodes
How It Connects
IntentExtractor parses query → outputs intent (role, keywords, domains)
SearchPlanner reads intent → calls search_web() → outputs search results
MultiSiteFetcher reads URLs → calls fetch_urls() → outputs HTML
ChunkProcessor reads HTML → calls process_etl() → outputs chunks
CrossSiteRanker reads chunks → calls retrieve_vectors() + rank_chunks_tool() → outputs top 3
FinalSynthesizer reads ranked chunks → creates final answer with provenance
Key Difference from LangGraph:

LangGraph: Programmatic state machine (explicit node functions)
CrewAI: Declarative agents (roles as strings, LLM auto-selects tools)
CrewAI lets LLM decide when to use each tool vs explicit routing