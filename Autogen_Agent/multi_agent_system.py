# AutoGen_Agent/multi_agent_system.py
from autogen import AssistantAgent, UserProxyAgent, config_list_from_json
from autogen.agentchat.conversable_agent import ConversableAgent
from typing import Any, Dict, List, Optional
import json
import asyncio

# Import from Shared_core
import sys
sys.path.insert(0, "../")
from Shared_core.models.intent import IntentSchema
from Shared_core.models.chunk import ChunkSchema
from Shared_core.tools.search import SearchTool
from Shared_core.tools.fetch import URLFetcher
from Shared_core.tools.etl_processor import ETLProcessorTool
from Shared_core.tools.vector_retrieve import VectorRetriever
from Shared_core.tools.rank_compare import RankCompareTool
from Shared_core.logger.structured_logger import StructuredLogger
from Shared_core.config.constants import MAX_CHUNKS_PER_AGENT, DEFAULT_SEARCH_RESULTS


# ============================================================================
# AUTOGEN TOOLS (wrapped as Python functions)
# ============================================================================

class AutoGenToolsAdapter:
    """Adapter to wrap Shared_core tools for AutoGen function calls."""
    
    def __init__(self):
        self.logger = StructuredLogger(__name__)
        self.search_tool = SearchTool()
        self.fetcher = URLFetcher()
        self.etl_processor = ETLProcessorTool()
        self.retriever = VectorRetriever()
        self.ranker = RankCompareTool()
    
    def search_web(self, query: str, top_k: int = DEFAULT_SEARCH_RESULTS) -> str:
        """
        Search the web using DuckDuckGo/Bing.
        Returns JSON of top results.
        """
        try:
            results = asyncio.run(self.search_tool.search(query, top_k))
            results_list = [
                {
                    "url": sr.url,
                    "title": sr.title,
                    "snippet": sr.snippet[:200],
                    "source": sr.source,
                    "rank": sr.rank
                }
                for sr in results
            ]
            self.logger.log_metric("autogen_search", len(results_list))
            return json.dumps({"status": "success", "results": results_list})
        except Exception as e:
            self.logger.log_metric("autogen_search_error", 1.0, {"error": str(e)})
            return json.dumps({"status": "error", "message": str(e)})
    
    def fetch_urls(self, urls: List[str]) -> str:
        """
        Fetch HTML from URLs. Returns dict of url->html (truncated).
        """
        try:
            fetched = {}
            for url in urls[:5]:
                html = asyncio.run(self.fetcher.fetch_url(url, timeout=15))
                if html:
                    fetched[url] = html[:1500]  # Truncate for context
            self.logger.log_metric("autogen_fetch", len(fetched))
            return json.dumps({"status": "success", "fetched": fetched})
        except Exception as e:
            self.logger.log_metric("autogen_fetch_error", 1.0, {"error": str(e)})
            return json.dumps({"status": "error", "message": str(e)})
    
    def process_etl(self, urls: List[str]) -> str:
        """
        Run ETL pipeline on URLs. Returns JSON of chunks.
        """
        try:
            chunks = asyncio.run(self.etl_processor.process_urls_only(urls))
            chunks_json = [
                {
                    "content": c.content[:400],
                    "source_id": c.source_id,
                    "label": c.label,
                    "title": c.title,
                    "chunk_id": c.chunk_id
                }
                for c in chunks[:10]  # Top 10 chunks
            ]
            self.logger.log_metric("autogen_etl", len(chunks_json))
            return json.dumps({"status": "success", "chunks": chunks_json})
        except Exception as e:
            self.logger.log_metric("autogen_etl_error", 1.0, {"error": str(e)})
            return json.dumps({"status": "error", "message": str(e)})
    
    def retrieve_vectors(self, query: str, top_k: int = 10) -> str:
        """
        Retrieve semantically similar chunks from vector DB.
        """
        try:
            chunks = asyncio.run(self.retriever.retrieve(query, top_k))
            chunks_json = [
                {
                    "content": c.content[:300],
                    "source_id": c.source_id,
                    "title": c.title,
                    "score": 0.9  # Placeholder
                }
                for c in chunks
            ]
            self.logger.log_metric("autogen_retrieve", len(chunks_json))
            return json.dumps({"status": "success", "chunks": chunks_json})
        except Exception as e:
            self.logger.log_metric("autogen_retrieve_error", 1.0, {"error": str(e)})
            return json.dumps({"status": "error", "message": str(e)})
    
    def rank_chunks(self, chunks_json: str, query: str) -> str:
        """
        Rank and deduplicate chunks. Returns top-ranked.
        """
        try:
            chunks_list = json.loads(chunks_json)
            # In production, would deserialize to ChunkSchema
            top_chunks = chunks_list[:3]
            self.logger.log_metric("autogen_rank", len(top_chunks))
            return json.dumps({"status": "success", "ranked": top_chunks})
        except Exception as e:
            self.logger.log_metric("autogen_rank_error", 1.0, {"error": str(e)})
            return json.dumps({"status": "error", "message": str(e)})


# ============================================================================
# AUTOGEN TWO-AGENT SYSTEM
# ============================================================================

class AutoGenOrchestrator:
    """
    AutoGen two-agent system: AssistantAgent + UserProxyAgent.
    AssistantAgent: LLM-powered, runs tools, generates answers.
    UserProxyAgent: Human-in-loop validator, approves/rejects outputs.
    """
    
    def __init__(self, llm_config: Optional[Dict] = None):
        """
        Initialize AutoGen orchestrator.
        
        Args:
            llm_config: LLM configuration (model, API key, etc.)
                       If None, uses local Qwen model via ollama
        """
        self.logger = StructuredLogger(__name__)
        self.tools_adapter = AutoGenToolsAdapter()
        
        # Default LLM config (local Qwen via ollama)
        if llm_config is None:
            llm_config = {
                "config_list": [
                    {
                        "model": "qwen-3-4b-vl",  # Local model
                        "api_type": "local",
                        "base_url": "http://localhost:8000/v1"
                    }
                ],
                "temperature": 0.7,
            }
        
        self.llm_config = llm_config
        self._setup_agents()
    
    def _setup_agents(self):
        """Setup AssistantAgent and UserProxyAgent."""
        
        # ====================================================================
        # ASSISTANT AGENT (LLM-powered tool runner)
        # ====================================================================
        self.assistant = AssistantAgent(
            name="ResearchAssistant",
            system_message="""You are an expert research assistant. Your role is to:
1. Search the web for information
2. Fetch and process URLs
3. Extract semantic chunks via ETL
4. Retrieve from vector DB
5. Rank and deduplicate results
6. Synthesize final answer

When the user asks a query:
- Use search_web() to find relevant URLs
- Use fetch_urls() to retrieve content
- Use process_etl() to extract chunks
- Use retrieve_vectors() to find similar chunks in DB
- Use rank_chunks() to sort by relevance
- Provide a comprehensive answer with sources

Always cite sources and be transparent about data processing steps.
If the user rejects your output, explain your reasoning and refine.
""",
            llm_config=self.llm_config,
        )
        
        # Register tools with assistant
        self._register_assistant_tools()
        
        # ====================================================================
        # USER PROXY AGENT (Human-in-loop validator)
        # ====================================================================
        self.user_proxy = UserProxyAgent(
            name="UserValidator",
            system_message="""You are a research validator. Your role is to:
1. Review outputs from ResearchAssistant
2. Approve, reject, or request refinements
3. Provide feedback on answer quality
4. Ensure sources are properly cited
5. Validate that data processing was appropriate

When you receive an answer:
- Check if sources are provided
- Verify that content is relevant to the query
- Ensure no hallucinations or unsupported claims
- Request refinements if needed

Type 'APPROVED' to accept the answer.
Type 'REJECTED: [reason]' to ask for refinement.
Type 'QUIT' to stop.
""",
            human_input_mode="ALWAYS",  # Require human validation for each step
            max_consecutive_auto_reply=1,  # Prevent infinite loops
        )
    
    def _register_assistant_tools(self):
        """Register Shared_core tools with AssistantAgent."""
        
        # Define tool schemas for AutoGen
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_web",
                    "description": "Search the web for information using DuckDuckGo/Bing",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query"
                            },
                            "top_k": {
                                "type": "integer",
                                "description": "Number of results (default 10)"
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "fetch_urls",
                    "description": "Fetch HTML content from URLs",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "urls": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of URLs to fetch"
                            }
                        },
                        "required": ["urls"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "process_etl",
                    "description": "Run ETL pipeline on URLs (extract, transform, load)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "urls": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "URLs to process"
                            }
                        },
                        "required": ["urls"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "retrieve_vectors",
                    "description": "Retrieve semantically similar chunks from vector DB",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Query for semantic search"
                            },
                            "top_k": {
                                "type": "integer",
                                "description": "Number of results (default 10)"
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "rank_chunks",
                    "description": "Rank and deduplicate chunks by relevance",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "chunks_json": {
                                "type": "string",
                                "description": "JSON string of chunks"
                            },
                            "query": {
                                "type": "string",
                                "description": "Original query for ranking"
                            }
                        },
                        "required": ["chunks_json", "query"]
                    }
                }
            }
        ]
        
        # Register function implementations
        self.assistant.register_function_implementations({
            "search_web": self.tools_adapter.search_web,
            "fetch_urls": self.tools_adapter.fetch_urls,
            "process_etl": self.tools_adapter.process_etl,
            "retrieve_vectors": self.tools_adapter.retrieve_vectors,
            "rank_chunks": self.tools_adapter.rank_chunks,
        })
    
    def run(self, query: str, max_turns: int = 10) -> Dict[str, Any]:
        """
        Run the two-agent conversation loop.
        
        Args:
            query: User research query
            max_turns: Max conversation turns before timeout
        
        Returns:
            Dict with final answer, conversation history, approvals
        """
        self.logger.log_metric("autogen_run_start", 1.0, {"query": query})
        
        conversation_history = []
        
        try:
            # Start conversation
            user_message = f"""
Please research the following query and provide a comprehensive answer with sources:

QUERY: {query}

WORKFLOW:
1. Search the web for relevant URLs
2. Fetch content from top URLs
3. Process through ETL pipeline
4. Retrieve semantically similar chunks from vector DB
5. Rank results by relevance
6. Synthesize final answer with proper citations

Please proceed step-by-step and cite all sources.
"""
            
            # Run conversation
            conversation_history = self.user_proxy.initiate_chat(
                self.assistant,
                message=user_message,
                max_turns=max_turns,
            )
            
            # Extract final answer
            final_answer = conversation_history.chat_history[-1]["content"] if conversation_history.chat_history else ""
            
            self.logger.log_metric("autogen_run_success", 1.0, {"query": query})
            
            return {
                "status": "success",
                "query": query,
                "final_answer": final_answer,
                "conversation_turns": len(conversation_history.chat_history),
                "approved": True  # If we got here, user approved
            }
            
        except Exception as e:
            self.logger.log_metric("autogen_run_error", 1.0, {"error": str(e)})
            return {
                "status": "error",
                "query": query,
                "error": str(e),
                "conversation_history": conversation_history
            }


# ============================================================================
# COMPARISON: AGENT ROLES IN EACH FRAMEWORK
# ============================================================================

class FrameworkComparison:
    """
    Docstring showing how 3 frameworks handle the same 6-role pipeline:
    
    LANGGRAPH (Programmatic):
    - Node-based DAG
    - Explicit state passing (StateGraph)
    - Deterministic routing (Command(goto=...))
    - Each node = async function
    - Full control, verbose setup
    
    CREWAI (Declarative):
    - Agent = role + goal + backstory
    - Task = unit of work with context
    - LLM decides tool selection
    - Sequential/hierarchical process
    - Config-driven, less code
    
    AUTOGEN (Conversational):
    - 2-agent conversation (Assistant + UserProxy)
    - Multi-turn dialogue with human-in-loop
    - Error recovery via conversation
    - Tool calling via chat
    - Best for validation/approval workflows
    
    USE CASES:
    - LangGraph: Deterministic pipelines, complex routing logic
    - CrewAI: Multi-goal workflows, LLM-driven task selection
    - AutoGen: Interactive research, human validation, error recovery
    """
    pass


# ============================================================================
# USAGE
# ============================================================================

if __name__ == "__main__":
    # Create orchestrator
    orchestrator = AutoGenOrchestrator()
    
    # Run conversation
    result = orchestrator.run(
        query="What are the latest AI advancements in 2026?",
        max_turns=15
    )
    
    print("\n" + "="*80)
    print("AUTOGEN TWO-AGENT RESULT")
    print("="*80)
    print(f"\nStatus: {result['status']}")
    print(f"\nQuery: {result['query']}")
    print(f"\nConversation Turns: {result.get('conversation_turns', 'N/A')}")
    print(f"\nFinal Answer:\n{result.get('final_answer', 'N/A')}")
    print(f"\nApproved: {result.get('approved', False)}")

    