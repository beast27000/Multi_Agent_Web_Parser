#  Real ETL Transformer (HTML → Chunks)

"""
Phase 2C: Real ETL transformation.
HTML → BeautifulSoup clean → semantic chunks with labels.
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
import re

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

from ..models.chunk import ChunkSchema, ChunkLabel
from ..utils.token_counter import TokenCounter
from ..config.constants import MAX_CHUNK_TOKENS, CHUNK_OVERLAP_TOKENS


@dataclass
class ProcessedChunk:
    """Intermediate chunk before ChunkSchema conversion."""
    content: str
    label: str = "general"
    tokens: int = 0
    confidence: float = 0.8


class RealETLTransformer:
    """Transform HTML to semantic chunks with auto-labeling."""
    
    def __init__(self):
        self.token_counter = TokenCounter()
        self.bs_available = BeautifulSoup is not None
        
        if not self.bs_available:
            print("⚠️  beautifulsoup4 not installed. Run: pip install beautifulsoup4")
    
    async def transform_html(
        self,
        html: str,
        url: str,
        title: str = ""
    ) -> List[ChunkSchema]:
        """
        Transform HTML to chunks.
        
        Args:
            html: Raw HTML content
            url: Source URL
            title: Page title
        
        Returns:
            List of ChunkSchema objects
        """
        if not self.bs_available:
            return self._mock_chunks(url, title)
        
        # Parse HTML
        chunks = []
        try:
            soup = BeautifulSoup(html, "html.parser")
            
            # Remove script/style tags
            for tag in soup(["script", "style"]):
                tag.decompose()
            
            # Extract sections
            sections = self._extract_sections(soup)
            
            # Process each section
            chunk_counter = 0
            for section_text, section_label in sections:
                # Break into sized chunks
                sub_chunks = self._split_into_tokens(section_text, section_label)
                
                for chunk_text, chunk_label in sub_chunks:
                    chunk_counter += 1
                    chunk_id = f"{url}#{chunk_counter}"
                    
                    tokens = self.token_counter.count_tokens(chunk_text)
                    
                    chunk = ChunkSchema(
                        chunk_id=chunk_id,
                        content=chunk_text,
                        label=chunk_label,
                        source_url=url,
                        confidence_score=self._calculate_confidence(chunk_text, chunk_label),
                        timestamp=self._get_timestamp(),
                        token_count=tokens,
                        metadata={
                            "title": title,
                            "section": section_label,
                            "source": "real_etl"
                        }
                    )
                    chunks.append(chunk)
            
            print(f"✓ Processed {len(chunks)} chunks from {url}")
            return chunks
        
        except Exception as e:
            print(f"⚠️  ETL transformation error: {e}")
            return self._mock_chunks(url, title)
    
    def _extract_sections(self, soup) -> List[tuple]:
        """Extract main content sections."""
        sections = []
        
        # Try to find main article/content
        main_content = soup.find("article") or soup.find("main") or soup.find("div", class_="content")
        if not main_content:
            main_content = soup.body or soup
        
        # Extract paragraphs, lists, headings
        for element in main_content.find_all(["h1", "h2", "h3", "p", "li", "div"]):
            text = element.get_text(strip=True)
            
            if not text or len(text) < 10:
                continue
            
            # Auto-label based on content
            label = self._auto_label(text)
            sections.append((text, label))
        
        return sections
    
    def _split_into_tokens(self, text: str, label: str) -> List[tuple]:
        """Split text into token-sized chunks."""
        chunks = []
        tokens = self.token_counter.count_tokens(text)
        
        # If already small enough, return as-is
        if tokens <= MAX_CHUNK_TOKENS:
            return [(text, label)]
        
        # Split by sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        current_chunk = ""
        for sentence in sentences:
            test_chunk = current_chunk + " " + sentence if current_chunk else sentence
            test_tokens = self.token_counter.count_tokens(test_chunk)
            
            if test_tokens > MAX_CHUNK_TOKENS:
                if current_chunk:
                    chunks.append((current_chunk.strip(), label))
                current_chunk = sentence
            else:
                current_chunk = test_chunk
        
        if current_chunk:
            chunks.append((current_chunk.strip(), label))
        
        return chunks
    
    def _auto_label(self, text: str) -> str:
        """Auto-label chunk based on content."""
        text_lower = text.lower()
        
        # Price detection
        if any(word in text_lower for word in ["$", "price", "cost", "₹", "€", "£", "pay", "charge", "fee"]):
            return ChunkLabel.PRICE.value
        
        # Review detection
        if any(word in text_lower for word in ["review", "rating", "star", "feedback", "opinion", "experienced"]):
            return ChunkLabel.REVIEW.value
        
        # Specification detection
        if any(word in text_lower for word in ["spec", "feature", "model", "dimension", "weight", "processor", "memory"]):
            return ChunkLabel.SPECIFICATION.value
        
        # Comparison detection
        if any(word in text_lower for word in ["compare", "vs", "versus", "better", "worse", "advantage", "disadvantage"]):
            return ChunkLabel.COMPARISON.value
        
        # Policy detection
        if any(word in text_lower for word in ["policy", "term", "condition", "rule", "legal", "warranty", "guarantee"]):
            return ChunkLabel.POLICY.value
        
        # News/fact detection
        if any(word in text_lower for word in ["announce", "report", "news", "breaking", "update", "discovered", "research"]):
            return ChunkLabel.NEWS.value
        
        return ChunkLabel.OTHER.value
    
    def _calculate_confidence(self, text: str, label: str) -> float:
        """Calculate confidence score (0-1)."""
        # Base confidence
        confidence = 0.7
        
        # Increase if label is specific
        if label != ChunkLabel.OTHER.value:
            confidence += 0.15
        
        # Bonus for length
        if len(text.split()) > 50:
            confidence = min(confidence + 0.1, 0.99)
        
        return confidence
    
    def _get_timestamp(self) -> str:
        """Get ISO timestamp."""
        from datetime import datetime
        return datetime.utcnow().isoformat()
    
    def _mock_chunks(self, url: str, title: str) -> List[ChunkSchema]:
        """Return mock chunks when BeautifulSoup unavailable."""
        return [
            ChunkSchema(
                chunk_id=f"{url}#1",
                content="Mock chunk 1: This is sample content extracted from the page.",
                label="general",
                source_url=url,
                confidence_score=0.8,
                timestamp=self._get_timestamp(),
                token_count=15,
                metadata={"title": title, "source": "mock"}
            ),
            ChunkSchema(
                chunk_id=f"{url}#2",
                content="Mock chunk 2: Additional information from the page content.",
                label="fact",
                source_url=url,
                confidence_score=0.85,
                timestamp=self._get_timestamp(),
                token_count=14,
                metadata={"title": title, "source": "mock"}
            )
        ]


# Singleton instance
_transformer: Optional[RealETLTransformer] = None

async def get_transformer() -> RealETLTransformer:
    """Get or create transformer."""
    global _transformer
    if _transformer is None:
        _transformer = RealETLTransformer()
    return _transformer
