# Shared_core/memory/chroma_manager.py

# This manages embeddings: stores chunk vectors so you can find similar chunks by meaning (not just keyword search).

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