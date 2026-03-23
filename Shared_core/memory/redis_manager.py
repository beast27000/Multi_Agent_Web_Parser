# Shared_core/memory/redis_manager.py

import redis
import hashlib
import json
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

class RedisManager:
    """Manage caching and deduplication using Redis."""
    
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0, ttl_minutes: int = 45):
        """
        Args:
            host: Redis server host (default: localhost)
            port: Redis server port (default: 6379)
            db: Redis database number (default: 0)
            ttl_minutes: Time-to-live for cached entries in minutes (default: 45)
        """
        try:
            self.client = redis.Redis(host=host, port=port, db=db, decode_responses=True)
            self.client.ping()  # Test connection
            self.connected = True
        except Exception as e:
            print(f"Warning: Redis connection failed ({e}). Caching disabled.")
            self.client = None
            self.connected = False
        
        self.ttl = timedelta(minutes=ttl_minutes)
    
    def _hash_query(self, query: str) -> str:
        """Create MD5 hash of query for cache key."""
        return hashlib.md5(query.encode()).hexdigest()
    
    def cache_get(self, query: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached result for query."""
        if not self.connected:
            return None
        
        try:
            hash_key = self._hash_query(query)
            cached = self.client.get(hash_key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            print(f"Cache get error: {e}")
        
        return None
    
    def cache_set(self, query: str, data: Dict[str, Any]) -> bool:
        """Store result in cache."""
        if not self.connected:
            return False
        
        try:
            hash_key = self._hash_query(query)
            self.client.setex(hash_key, self.ttl, json.dumps(data))
            return True
        except Exception as e:
            print(f"Cache set error: {e}")
        
        return False
    
    def deduplicate_urls(self, urls: list) -> list:
        """Remove duplicate URLs using Redis SET."""
        if not self.connected:
            return list(set(urls))  # Fallback to Python set
        
        try:
            unique_urls = []
            for url in urls:
                if not self.client.sismember("seen_urls", url):
                    unique_urls.append(url)
                    self.client.sadd("seen_urls", url)
            return unique_urls
        except Exception as e:
            print(f"Deduplicate error: {e}")
            return list(set(urls))
    
    def clear_cache(self) -> bool:
        """Clear all cached entries."""
        if not self.connected:
            return False
        
        try:
            self.client.flushdb()
            return True
        except Exception as e:
            print(f"Clear cache error: {e}")
        
        return False
