The Concept
The Extractor is the first stage of your ETL pipeline. It takes raw HTML fetched from websites and converts it into clean, usable text. Think of it as a "HTML → Text converter" that:

Removes noise (scripts, styles, ads, navigation menus)
Extracts semantic content (headings, paragraphs, lists, tables)
Preserves structure (relationships between sections)
Adds metadata (URLs, timestamps, source identifiers)
Handles encoding (UTF-8, special characters)
The Extractor doesn't split into chunks yet — that's the Transformer's job. It just produces clean, structured text ready for processing.

The Code

# Shared_core/etl/extractor.py

import re
from typing import Optional, Dict, Any, List
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from datetime import datetime
from ..models.chunk import ChunkSchema, ChunkLabel


class HTMLExtractor:
    """Extract and clean text from raw HTML."""
    
    # Tags to remove entirely (including content)
    REMOVE_TAGS = {'script', 'style', 'meta', 'noscript', 'iframe', 'nav', 'footer'}
    
    # Tags to extract text from but not preserve structure
    FLATTEN_TAGS = {'span', 'strong', 'em', 'b', 'i'}
    
    # Tags that indicate section boundaries
    SECTION_TAGS = {'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'article', 'section', 'main'}
    
    # Common ad/tracking patterns
    AD_PATTERNS = [
        r'(?i)(advertisement|ad-container|ads|sponsored)',
        r'(?i)(tracking pixel|beacon)',
        r'(?i)(google analytics|gtag)',
    ]
    
    @staticmethod
    def is_ad_or_tracking(text: str) -> bool:
        """Check if text looks like ad or tracking code."""
        for pattern in HTMLExtractor.AD_PATTERNS:
            if re.search(pattern, text):
                return True
        return False
    
    @staticmethod
    def clean_text(text: str) -> str:
        """Remove extra whitespace and normalize text."""
        # Remove multiple spaces
        text = re.sub(r' {2,}', ' ', text)
        # Remove extra newlines
        text = re.sub(r'\n{3,}', '\n\n', text)
        # Remove leading/trailing whitespace
        text = text.strip()
        return text
    
    @staticmethod
    def extract_from_html(
        html: str,
        url: str,
        source_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Extract clean text from HTML.
        
        Args:
            html: Raw HTML string
            url: Source URL
            source_id: Optional identifier for the source
        
        Returns:
            Dictionary with cleaned text, metadata, sections
        """
        try:
            soup = BeautifulSoup(html, 'html.parser')
        except Exception:
            # Fallback for malformed HTML
            soup = BeautifulSoup(html, 'html.parser')
        
        # Remove noise
        for tag in soup.find_all(HTMLExtractor.REMOVE_TAGS):
            tag.decompose()
        
        # Extract title
        title = ""
        if soup.find('title'):
            title = soup.find('title').get_text(strip=True)
        elif soup.find('h1'):
            title = soup.find('h1').get_text(strip=True)
        
        # Extract main body sections
        sections: List[Dict[str, str]] = []
        current_section = None
        
        for element in soup.find_all(['h1', 'h2', 'h3', 'p', 'li', 'table', 'blockquote']):
            text = element.get_text(strip=True)
            
            # Skip empty, ads, or tracking
            if not text or HTMLExtractor.is_ad_or_tracking(text):
                continue
            
            # Start new section on heading
            if element.name in ['h1', 'h2', 'h3']:
                if current_section and current_section.get('content', '').strip():
                    sections.append(current_section)
                
                current_section = {
                    'heading': text,
                    'level': int(element.name[1]),  # h1 → 1, h2 → 2
                    'content': '',
                    'type': 'heading'
                }
            
            # Add content to current section
            elif current_section:
                if element.name == 'table':
                    # Extract table as markdown-like
                    current_section['content'] += f"\n[TABLE]\n{text}\n[/TABLE]\n"
                elif element.name == 'blockquote':
                    current_section['content'] += f"\n> {text}\n"
                else:
                    current_section['content'] += f"\n{text}"
            
            else:
                # No heading yet, create default section
                current_section = {
                    'heading': 'Introduction',
                    'level': 0,
                    'content': text,
                    'type': 'text'
                }
        
        # Add last section
        if current_section and current_section.get('content', '').strip():
            sections.append(current_section)
        
        # Compile full text
        full_text = ""
        for section in sections:
            if section['type'] == 'heading':
                full_text += f"\n{'#' * section['level']} {section['heading']}\n"
                full_text += section['content']
            else:
                full_text += section['content']
        
        full_text = HTMLExtractor.clean_text(full_text)
        
        # Extract domain
        try:
            domain = urlparse(url).netloc
        except:
            domain = "unknown"
        
        # Compile metadata
        metadata = {
            'url': url,
            'source_id': source_id or domain,
            'domain': domain,
            'title': title,
            'extracted_at': datetime.utcnow().isoformat(),
            'section_count': len(sections),
            'char_count': len(full_text),
        }
        
        return {
            'text': full_text,
            'metadata': metadata,
            'sections': sections,
            'title': title,
        }
    
    @staticmethod
    def extract_with_schema(
        html: str,
        url: str,
        source_id: Optional[str] = None
    ) -> ChunkSchema:
        """Extract and return as ChunkSchema for downstream processing."""
        result = HTMLExtractor.extract_from_html(html, url, source_id)
        
        # Create a chunk representing the entire extracted content
        return ChunkSchema(
            url=url,
            label=ChunkLabel.RAW_EXTRACTION,
            content=result['text'],
            title=result['title'],
            source_id=result['metadata']['source_id'],
            extracted_at=result['metadata']['extracted_at'],
            metadata={
                'domain': result['metadata']['domain'],
                'section_count': result['metadata']['section_count'],
                'char_count': result['metadata']['char_count'],
            }
        )

Key Concepts
Concept	Purpose	Example
BeautifulSoup parsing	Parse malformed HTML safely	BeautifulSoup(html, 'html.parser')
Tag decomposition	Remove entire sections (scripts, styles)	script_tag.decompose() removes tag + children
Text extraction	Get content without HTML markup	.get_text(strip=True) removes tags, normalizes whitespace
Section detection	Group content by headings	h1/h2 marks section boundaries → preserve hierarchy
Ad/tracking filters	Skip noise patterns	Regex matches: "advertisement", "gtag", etc.
Metadata capture	Preserve source context	URL, domain, title, extraction timestamp
ChunkSchema bridge	Return Pydantic model for use downstream	RAW_EXTRACTION label signals "this is raw extracted text"
How It Connects
← INPUT: Raw HTML from web fetch (via MultiSiteFetcher agent)
PROCESS: Extract clean text, preserve structure, add metadata
→ OUTPUT: ChunkSchema(label=RAW_EXTRACTION, content=clean_text, metadata=...)
Feeds into Transformer (File 2) which chunks into semantic pieces
Labels help Transformer know to split further
MEMORY: Metadata stored; full text passed to Transformer


### FILE 2:The Concept
The Transformer takes raw extracted text and splits it into semantic chunks. Unlike generic splitting, the Transformer is smart:

Respects token limits (max 1,800 tokens per chunk from constants)
Preserves semantics (splits at paragraph/heading boundaries, not mid-sentence)
Maintains context (sliding window overlap so no information is orphaned)
Detects content type (heading, paragraph, code, table)
Assigns labels (HEADING, PARAGRAPH, CODE_BLOCK, TABLE_DATA)
Think of it as: "Take raw text, break it into meaningful pieces, each piece ≤ 1,800 tokens, label them, keep context."

The Code

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

Key Concepts
Concept	Purpose	Example
Semantic boundaries	Split at natural breaks, not arbitrary positions	\n\n (paragraphs), headings
Token counting	Measure content size precisely before splitting	token_counter.count_tokens(text) returns actual token count
MAX_CHUNK_TOKENS	Hard limit from constants (1,800)	Prevents chunks from exceeding LLM limits
Sliding window overlap	Keep context between chunks	Last N tokens of chunk 1 prepended to chunk 2 (CHUNK_OVERLAP_TOKENS)
Content type detection	Label chunks by what they contain	Code block → CODE_BLOCK, heading → HEADING, etc.
Oversized segment handling	Split large segments by sentences if paragraphs too big	Fallback when single paragraph exceeds 1,800 tokens
Metadata inheritance	Carry source info through pipeline	URL, source_id, title passed to all child chunks
How It Connects
← INPUT: ChunkSchema(label=RAW_EXTRACTION, content=full_text) from Extractor
PROCESS:
Detect semantic boundaries (paragraphs, headings)
Build chunks respecting 1,800 token limit
Preserve context via sliding window overlap
Label each chunk (HEADING, PARAGRAPH, CODE, TABLE_DATA)
→ OUTPUT: List of ChunkSchema objects, each semantically meaningful, token-aware, labeled
Feeds into Loader (File 3) which saves to Redis/Chroma/Markdown
USES: TokenCounter utility, MAX_CHUNK_TOKENS & CHUNK_OVERLAP_TOKENS from constants


### File 3 loader.py

The Concept
The Loader is the final stage of ETL. It takes the semantic chunks from the Transformer and orchestrates saving them to three memory systems simultaneously:

Redis (fast cache, 45-min TTL, for recent queries)
Chroma (vector embeddings, semantic search)
Markdown Archive (persistent disk storage, human-readable)
Think of it as: "Take chunks, embed them, deduplicate, cache, and archive — all at once."

The Code

# Shared_core/etl/loader.py

import asyncio
from typing import List, Dict, Optional
from ..models.chunk import ChunkSchema
from ..memory.redis_manager import RedisManager
from ..memory.chroma_manager import ChromaManager
from ..memory.markdown_archive import MarkdownArchive
from ..logger.structured_logger import StructuredLogger
from datetime import datetime


class ChunkLoader:
    """Load transformed chunks into memory systems (Redis, Chroma, Markdown)."""
    
    def __init__(self):
        """Initialize all memory managers and logger."""
        self.redis_mgr = RedisManager()
        self.chroma_mgr = ChromaManager()
        self.archive_mgr = MarkdownArchive()
        self.logger = StructuredLogger()
    
    def load_chunks(
        self,
        chunks: List[ChunkSchema],
        query_intent: Optional[str] = None,
    ) -> Dict[str, any]:
        """
        Load a list of chunks into all memory systems.
        
        Args:
            chunks: List of ChunkSchema objects from Transformer
            query_intent: Optional intent string for logging context
        
        Returns:
            Dictionary with load results (counts, errors, timestamps)
        """
        load_start = datetime.utcnow()
        results = {
            'query_intent': query_intent,
            'chunks_received': len(chunks),
            'redis_saved': 0,
            'chroma_added': 0,
            'archive_saved': 0,
            'errors': [],
            'started_at': load_start.isoformat(),
        }
        
        if not chunks:
            self.logger.log_metric(
                component='loader',
                event='load_chunks',
                wall_time_ms=0,
                tokens_used=0,
                metadata={'chunks': 0, 'status': 'no_chunks'}
            )
            return results
        
        # Process each chunk
        for i, chunk in enumerate(chunks):
            try:
                # 1. Add to Chroma (vector DB) — this creates embeddings
                self.chroma_mgr.add_chunk(chunk)
                results['chroma_added'] += 1
                
                # 2. Cache to Redis (fast lookup, prevents duplicate work)
                self.redis_mgr.cache_chunk(chunk)
                results['redis_saved'] += 1
                
                # 3. Archive to Markdown (persistent storage)
                self.archive_mgr.save_chunk(chunk)
                results['archive_saved'] += 1
                
                self.logger.log_metric(
                    component='loader',
                    event='chunk_loaded',
                    wall_time_ms=0,
                    tokens_used=len(chunk.content.split()),
                    metadata={
                        'chunk_index': i,
                        'label': chunk.label.value,
                        'url': chunk.url,
                    }
                )
            
            except Exception as e:
                error_msg = f"Failed to load chunk {i}: {str(e)}"
                results['errors'].append(error_msg)
                self.logger.log_metric(
                    component='loader',
                    event='chunk_load_error',
                    wall_time_ms=0,
                    tokens_used=0,
                    metadata={'chunk_index': i, 'error': str(e)}
                )
        
        load_end = datetime.utcnow()
        load_ms = (load_end - load_start).total_seconds() * 1000
        
        results.update({
            'completed_at': load_end.isoformat(),
            'total_load_time_ms': load_ms,
            'error_count': len(results['errors']),
        })
        
        self.logger.log_metric(
            component='loader',
            event='load_session_complete',
            wall_time_ms=load_ms,
            tokens_used=sum(len(c.content.split()) for c in chunks),
            metadata={
                'chunks': len(chunks),
                'redis_saved': results['redis_saved'],
                'chroma_added': results['chroma_added'],
                'archive_saved': results['archive_saved'],
                'errors': len(results['errors']),
            }
        )
        
        return results
    
    def load_query_session(
        self,
        chunks: List[ChunkSchema],
        query: str,
        intent: str,
        source_urls: List[str],
    ) -> Dict[str, any]:
        """
        Load chunks as part of a query session (for archival).
        
        Args:
            chunks: Processed chunks
            query: Original user query
            intent: Extracted intent
            source_urls: List of source URLs
        
        Returns:
            Session metadata
        """
        session_id = self.archive_mgr.save_query_session(
            chunks=chunks,
            query=query,
            intent=intent,
            source_urls=source_urls
        )
        
        # Also load into fast access layers
        load_results = self.load_chunks(chunks, query_intent=intent)
        
        load_results['session_id'] = session_id
        
        self.logger.log_metric(
            component='loader',
            event='query_session_loaded',
            wall_time_ms=0,
            tokens_used=sum(len(c.content.split()) for c in chunks),
            metadata={'session_id': session_id, 'query': query}
        )
        
        return load_results
    
    def get_load_stats(self) -> Dict[str, any]:
        """Get aggregate statistics from all memory systems."""
        redis_stats = self.redis_mgr.get_stats()
        chroma_stats = self.chroma_mgr.get_stats()
        archive_stats = self.archive_mgr.get_archive_stats()
        
        stats = {
            'redis': redis_stats,
            'chroma': chroma_stats,
            'archive': archive_stats,
            'aggregated_at': datetime.utcnow().isoformat(),
        }
        
        self.logger.log_metric(
            component='loader',
            event='stats_retrieved',
            wall_time_ms=0,
            tokens_used=0,
            metadata=stats
        )
        
        return stats
    
    def cleanup_old_archives(self, days: int = 30) -> Dict[str, any]:
        """
        Clean up old archives (older than N days).
        
        Args:
            days: Keep archives newer than this many days
        
        Returns:
            Cleanup results
        """
        cleaned = self.archive_mgr.cleanup_old_archives(days=days)
        
        self.logger.log_metric(
            component='loader',
            event='cleanup_archives',
            wall_time_ms=0,
            tokens_used=0,
            metadata={'days': days, 'removed': cleaned}
        )
        
        return {'removed': cleaned, 'cleaned_at': datetime.utcnow().isoformat()}


class LoaderPipeline:
    """Orchestrate full ETL pipeline: Extract → Transform → Load."""
    
    def __init__(self):
        """Initialize ETL components."""
        from .extractor import HTMLExtractor
        from .transformer import TextTransformer
        
        self.extractor = HTMLExtractor()
        self.transformer = TextTransformer()
        self.loader = ChunkLoader()
    
    def process_url(
        self,
        html: str,
        url: str,
        source_id: Optional[str] = None,
        query_intent: Optional[str] = None,
    ) -> Dict[str, any]:
        """
        Full ETL: Extract HTML → Transform to chunks → Load to memory.
        
        Args:
            html: Raw HTML from fetch
            url: Source URL
            source_id: Optional source identifier
            query_intent: Optional query context
        
        Returns:
            Full pipeline results
        """
        pipeline_start = datetime.utcnow()
        results = {'url': url, 'stages': {}}
        
        try:
            # EXTRACT
            extract_start = datetime.utcnow()
            raw_chunk = self.extractor.extract_with_schema(html, url, source_id)
            extract_ms = (datetime.utcnow() - extract_start).total_seconds() * 1000
            results['stages']['extract'] = {
                'status': 'success',
                'time_ms': extract_ms,
                'content_length': len(raw_chunk.content),
            }
            
            # TRANSFORM
            transform_start = datetime.utcnow()
            semantic_chunks = self.transformer.transform_to_chunks(
                raw_chunk, url, source_id or url
            )
            transform_ms = (datetime.utcnow() - transform_start).total_seconds() * 1000
            results['stages']['transform'] = {
                'status': 'success',
                'time_ms': transform_ms,
                'chunks_created': len(semantic_chunks),
            }
            
            # LOAD
            load_start = datetime.utcnow()
            load_results = self.loader.load_chunks(semantic_chunks, query_intent)
            load_ms = (datetime.utcnow() - load_start).total_seconds() * 1000
            results['stages']['load'] = {
                'status': 'success',
                'time_ms': load_ms,
                **load_results
            }
            
            pipeline_ms = (datetime.utcnow() - pipeline_start).total_seconds() * 1000
            results['total_time_ms'] = pipeline_ms
            results['status'] = 'success'
        
        except Exception as e:
            results['status'] = 'error'
            results['error'] = str(e)
            results['total_time_ms'] = (
                datetime.utcnow() - pipeline_start
            ).total_seconds() * 1000
        
        return results

Key Concepts
Concept	Purpose	Example
Multi-system save	Redundancy + speed: cache + embed + archive	Redis (fast), Chroma (semantic), Markdown (durable)
Redis layer	Recent queries, deduplication, 45-min TTL	cache_chunk() prevents re-processing
Chroma layer	Vector embeddings, semantic search, cosine similarity	Enables "find similar chunks" queries later
Markdown Archive	Human-readable, disk-stored, versioned	For debugging, export, long-term retention
Load stats	Visibility into what's cached/embedded/archived	Aggregates stats from all 3 systems
Cleanup routine	Remove stale archives to save disk space	cleanup_old_archives(days=30)
Full pipeline	Container that orchestrates Extract → Transform → Load	LoaderPipeline.process_url() ties all 3 stages
How It Connects
← INPUT: List of ChunkSchema objects from Transformer (File 2)
PROCESS:
Save each chunk to Redis (fast cache)
Add each chunk to Chroma (generates embeddings, enables semantic search)
Archive each chunk to Markdown (persistent storage)
Log metrics at every step (timing, token counts, errors)
→ OUTPUT:
Results dict with counts: {redis_saved, chroma_added, archive_saved, errors}
All three memory systems populated and ready for downstream queries
USES: RedisManager, ChromaManager, MarkdownArchive, StructuredLogger
PROVIDES: LoaderPipeline class that ties Extract+Transform+Load into one method

### file 4

pipeline.py

The Concept
The Pipeline is the orchestrator and API for the full ETL system. It ties Extract → Transform → Load into one clean interface. Think of it as:

"One method call: pipeline.process_html(html, url) and everything happens."

Plus, it provides utility methods for agents to:

Retrieve cached/embedded chunks for a query
Search by intent, label, or similarity
Export results as markdown or JSON
Log everything for evaluation

The Code

# Shared_core/etl/pipeline.py

from typing import List, Dict, Optional, Any
from datetime import datetime
from ..models.chunk import ChunkSchema, ChunkLabel, IntentSchema
from ..models.search_plan import SearchPlanSchema
from ..memory.redis_manager import RedisManager
from ..memory.chroma_manager import ChromaManager
from ..memory.markdown_archive import MarkdownArchive
from ..logger.structured_logger import StructuredLogger
from .extractor import HTMLExtractor
from .transformer import TextTransformer
from .loader import ChunkLoader, LoaderPipeline


class ETLPipeline:
    """
    High-level ETL API for agents.
    
    Single entry point: process_html() or process_url()
    Orchestrates: Extract → Transform → Load
    Provides: Search, retrieval, export functions
    """
    
    def __init__(self):
        """Initialize all ETL components."""
        self.extractor = HTMLExtractor()
        self.transformer = TextTransformer()
        self.loader = ChunkLoader()
        self.redis_mgr = RedisManager()
        self.chroma_mgr = ChromaManager()
        self.archive_mgr = MarkdownArchive()
        self.logger = StructuredLogger()
    
    def process_html(
        self,
        html: str,
        url: str,
        source_id: Optional[str] = None,
        query_intent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Full ETL pipeline: Extract HTML → Transform → Load.
        
        Args:
            html: Raw HTML from fetcher
            url: Source URL
            source_id: Optional source identifier (defaults to domain)
            query_intent: Optional query context for logging
        
        Returns:
            Pipeline results: {status, chunks_created, saved_to: {redis, chroma, archive}}
        """
        pipeline_start = datetime.utcnow()
        results = {
            'url': url,
            'source_id': source_id,
            'query_intent': query_intent,
            'started_at': pipeline_start.isoformat(),
        }
        
        try:
            # EXTRACT: HTML → Raw chunk
            raw_chunk = self.extractor.extract_with_schema(html, url, source_id)
            self.logger.log_metric(
                component='pipeline',
                event='extract_complete',
                wall_time_ms=0,
                tokens_used=len(raw_chunk.content.split()),
                metadata={'url': url, 'char_count': len(raw_chunk.content)}
            )
            
            # TRANSFORM: Raw chunk → Semantic chunks
            semantic_chunks = self.transformer.transform_to_chunks(
                raw_chunk, url, source_id or url
            )
            self.logger.log_metric(
                component='pipeline',
                event='transform_complete',
                wall_time_ms=0,
                tokens_used=sum(len(c.content.split()) for c in semantic_chunks),
                metadata={'chunks_created': len(semantic_chunks)}
            )
            
            # LOAD: Save to Redis + Chroma + Markdown
            load_results = self.loader.load_chunks(semantic_chunks, query_intent)
            
            pipeline_end = datetime.utcnow()
            pipeline_ms = (pipeline_end - pipeline_start).total_seconds() * 1000
            
            results.update({
                'status': 'success',
                'chunks_created': len(semantic_chunks),
                'saved_to': {
                    'redis': load_results['redis_saved'],
                    'chroma': load_results['chroma_added'],
                    'archive': load_results['archive_saved'],
                },
                'errors': load_results.get('errors', []),
                'total_time_ms': pipeline_ms,
                'completed_at': pipeline_end.isoformat(),
            })
            
            self.logger.log_metric(
                component='pipeline',
                event='etl_complete',
                wall_time_ms=pipeline_ms,
                tokens_used=sum(len(c.content.split()) for c in semantic_chunks),
                metadata={
                    'url': url,
                    'chunks': len(semantic_chunks),
                    'redis': load_results['redis_saved'],
                    'chroma': load_results['chroma_added'],
                }
            )
        
        except Exception as e:
            pipeline_end = datetime.utcnow()
            results['status'] = 'error'
            results['error'] = str(e)
            results['total_time_ms'] = (pipeline_end - pipeline_start).total_seconds() * 1000
            
            self.logger.log_metric(
                component='pipeline',
                event='etl_error',
                wall_time_ms=results['total_time_ms'],
                tokens_used=0,
                metadata={'url': url, 'error': str(e)}
            )
        
        return results
    
    def search_by_query(
        self,
        query: str,
        intent: IntentSchema,
        top_k: int = 5,
    ) -> List[ChunkSchema]:
        """
        Semantic search: Find top-k most similar chunks to query.
        
        Args:
            query: User question/search string
            intent: Extracted IntentSchema with QueryType
            top_k: Number of results to return (default 5)
        
        Returns:
            List of most relevant ChunkSchema objects
        """
        try:
            # Search Chroma vector DB by similarity
            results = self.chroma_mgr.search(query, top_k=top_k)
            
            self.logger.log_metric(
                component='pipeline',
                event='search_complete',
                wall_time_ms=0,
                tokens_used=len(query.split()),
                metadata={'query': query, 'intent': intent.query_type.value, 'results': len(results)}
            )
            
            return results
        
        except Exception as e:
            self.logger.log_metric(
                component='pipeline',
                event='search_error',
                wall_time_ms=0,
                tokens_used=0,
                metadata={'query': query, 'error': str(e)}
            )
            return []
    
    def search_by_label(
        self,
        label: ChunkLabel,
        top_k: int = 10,
    ) -> List[ChunkSchema]:
        """
        Find all chunks with a specific label (HEADING, PARAGRAPH, CODE_BLOCK, etc).
        
        Args:
            label: ChunkLabel enum value (e.g., HEADING, PARAGRAPH)
            top_k: Max number to return
        
        Returns:
            List of chunks with matching label
        """
        try:
            results = self.chroma_mgr.search_by_label(label, top_k=top_k)
            
            self.logger.log_metric(
                component='pipeline',
                event='search_by_label',
                wall_time_ms=0,
                tokens_used=0,
                metadata={'label': label.value, 'results': len(results)}
            )
            
            return results
        
        except Exception as e:
            self.logger.log_metric(
                component='pipeline',
                event='search_by_label_error',
                wall_time_ms=0,
                tokens_used=0,
                metadata={'label': label.value if label else 'unknown', 'error': str(e)}
            )
            return []
    
    def get_cached_results(
        self,
        query_hash: str,
    ) -> Optional[List[ChunkSchema]]:
        """
        Retrieve cached results for a query (from Redis).
        
        Args:
            query_hash: MD5 hash of query (created by RedisManager)
        
        Returns:
            List of cached ChunkSchema objects, or None if not found/expired
        """
        try:
            cached = self.redis_mgr.get_cached_query_result(query_hash)
            
            if cached:
                self.logger.log_metric(
                    component='pipeline',
                    event='cache_hit',
                    wall_time_ms=0,
                    tokens_used=0,
                    metadata={'query_hash': query_hash, 'chunks': len(cached)}
                )
            
            return cached
        
        except Exception as e:
            self.logger.log_metric(
                component='pipeline',
                event='cache_read_error',
                wall_time_ms=0,
                tokens_used=0,
                metadata={'query_hash': query_hash, 'error': str(e)}
            )
            return None
    
    def cache_results(
        self,
        query_hash: str,
        chunks: List[ChunkSchema],
        ttl_seconds: int = 2700,  # Default 45 mins
    ) -> bool:
        """
        Cache search results for future reuse.
        
        Args:
            query_hash: MD5 hash of query
            chunks: List of ChunkSchema to cache
            ttl_seconds: Time-to-live in seconds (default 45 min)
        
        Returns:
            True if cached successfully
        """
        try:
            self.redis_mgr.cache_query_result(query_hash, chunks, ttl_seconds=ttl_seconds)
            
            self.logger.log_metric(
                component='pipeline',
                event='cache_write',
                wall_time_ms=0,
                tokens_used=0,
                metadata={'query_hash': query_hash, 'chunks': len(chunks)}
            )
            
            return True
        
        except Exception as e:
            self.logger.log_metric(
                component='pipeline',
                event='cache_write_error',
                wall_time_ms=0,
                tokens_used=0,
                metadata={'query_hash': query_hash, 'error': str(e)}
            )
            return False
    
    def export_chunks_as_markdown(
        self,
        chunks: List[ChunkSchema],
        output_file: str,
        title: str = "Search Results",
    ) -> bool:
        """
        Export chunks to a markdown file.
        
        Args:
            chunks: List of ChunkSchema to export
            output_file: Path to write markdown file
            title: Markdown document title
        
        Returns:
            True if export successful
        """
        try:
            from ..utils.markdown_builder import MarkdownBuilder
            
            builder = MarkdownBuilder()
            
            # Create table of chunks
            table_md = builder.create_results_table(chunks)
            
            # Create summary section
            summary_md = builder.create_summary_section(len(chunks), title)
            
            # Combine
            full_doc = f"# {title}\n\n{summary_md}\n\n{table_md}"
            
            # Save to file
            builder.save_to_file(full_doc, output_file)
            
            self.logger.log_metric(
                component='pipeline',
                event='export_markdown',
                wall_time_ms=0,
                tokens_used=sum(len(c.content.split()) for c in chunks),
                metadata={'output_file': output_file, 'chunks': len(chunks)}
            )
            
            return True
        
        except Exception as e:
            self.logger.log_metric(
                component='pipeline',
                event='export_error',
                wall_time_ms=0,
                tokens_used=0,
                metadata={'output_file': output_file, 'error': str(e)}
            )
            return False
    
    def get_pipeline_stats(self) -> Dict[str, Any]:
        """Get aggregate statistics across all memory systems."""
        try:
            stats = {
                'redis': self.redis_mgr.get_stats(),
                'chroma': self.chroma_mgr.get_stats(),
                'archive': self.archive_mgr.get_archive_stats(),
                'queried_at': datetime.utcnow().isoformat(),
            }
            
            self.logger.log_metric(
                component='pipeline',
                event='stats_retrieved',
                wall_time_ms=0,
                tokens_used=0,
                metadata=stats
            )
            
            return stats
        
        except Exception as e:
            self.logger.log_metric(
                component='pipeline',
                event='stats_error',
                wall_time_ms=0,
                tokens_used=0,
                metadata={'error': str(e)}
            )
            return {}
    
    def cleanup(self, days: int = 30) -> Dict[str, Any]:
        """
        Clean up old data (archives older than N days).
        
        Args:
            days: Archive age threshold
        
        Returns:
            Cleanup results
        """
        try:
            removed = self.archive_mgr.cleanup_old_archives(days=days)
            
            results = {
                'status': 'success',
                'archives_removed': removed,
                'cleaned_at': datetime.utcnow().isoformat(),
            }
            
            self.logger.log_metric(
                component='pipeline',
                event='cleanup_complete',
                wall_time_ms=0,
                tokens_used=0,
                metadata={'days': days, 'removed': removed}
            )
            
            return results
        
        except Exception as e:
            results = {
                'status': 'error',
                'error': str(e),
            }
            
            self.logger.log_metric(
                component='pipeline',
                event='cleanup_error',
                wall_time_ms=0,
                tokens_used=0,
                metadata={'days': days, 'error': str(e)}
            )
            
            return results


# Singleton instance for easy import
_pipeline_instance = None

def get_pipeline() -> ETLPipeline:
    """Get or create the global ETL pipeline singleton."""
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = ETLPipeline()
    return _pipeline_instance


Key Concepts
Concept	Purpose	Example
Single entry point	One method for full ETL	pipeline.process_html(html, url) does Extract+Transform+Load
search_by_query()	Semantic search via Chroma	Find top-5 most similar chunks to user question
search_by_label()	Filter by content type	Get all HEADING chunks from a domain
Cache layer	Avoid redundant processing	cache_results() saves query results for 45 mins
Export utilities	Downstream agent tools	export_chunks_as_markdown() for human-readable output
Pipeline stats	Observability	Aggregate info: Redis keys, Chroma vectors, Archive size
Cleanup routine	Maintenance	Remove old archives to save disk
Singleton pattern	Global access	get_pipeline() ensures one instance
How It Connects
← INPUT:
Raw HTML from Fetcher agent → process_html()
User query → search_by_query()
Intent → search_by_label()
PROCESS:
Full ETL orchestration
Semantic search
Cache management
Export formatting
→ OUTPUT:
Processed chunks ready for LLM (via search_by_query())
Markdown exports for agents to read
Cache hits for deduplication
USED BY: All 6 agents (IntentExtractor, SearchPlanner, Fetcher, ChunkProcessor, Ranker, Synthesizer)
PROVIDES: Clean API so agents don't import Loader/Transformer/Extractor directly
