# tiktoken wrapper

""""
This file estimates how many tokens a string uses (important for enforcing MAX_TOKENS_PER_CALL = 8000).
"""

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