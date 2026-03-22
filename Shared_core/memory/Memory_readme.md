File 1: redis_manager.py — Redis Cache Operations

This manages query deduplication and chunk caching to avoid re-fetching.

CODE :

# Shared_core/memory/redis_manager.py

import redis
import json
from typing import Optional, List, Dict
from datetime import timedelta
import hashlib

class RedisManager:
    """Manage caching layer using Redis for deduplication & query results."""
    
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0, ttl_seconds: int = 2700):
        """
        Args:
            host: Redis host (default: localhost)
            port: Redis port (default: 6379)
            db: Redis database number (default: 0)
            ttl_seconds: Cache time-to-live in seconds (default: 2700 = 45 min)
        """
        self.client = redis.Redis(host=host, port=port, db=db, decode_responses=True)
        self.ttl = timedelta(seconds=ttl_seconds)
        self.prefix = "agentic_research:"
    
    def _make_key(self, key_type: str, key_id: str) -> str:
        """
        Create namespaced Redis key.
        
        Args:
            key_type: Type of key (e.g., "query", "chunk", "url")
            key_id: Unique identifier
        
        Returns:
            Namespaced key (e.g., "agentic_research:query:abc123")
        """
        return f"{self.prefix}{key_type}:{key_id}"
    
    def cache_query_result(self, query: str, result: Dict) -> None:
        """
        Cache search result for a query to avoid re-fetching.
        
        Args:
            query: User query (e.g., "best laptop under $1000")
            result: Result dict (search plan, fetched chunks, etc.)
        """
        query_hash = hashlib.md5(query.encode()).hexdigest()
        key = self._make_key("query", query_hash)
        
        # Store as JSON string
        self.client.setex(key, self.ttl, json.dumps(result))
    
    def get_cached_query_result(self, query: str) -> Optional[Dict]:
        """
        Retrieve cached result for a query if it exists & hasn't expired.
        
        Args:
            query: User query
        
        Returns:
            Cached result dict, or None if not found/expired
        """
        query_hash = hashlib.md5(query.encode()).hexdigest()
        key = self._make_key("query", query_hash)
        
        cached = self.client.get(key)
        if cached:
            return json.loads(cached)
        return None
    
    def cache_chunk(self, url: str, chunk_id: str, chunk_text: str, metadata: Optional[Dict] = None) -> None:
        """
        Cache a single chunk to avoid re-parsing same URL.
        
        Args:
            url: Source URL
            chunk_id: Unique chunk identifier (e.g., hash of content)
            chunk_text: Chunk content
            metadata: Optional metadata (label, tokens, etc.)
        """
        key = self._make_key("chunk", chunk_id)
        
        data = {
            "text": chunk_text,
            "url": url,
            "metadata": metadata or {}
        }
        
        self.client.setex(key, self.ttl, json.dumps(data))
    
    def get_cached_chunk(self, chunk_id: str) -> Optional[Dict]:
        """
        Retrieve cached chunk if available.
        
        Args:
            chunk_id: Chunk identifier
        
        Returns:
            Chunk dict with 'text', 'url', 'metadata', or None
        """
        key = self._make_key("chunk", chunk_id)
        cached = self.client.get(key)
        if cached:
            return json.loads(cached)
        return None
    
    def cache_url_fetch(self, url: str, html_content: str) -> None:
        """
        Cache raw HTML from URL to avoid re-fetching same page.
        
        Args:
            url: URL that was fetched
            html_content: HTML content from that URL
        """
        url_hash = hashlib.md5(url.encode()).hexdigest()
        key = self._make_key("url", url_hash)
        
        self.client.setex(key, self.ttl, html_content)
    
    def get_cached_url_fetch(self, url: str) -> Optional[str]:
        """
        Retrieve cached HTML for a URL if available.
        
        Args:
            url: URL to check
        
        Returns:
            HTML content, or None if not cached/expired
        """
        url_hash = hashlib.md5(url.encode()).hexdigest()
        key = self._make_key("url", url_hash)
        
        return self.client.get(key)
    
    def mark_url_as_fetched(self, url: str) -> None:
        """
        Track URLs that have been processed (prevents duplicate fetches).
        
        Args:
            url: URL that was fetched
        """
        url_hash = hashlib.md5(url.encode()).hexdigest()
        key = self._make_key("fetched_urls", url_hash)
        
        self.client.setex(key, self.ttl, "1")
    
    def is_url_fetched(self, url: str) -> bool:
        """
        Check if URL has already been fetched in recent cache window.
        
        Args:
            url: URL to check
        
        Returns:
            True if URL was fetched recently, False otherwise
        """
        url_hash = hashlib.md5(url.encode()).hexdigest()
        key = self._make_key("fetched_urls", url_hash)
        
        return self.client.exists(key) > 0
    
    def clear_all(self) -> None:
        """
        Clear all cached data (use sparingly — for testing only).
        """
        pattern = f"{self.prefix}*"
        keys = self.client.keys(pattern)
        if keys:
            self.client.delete(*keys)
    
    def get_stats(self) -> Dict:
        """
        Get cache statistics (useful for monitoring).
        
        Returns:
            {
                "total_keys": int,
                "cached_queries": int,
                "cached_chunks": int,
                "cached_urls": int
            }
        """
        pattern = f"{self.prefix}*"
        keys = self.client.keys(pattern)
        
        stats = {
            "total_keys": len(keys),
            "cached_queries": len([k for k in keys if ":query:" in k]),
            "cached_chunks": len([k for k in keys if ":chunk:" in k]),
            "cached_urls": len([k for k in keys if ":url:" in k])
        }
        
        return stats


        Key Concepts:

Concept	Purpose	Used By
cache_query_result()	Store full query result (prevent re-searching)	SearchPlanner (deduplication)
cache_chunk()	Store individual chunks parsed from pages	ChunkProcessor (avoid re-parsing)
cache_url_fetch()	Store raw HTML (avoid re-fetching same page)	MultiSiteFetcher
is_url_fetched()	Check if URL already in cache	SearchPlanner (parallel fetching)
MD5 hashing	Convert query/URL → consistent hash key	Key naming (deterministic lookup)
ttl = 2700s	Auto-expire old entries (45 min)	settings.py controls this
get_stats()	Monitor cache size/efficiency	Debugging + performance tuning
How It Connects:

settings.py provides redis_host, redis_port, cache_ttl_seconds
MultiSiteFetcher checks is_url_fetched() before parallel fetch to avoid duplicates
ChunkProcessor stores chunks via cache_chunk() for later retrieval
StructuredLogger can log cache hit/miss stats

Example usage:
from Shared_core.memory import RedisManager

redis_mgr = RedisManager(host="localhost", port=6379, ttl_seconds=2700)

# Before fetching URL, check cache
if redis_mgr.is_url_fetched("https://amazon.com/laptop"):
    print("Already fetched recently")
else:
    # Fetch & cache
    html = fetch_url(...)
    redis_mgr.cache_url_fetch("https://amazon.com/laptop", html)

Cache key format: agentic_research:query:abc123def456 (namespaced to prevent collisions)

File 2: chroma_manager.py — Chroma Vector Store for Semantic Search

This manages embeddings: stores chunk vectors so you can find similar chunks by meaning (not just keyword search).

CODE:

# Shared_core/memory/chroma_manager.py

import chromadb
from chromadb.config import Settings
from typing import List, Dict, Optional
import hashlib

class ChromaManager:
    """Manage vector embeddings in Chroma for semantic search on chunks."""
    
    def __init__(self, persist_directory: str = "./chroma_data", collection_name: str = "web_chunks"):
        """
        Args:
            persist_directory: Where to store Chroma embeddings (default: ./chroma_data)
            collection_name: Name of Chroma collection (default: web_chunks)
        """
        # Initialize Chroma with persistence
        settings = Settings(
            chroma_db_impl="duckdb+parquet",
            persist_directory=persist_directory,
            anonymized_telemetry=False
        )
        
        self.client = chromadb.Client(settings)
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}  # Use cosine similarity
        )
    
    def add_chunk(
        self,
        chunk_id: str,
        chunk_text: str,
        source_url: str,
        label: str = "general",
        metadata: Optional[Dict] = None
    ) -> None:
        """
        Add a chunk to the vector store.
        Chroma automatically embeds the text.
        
        Args:
            chunk_id: Unique chunk identifier (e.g., hash of content)
            chunk_text: Full chunk text to embed
            source_url: URL where chunk came from
            label: Chunk label (e.g., "price", "review", "definition")
            metadata: Additional metadata (tokens, domain, etc.)
        """
        meta = metadata or {}
        meta["source_url"] = source_url
        meta["label"] = label
        
        # Add to collection (auto-embedded)
        self.collection.add(
            ids=[chunk_id],
            documents=[chunk_text],
            metadatas=[meta]
        )
    
    def search(
        self,
        query: str,
        top_k: int = 5,
        label_filter: Optional[str] = None
    ) -> List[Dict]:
        """
        Semantic search: find most similar chunks by meaning.
        
        Args:
            query: Search query (e.g., "price in USD")
            top_k: How many results to return (default: 5)
            label_filter: Optional — only return chunks with this label
        
        Returns:
            List of result dicts:
            [
                {
                    "chunk_id": str,
                    "chunk_text": str,
                    "distance": float (0=identical, 1=opposite),
                    "source_url": str,
                    "label": str
                },
                ...
            ]
        """
        # Build where filter if label specified
        where_filter = None
        if label_filter:
            where_filter = {"label": {"$eq": label_filter}}
        
        results = self.collection.query(
            query_texts=[query],
            n_results=top_k,
            where=where_filter
        )
        
        # Parse results into friendly format
        parsed = []
        if results["ids"] and len(results["ids"]) > 0:
            for i, chunk_id in enumerate(results["ids"][0]):
                parsed.append({
                    "chunk_id": chunk_id,
                    "chunk_text": results["documents"][0][i],
                    "distance": results["distances"][0][i],
                    "source_url": results["metadatas"][0][i].get("source_url", ""),
                    "label": results["metadatas"][0][i].get("label", "")
                })
        
        return parsed
    
    def search_by_label(
        self,
        label: str,
        top_k: int = 10
    ) -> List[Dict]:
        """
        Get all chunks with a specific label (e.g., all "price" chunks).
        
        Args:
            label: Label to filter by
            top_k: Max results to return
        
        Returns:
            List of chunk dicts with that label
        """
        results = self.collection.get(
            where={"label": {"$eq": label}},
            limit=top_k
        )
        
        parsed = []
        if results["ids"]:
            for i, chunk_id in enumerate(results["ids"]):
                parsed.append({
                    "chunk_id": chunk_id,
                    "chunk_text": results["documents"][i],
                    "source_url": results["metadatas"][i].get("source_url", ""),
                    "label": results["metadatas"][i].get("label", "")
                })
        
        return parsed
    
    def get_chunk(self, chunk_id: str) -> Optional[Dict]:
        """
        Retrieve a specific chunk by ID.
        
        Args:
            chunk_id: Chunk ID to fetch
        
        Returns:
            Chunk dict, or None if not found
        """
        results = self.collection.get(ids=[chunk_id])
        
        if results["ids"] and len(results["ids"]) > 0:
            return {
                "chunk_id": chunk_id,
                "chunk_text": results["documents"][0],
                "source_url": results["metadatas"][0].get("source_url", ""),
                "label": results["metadatas"][0].get("label", "")
            }
        
        return None
    
    def delete_chunk(self, chunk_id: str) -> None:
        """
        Remove a chunk from the vector store.
        
        Args:
            chunk_id: Chunk ID to delete
        """
        self.collection.delete(ids=[chunk_id])
    
    def clear_collection(self) -> None:
        """
        Clear all chunks from collection (use sparingly — for testing).
        """
        try:
            self.client.delete_collection(name=self.collection.name)
            self.collection = self.client.get_or_create_collection(
                name=self.collection.name,
                metadata={"hnsw:space": "cosine"}
            )
        except Exception:
            # If delete fails, just continue
            pass
    
    def count(self) -> int:
        """
        Get total number of chunks in collection.
        
        Returns:
            Number of chunks stored
        """
        return self.collection.count()
    
    def get_stats(self) -> Dict:
        """
        Get collection statistics.
        
        Returns:
            {
                "total_chunks": int,
                "chunks_by_label": {label: count, ...}
            }
        """
        count = self.collection.count()
        
        # Get all chunks to count by label
        all_results = self.collection.get(limit=10000)  # Reasonable upper limit
        
        label_counts = {}
        if all_results["metadatas"]:
            for meta in all_results["metadatas"]:
                label = meta.get("label", "unknown")
                label_counts[label] = label_counts.get(label, 0) + 1
        
        return {
            "total_chunks": count,
            "chunks_by_label": label_counts
        }

Key Concepts:

Concept	Purpose	Used By
add_chunk()	Store chunk text + metadata in Chroma (auto-embedded)	ChunkProcessor (after parsing)
search()	Semantic search by query meaning (find relevant chunks)	CrossSiteRanker (retrieve context)
search_by_label()	Filter chunks by type (e.g., all "price" chunks)	Ranker (within-label comparison)
label_filter	Search only specific chunk types	Targeted retrieval (efficiency)
distance metric	Cosine similarity (0=identical, 1=opposite)	Ranking chunks by relevance
persist_directory	Where embeddings are saved (disk-backed)	Survives restarts
get_stats()	Monitor collection size by label	Debugging + performance tracking
How It Connects:

settings.py provides chroma.persist_directory and chroma.collection_name
ChunkProcessor calls add_chunk() after extracting & labeling each chunk from HTML
CrossSiteRanker calls search() to find top-K most similar chunks to query
StructuredLogger can log search times/result counts

Example usage:

from Shared_core.memory import ChromaManager

chroma = ChromaManager(persist_directory="./chroma_data")

# Add chunks after processing
chroma.add_chunk(
    chunk_id="chunk_abc123",
    chunk_text="iPhone 15 costs $999 and has 48MP camera",
    source_url="https://apple.com",
    label="price"
)

# Later: search for relevant chunks
results = chroma.search("How much does iPhone cost?", top_k=5)
# Returns top-5 chunks most similar to the query, ranked by cosine distance

# Or filter by label
price_chunks = chroma.search_by_label("price", top_k=10)

Persistence: embeddings stored on disk, reloaded on next session



### File 3: markdown_archive.py — Persist Chunks as Markdown (Long-Term Storage)

Redis is temporary (45-min cache), Chroma is vector search. This file saves chunks as markdown files for permanent storage & offline access.


CODE:

# Shared_core/memory/markdown_archive.py

import os
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
import json

class MarkdownArchive:
    """Archive chunks as markdown files for persistence & easy human review."""
    
    def __init__(self, archive_dir: str = "./chunk_archive"):
        """
        Args:
            archive_dir: Directory where markdown chunks are saved
                        (default: ./chunk_archive)
        """
        self.archive_dir = Path(archive_dir)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
    
    def _sanitize_filename(self, text: str, max_length: int = 50) -> str:
        """
        Convert text to valid filename (remove special chars).
        
        Args:
            text: Text to convert
            max_length: Max filename length
        
        Returns:
            Sanitized filename (e.g., "best_laptop_under_1000")
        """
        # Keep only alphanumeric and underscores
        sanitized = "".join(c if c.isalnum() or c == "_" else "_" for c in text)
        # Remove consecutive underscores
        while "__" in sanitized:
            sanitized = sanitized.replace("__", "_")
        return sanitized[:max_length]
    
    def save_chunk(
        self,
        chunk_id: str,
        chunk_text: str,
        source_url: str,
        label: str = "general",
        tokens: int = 0,
        metadata: Optional[Dict] = None
    ) -> str:
        """
        Save a chunk as a markdown file.
        
        Args:
            chunk_id: Unique chunk identifier
            chunk_text: Chunk content
            source_url: Where chunk came from
            label: Chunk label (price, review, etc.)
            tokens: Token count for this chunk
            metadata: Additional metadata
        
        Returns:
            Path to saved markdown file
        """
        # Create query-specific subdirectory
        query_dir = self.archive_dir / label
        query_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate filename from chunk text
        filename = self._sanitize_filename(chunk_text) + f"_{chunk_id[:8]}.md"
        filepath = query_dir / filename
        
        # Build markdown content
        markdown = f"""# {label.upper()}: Chunk {chunk_id[:8]}

**Saved:** {datetime.utcnow().isoformat()}

## Metadata
- **Source:** [{source_url}]({source_url})
- **Label:** {label}
- **Tokens:** {tokens}
- **Chunk ID:** {chunk_id}

"""
        
        # Add custom metadata if provided
        if metadata:
            markdown += "## Custom Metadata\n"
            for key, value in metadata.items():
                markdown += f"- **{key}:** {value}\n"
            markdown += "\n"
        
        # Add chunk content
        markdown += f"""## Content

{chunk_text}

---

*This chunk was automatically archived on {datetime.utcnow().isoformat()}*
"""
        
        # Write to file
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(markdown)
        
        return str(filepath)
    
    def save_query_session(
        self,
        query: str,
        chunks: List[Dict],
        results_summary: str
    ) -> str:
        """
        Save an entire query session as an index markdown file.
        Groups all chunks fetched for a query into one readable document.
        
        Args:
            query: User query
            chunks: List of chunk dicts (each with 'text', 'source_url', 'label')
            results_summary: Human-readable summary of findings
        
        Returns:
            Path to saved session file
        """
        # Create session directory
        query_name = self._sanitize_filename(query)
        session_dir = self.archive_dir / f"sessions"
        session_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        session_file = session_dir / f"{query_name}_{timestamp}.md"
        
        # Build session markdown
        markdown = f"""# Query Session: {query}

**Generated:** {datetime.utcnow().isoformat()}

## Summary
{results_summary}

## Chunks Fetched ({len(chunks)} total)

"""
        
        # List all chunks
        for i, chunk in enumerate(chunks):
            source = chunk.get("source_url", "unknown")
            label = chunk.get("label", "general")
            text = chunk.get("text", "")[:200]  # First 200 chars
            
            markdown += f"""### Chunk {i+1}: {label}
- **Source:** [{source}]({source})
- **Preview:** {text}...

"""
        
        # Write session file
        with open(session_file, "w", encoding="utf-8") as f:
            f.write(markdown)
        
        return str(session_file)
    
    def list_chunks_by_label(self, label: str) -> List[str]:
        """
        List all archived chunks with a specific label.
        
        Args:
            label: Label to filter by (e.g., "price")
        
        Returns:
            List of file paths
        """
        label_dir = self.archive_dir / label
        
        if not label_dir.exists():
            return []
        
        return [str(f) for f in label_dir.glob("*.md")]
    
    def get_archive_stats(self) -> Dict:
        """
        Get archive statistics.
        
        Returns:
            {
                "total_chunks": int,
                "total_sessions": int,
                "chunks_by_label": {label: count, ...},
                "archive_size_mb": float
            }
        """
        chunk_files = list(self.archive_dir.glob("**/*.md"))
        session_files = list((self.archive_dir / "sessions").glob("*.md")) if (self.archive_dir / "sessions").exists() else []
        
        # Count chunks by label
        chunks_by_label = {}
        for chunk_file in chunk_files:
            if chunk_file.parent.name != "sessions":
                label = chunk_file.parent.name
                chunks_by_label[label] = chunks_by_label.get(label, 0) + 1
        
        # Calculate size
        total_size = sum(f.stat().st_size for f in chunk_files) / (1024 * 1024)  # Convert to MB
        
        return {
            "total_chunks": len(chunk_files) - len(session_files),
            "total_sessions": len(session_files),
            "chunks_by_label": chunks_by_label,
            "archive_size_mb": round(total_size, 2)
        }
    
    def cleanup_old_archives(self, keep_days: int = 30) -> int:
        """
        Delete archived chunks older than keep_days (optional cleanup).
        
        Args:
            keep_days: Keep only chunks from last N days
        
        Returns:
            Number of files deleted
        """
        from datetime import timedelta
        
        cutoff_time = datetime.utcnow() - timedelta(days=keep_days)
        deleted_count = 0
        
        for chunk_file in self.archive_dir.glob("**/*.md"):
            file_time = datetime.fromtimestamp(chunk_file.stat().st_mtime)
            if file_time < cutoff_time:
                chunk_file.unlink()
                deleted_count += 1
        
        return deleted_count
    
    def export_label_summary(self, label: str, output_file: str) -> None:
        """
        Export all chunks with a label into one compiled markdown file.
        Great for offline review & sharing.
        
        Args:
            label: Label to export
            output_file: Path to save compiled markdown
        """
        label_dir = self.archive_dir / label
        chunk_files = sorted(label_dir.glob("*.md")) if label_dir.exists() else []
        
        compiled = f"# {label.upper()} — Compiled Archive\n\n"
        compiled += f"**Generated:** {datetime.utcnow().isoformat()}\n"
        compiled += f"**Total Chunks:** {len(chunk_files)}\n\n"
        compiled += "---\n\n"
        
        for chunk_file in chunk_files:
            with open(chunk_file, "r", encoding="utf-8") as f:
                compiled += f.read() + "\n\n---\n\n"
        
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(compiled)

Key Concepts:

Concept	Purpose	Used By
save_chunk()	Archive single chunk as markdown file	ChunkProcessor (after labeling)
save_query_session()	Archive entire query + all chunks in one file	End-of-query summary
Folder structure	Organize by label (./price/, ./review/, etc.)	Easy browsing offline
list_chunks_by_label()	Find all chunks of a type	Filtering/review
export_label_summary()	Compile all chunks with label into one doc	Offline sharing + archival
get_archive_stats()	Monitor what's been archived	Size management
cleanup_old_archives()	Delete old data (optional, manual cleanup)	Storage optimization
How It Connects:

ChunkProcessor calls save_chunk() after parsing & labeling each chunk
FinalSynthesizer calls save_query_session() at end of full query to archive results
MarkdownBuilder (Step 4) formats markdown tables; MarkdownArchive persists them

Example usage:

from Shared_core.memory import MarkdownArchive

archive = MarkdownArchive(archive_dir="./chunk_archive")

# Save individual chunk
filepath = archive.save_chunk(
    chunk_id="chunk_abc123",
    chunk_text="iPhone 15 costs $999",
    source_url="https://apple.com",
    label="price",
    tokens=10
)
# Creates: ./chunk_archive/price/iphone_15_costs_abc12345.md

# Save entire session
session = archive.save_query_session(
    query="best laptop",
    chunks=[...],
    results_summary="Found 3 top options"
)
# Creates: ./chunk_archive/sessions/best_laptop_20260322_120000.md

# Compile for offline review
archive.export_label_summary("price", "./price_review.md")

No TTL (unlike Redis): persists forever until manually cleaned
Human-readable markdown: easy to review offline/manually