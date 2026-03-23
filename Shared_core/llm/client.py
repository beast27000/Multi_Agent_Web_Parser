#  LLM Client for Phase 1 Testing

"""
Universal LLM client supporting:
1. OpenAI API (gpt-4-turbo, gpt-3.5-turbo)
2. Local Ollama (Qwen, Mistral)
3. HuggingFace Inference API
"""

import os
import json
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import asyncio
from dotenv import load_dotenv

# Load .env file
load_dotenv()

@dataclass
class LLMResponse:
    """Structured LLM response."""
    content: str
    tokens_used: int
    model: str
    stop_reason: str = "stop"

class UniversalLLMClient:
    """Single client supporting multiple LLM backends."""
    
    def __init__(self, backend: str = "openai", model: str = None):
        """
        Initialize LLM client.
        
        Args:
            backend: "openai", "ollama", "huggingface", "local", or "mock"
            model: Model name (gpt-4, mistral:latest, qwen/qwen3-vl-4b, etc.)
        """
        self.backend = backend or "mock"
        self.model = model or self._get_default_model(backend)
        self.base_url = os.getenv("LLM_BASE_URL", "http://localhost:1234")
        
        if backend == "openai":
            self._init_openai()
        elif backend == "ollama":
            self._init_ollama()
        elif backend == "huggingface":
            self._init_huggingface()
        elif backend == "local":
            self._init_local()
        # "mock" needs no initialization
    
    def _get_default_model(self, backend: str = None) -> str:
        backend = backend or self.backend
        if backend == "openai":
            return "gpt-4-turbo"
        elif backend == "ollama":
            return "mistral:latest"
        elif backend == "huggingface":
            return "meta-llama/Llama-2-7b-chat-hf"
        elif backend == "local":
            return "qwen/qwen3-vl-4b"
        return "mock"
    
    def _init_openai(self):
        """Initialize OpenAI client."""
        try:
            from openai import AsyncOpenAI
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY not set. Falling back to mock.")
            self.client = AsyncOpenAI(api_key=api_key)
        except Exception as e:
            print(f"⚠️  OpenAI init failed: {e}. Using mock backend.")
            self.backend = "mock"
    
    def _init_ollama(self):
        """Initialize Ollama client."""
        try:
            from ollama import AsyncClient
            self.client = AsyncClient(host=os.getenv("OLLAMA_HOST", "http://localhost:11434"))
        except Exception as e:
            print(f"⚠️  Ollama init failed: {e}. Using mock backend.")
            self.backend = "mock"
    
    def _init_huggingface(self):
        """Initialize HuggingFace Inference client."""
        try:
            from huggingface_hub import AsyncInferenceClient
            api_key = os.getenv("HF_API_KEY")
            self.client = AsyncInferenceClient(api_key=api_key)
        except Exception as e:
            print(f"⚠️  HuggingFace init failed: {e}. Using mock backend.")
            self.backend = "mock"
    
    def _init_local(self):
        """Initialize local LM Studio client (Qwen 3 VL via HTTP)."""
        try:
            import httpx
            self.client = httpx.AsyncClient(base_url=self.base_url)
            print(f"✓ Local LM Studio connected at {self.base_url} (model: {self.model})")
        except Exception as e:
            print(f"⚠️  Local LM Studio init failed: {e}. Using mock backend.")
            self.backend = "mock"
    
    async def generate(
        self,
        prompt: str,
        system_prompt: str = None,
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> LLMResponse:
        """
        Generate response from LLM.
        
        Args:
            prompt: User/agent message
            system_prompt: System instructions
            temperature: Creativity (0=deterministic, 1=creative)
            max_tokens: Max output tokens
        
        Returns:
            LLMResponse with content and token count
        """
        if self.backend == "openai":
            return await self._generate_openai(prompt, system_prompt, temperature, max_tokens)
        elif self.backend == "ollama":
            return await self._generate_ollama(prompt, system_prompt, temperature, max_tokens)
        elif self.backend == "huggingface":
            return await self._generate_huggingface(prompt, system_prompt, temperature, max_tokens)
        elif self.backend == "local":
            return await self._generate_local(prompt, system_prompt, temperature, max_tokens)
        else:
            return self._generate_mock(prompt, system_prompt, temperature, max_tokens)
    
    async def _generate_openai(self, prompt: str, system_prompt: str, temp: float, max_tk: int) -> LLMResponse:
        """Call OpenAI API."""
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temp,
                max_tokens=max_tk
            )
            
            content = response.choices[0].message.content
            tokens_used = response.usage.total_tokens
            
            return LLMResponse(
                content=content,
                tokens_used=tokens_used,
                model=self.model,
                stop_reason="stop"
            )
        except Exception as e:
            return LLMResponse(
                content=f"Error calling OpenAI: {str(e)}",
                tokens_used=0,
                model=self.model,
                stop_reason="error"
            )
    
    async def _generate_ollama(self, prompt: str, system_prompt: str, temp: float, max_tk: int) -> LLMResponse:
        """Call local Ollama server."""
        try:
            full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
            
            response = await self.client.generate(
                model=self.model,
                prompt=full_prompt,
                temperature=temp,
                num_predict=max_tk,
                stream=False
            )
            
            content = response.get("response", "")
            tokens_used = response.get("eval_count", 0)
            
            return LLMResponse(
                content=content,
                tokens_used=tokens_used,
                model=self.model,
                stop_reason="stop"
            )
        except Exception as e:
            return LLMResponse(
                content=f"Error calling Ollama: {str(e)}",
                tokens_used=0,
                model=self.model,
                stop_reason="error"
            )
    
    async def _generate_huggingface(self, prompt: str, system_prompt: str, temp: float, max_tk: int) -> LLMResponse:
        """Call HuggingFace Inference API."""
        try:
            full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
            
            response = await self.client.text_generation(
                prompt=full_prompt,
                temperature=temp,
                max_new_tokens=max_tk,
                do_sample=True
            )
            
            return LLMResponse(
                content=response,
                tokens_used=max_tk,  # Approximation
                model=self.model,
                stop_reason="stop"
            )
        except Exception as e:
            return LLMResponse(
                content=f"Error calling HuggingFace: {str(e)}",
                tokens_used=0,
                model=self.model,
                stop_reason="error"
            )
    
    async def _generate_local(self, prompt: str, system_prompt: str, temp: float, max_tk: int) -> LLMResponse:
        """Call local LM Studio server (Qwen 3 VL via HTTP)."""
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            response = await self.client.post(
                "/v1/chat/completions",
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": temp,
                    "max_tokens": max_tk,
                    "stream": False
                }
            )
            
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            tokens_used = result.get("usage", {}).get("total_tokens", len(content.split()))
            
            return LLMResponse(
                content=content,
                tokens_used=tokens_used,
                model=self.model,
                stop_reason="stop"
            )
        except Exception as e:
            return LLMResponse(
                content=f"Error calling Local LM Studio: {str(e)}",
                tokens_used=0,
                model=self.model,
                stop_reason="error"
            )
    
    def _generate_mock(self, prompt: str, system_prompt: str, temp: float, max_tk: int) -> LLMResponse:
        """Mock LLM for testing (synchronous)."""
        # Mock responses based on prompt keywords
        query_lower = (prompt + (system_prompt or "")).lower()
        
        if "intent" in query_lower or "extract" in query_lower:
            content = json.dumps({
                "intent_type": "product_compare",
                "query": "latest AI advancements 2026",
                "keywords": ["AI", "2026", "advancements"],
                "preferred_domains": ["arxiv.org", "github.com", "techcrunch.com"]
            })
        elif "search" in query_lower or "plan" in query_lower:
            content = json.dumps({
                "search_apis": ["duckduckgo", "bing"],
                "num_results": 5,
                "fallback_enabled": True
            })
        elif "rank" in query_lower or "score" in query_lower:
            content = "This result has high relevance based on semantic matching and source authority."
        else:
            content = (
                "This is a mock LLM response. "
                "To get real responses, set OPENAI_API_KEY env var or start Ollama server."
            )
        
        # Ensure content is always a string
        if content is None:
            content = ""
        
        return LLMResponse(
            content=str(content),
            tokens_used=len(str(content).split()),
            model="mock",
            stop_reason="stop"
        )

# Singleton instance
_llm_client: Optional[UniversalLLMClient] = None

async def get_llm_client(backend: str = None, model: str = None) -> UniversalLLMClient:
    """Get or create LLM client."""
    global _llm_client
    
    backend = backend or os.getenv("LLM_API_TYPE") or os.getenv("LLM_BACKEND", "mock")
    model = model or os.getenv("LLM_MODEL")
    
    if _llm_client is None or _llm_client.backend != backend:
        _llm_client = UniversalLLMClient(backend=backend or "mock", model=model)
    
    return _llm_client
