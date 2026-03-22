"""
 Persist Chunks as Markdown (Long-Term Storage)

Redis is temporary (45-min cache), Chroma is vector search. This file saves chunks as markdown files for permanent storage & offline access.
"""

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