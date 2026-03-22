# BeautifulSoup cleaning + chunking

"""
The Concept
The Transformer takes raw extracted text and splits it into semantic chunks. Unlike generic splitting, the Transformer is smart:

Respects token limits (max 1,800 tokens per chunk from constants)
Preserves semantics (splits at paragraph/heading boundaries, not mid-sentence)
Maintains context (sliding window overlap so no information is orphaned)
Detects content type (heading, paragraph, code, table)
Assigns labels (HEADING, PARAGRAPH, CODE_BLOCK, TABLE_DATA)
Think of it as: "Take raw text, break it into meaningful pieces, each piece ≤ 1,800 tokens, label them, keep context."
"""

# Shared_core/etl/transformer.py

import re
from typing import List, Dict, Optional
from ..models.chunk import ChunkSchema, ChunkLabel
from ..utils.token_counter import TokenCounter
from ..config.constants import MAX_CHUNK_TOKENS, CHUNK_OVERLAP_TOKENS
from datetime import datetime


class TextTransformer:
    """Transform raw extracted text into semantic chunks."""
    
    # Content type detection patterns
    CODE_BLOCK_PATTERN = re.compile(r'```|```\w+|^    \S|^`{1,2}\w+`')
    TABLE_PATTERN = re.compile(r'\[TABLE\]|\|.*\|.*\|')
    HEADING_PATTERN = re.compile(r'^#{1,6}\s+\S')
    
    def __init__(self):
        """Initialize with token counter."""
        self.token_counter = TokenCounter()
    
    @staticmethod
    def detect_content_type(text: str) -> ChunkLabel:
        """Detect content type from text patterns."""
        text_sample = text[:200]  # First 200 chars
        
        if TextTransformer.HEADING_PATTERN.search(text_sample):
            return ChunkLabel.HEADING
        elif TextTransformer.CODE_BLOCK_PATTERN.search(text_sample):
            return ChunkLabel.CODE_BLOCK
        elif TextTransformer.TABLE_PATTERN.search(text_sample):
            return ChunkLabel.TABLE_DATA
        else:
            return ChunkLabel.PARAGRAPH
    
    @staticmethod
    def split_by_boundaries(text: str) -> List[str]:
        """Split text by semantic boundaries (paragraphs, headings)."""
        # Split by double newline first (paragraphs)
        paragraphs = text.split('\n\n')
        
        # For each paragraph, further split by headings
        segments = []
        for para in paragraphs:
            if TextTransformer.HEADING_PATTERN.search(para):
                # This is a heading, keep it separate
                segments.append(para)
            elif para.strip():  # Non-empty
                segments.append(para)
        
        return [s for s in segments if s.strip()]
    
    def transform_to_chunks(
        self,
        raw_chunk: ChunkSchema,
        url: str,
        source_id: str
    ) -> List[ChunkSchema]:
        """
        Transform a raw extracted chunk into semantic chunks.
        
        Args:
            raw_chunk: ChunkSchema with label=RAW_EXTRACTION and full content
            url: Source URL (inherited from raw chunk)
            source_id: Source identifier (inherited from raw chunk)
        
        Returns:
            List of ChunkSchema objects, each ≤ MAX_CHUNK_TOKENS
        """
        # Start with the raw text
        text = raw_chunk.content
        segments = self.split_by_boundaries(text)
        
        chunks: List[ChunkSchema] = []
        current_buffer = ""
        buffer_tokens = 0
        overlap_buffer = ""  # For context preservation
        
        for segment in segments:
            segment_tokens = self.token_counter.count_tokens(segment)
            
            # If segment alone exceeds MAX_CHUNK_TOKENS, split it further
            if segment_tokens > MAX_CHUNK_TOKENS:
                # Flush current buffer first
                if current_buffer.strip():
                    chunk = self._create_chunk(
                        content=current_buffer.strip(),
                        url=url,
                        source_id=source_id,
                        raw_chunk=raw_chunk
                    )
                    chunks.append(chunk)
                    overlap_buffer = current_buffer[-CHUNK_OVERLAP_TOKENS:]
                    current_buffer = ""
                    buffer_tokens = 0
                
                # Split oversized segment by words/sentences
                subsegments = self._split_oversized_segment(segment)
                for subseg in subsegments:
                    subseg_tokens = self.token_counter.count_tokens(subseg)
                    if subseg_tokens <= MAX_CHUNK_TOKENS:
                        chunk = self._create_chunk(
                            content=subseg.strip(),
                            url=url,
                            source_id=source_id,
                            raw_chunk=raw_chunk
                        )
                        chunks.append(chunk)
            
            # Try to add segment to current buffer
            elif buffer_tokens + segment_tokens <= MAX_CHUNK_TOKENS:
                current_buffer += f"\n{segment}"
                buffer_tokens += segment_tokens
            
            else:
                # Buffer is full, flush it and start new one
                if current_buffer.strip():
                    chunk = self._create_chunk(
                        content=current_buffer.strip(),
                        url=url,
                        source_id=source_id,
                        raw_chunk=raw_chunk
                    )
                    chunks.append(chunk)
                    overlap_buffer = current_buffer[-CHUNK_OVERLAP_TOKENS:]
                
                # Start new buffer with overlap + current segment
                current_buffer = overlap_buffer + f"\n{segment}"
                buffer_tokens = self.token_counter.count_tokens(current_buffer)
        
        # Flush final buffer
        if current_buffer.strip():
            chunk = self._create_chunk(
                content=current_buffer.strip(),
                url=url,
                source_id=source_id,
                raw_chunk=raw_chunk
            )
            chunks.append(chunk)
        
        return chunks
    
    def _split_oversized_segment(self, text: str, max_tokens: int = MAX_CHUNK_TOKENS) -> List[str]:
        """Split an oversized segment by sentences."""
        # Try splitting by period
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        chunks = []
        current = ""
        current_tokens = 0
        
        for sentence in sentences:
            sentence_tokens = self.token_counter.count_tokens(sentence)
            
            if current_tokens + sentence_tokens <= max_tokens:
                current += " " + sentence if current else sentence
                current_tokens += sentence_tokens
            else:
                if current:
                    chunks.append(current)
                current = sentence
                current_tokens = sentence_tokens
        
        if current:
            chunks.append(current)
        
        return chunks
    
    def _create_chunk(
        self,
        content: str,
        url: str,
        source_id: str,
        raw_chunk: ChunkSchema
    ) -> ChunkSchema:
        """Create a chunk from content."""
        label = self.detect_content_type(content)
        token_count = self.token_counter.count_tokens(content)
        
        # Inherit metadata from raw chunk, add new fields
        metadata = raw_chunk.metadata.copy() if raw_chunk.metadata else {}
        metadata.update({
            'token_count': token_count,
            'content_type': label.value,
            'transformed_at': datetime.utcnow().isoformat(),
        })
        
        return ChunkSchema(
            url=url,
            label=label,
            content=content,
            title=raw_chunk.title,
            source_id=source_id,
            extracted_at=raw_chunk.extracted_at,
            metadata=metadata
        )