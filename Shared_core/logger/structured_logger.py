# main logger class


"""
This file creates a logger that writes structured JSON metrics (not plain text).
Each log entry is a complete JSON object with timing, memory, and token counts.
"""


# Shared_core/logger/structured_logger.py

import json
import time
import psutil
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

class StructuredLogger:
    """Logs system metrics (wall_time, RSS delta, token count) as JSON."""
    
    def __init__(self, log_file: str, component_name: str):
        """
        Args:
            log_file: Path to JSON log file (e.g., "./logs/agent_metrics.jsonl")
            component_name: Name of agent/component logging (e.g., "IntentExtractor")
        """
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self.component_name = component_name
        self.process = psutil.Process()
        self.session_start_rss = self.process.memory_info().rss
        
    def log_metric(
        self,
        event_name: str,
        wall_time_ms: float = 0,
        tokens_used: int = 0,
        success: bool = True,
        error_msg: Optional[str] = None,
        metadata: Optional[dict] = None
    ):
        """
        Log a single metric event to JSON file.
        
        Args:
            event_name: e.g., "query_parsed", "chunks_fetched", "ranked_results"
            wall_time_ms: Elapsed time in milliseconds
            tokens_used: LLM tokens consumed (input + output)
            success: Whether operation succeeded
            error_msg: Error message if success=False
            metadata: Additional context (e.g., {"num_sources": 3, "query": "..."})
        """
        current_rss = self.process.memory_info().rss
        rss_delta_mb = (current_rss - self.session_start_rss) / 1024 / 1024
        
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "component": self.component_name,
            "event": event_name,
            "wall_time_ms": round(wall_time_ms, 2),
            "rss_delta_mb": round(rss_delta_mb, 2),
            "tokens_used": tokens_used,
            "success": success,
            "error": error_msg,
            "metadata": metadata or {}
        }
        
        # Append to JSONL file (one JSON object per line)
        with open(self.log_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
    
    def start_timer(self) -> dict:
        """
        Start a timer for measuring elapsed time.
        Returns a dict holding start_time for use with end_timer().
        """
        return {"start_time": time.time()}
    
    def end_timer(self, timer_dict: dict) -> float:
        """
        End a timer and return elapsed time in milliseconds.
        """
        elapsed_sec = time.time() - timer_dict["start_time"]
        return elapsed_sec * 1000  # Convert to milliseconds