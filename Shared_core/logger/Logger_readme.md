Step 3: Logger System — Structured Metrics Tracking

Your system needs observability: How long did each agent take? How much memory was used? How many tokens? This step teaches JSON-based logging.

### File 1: structured_logger.py — Central Logging Class

This file creates a logger that writes structured JSON metrics (not plain text). Each log entry is a complete JSON object with timing, memory, and token counts.

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
        wall_time_ms: float,
        tokens_used: int,
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

        Key Concepts:

Concept	Purpose	Used By
StructuredLogger class	Singleton logger for one component	Each agent (IntentExtractor, etc.)
log_metric()	Record one event with timing + memory + tokens	ETL pipeline + agent steps
wall_time_ms	Elapsed time in milliseconds	Performance profiling
rss_delta_mb	Memory increase since session start	Resource monitoring
tokens_used	LLM tokens (input + output combined)	Cost tracking + token accounting
JSONL format	One JSON object per line; grep-friendly	Log aggregation + analysis
start_timer() / end_timer()	Helper methods for timing blocks	Agent code (context managers)
How It Connects:

settings.py provides log_dir and json_log_file → StructuredLogger reads these
constants.py provides MAX_TOKENS_PER_CALL → agents pass token counts to log_metric()
Each agent creates a StructuredLogger instance and calls log_metric() after every major step

Example usage (not taught yet, but shows flow):

logger = StructuredLogger(settings.log_dir + "/agent_metrics.jsonl", "IntentExtractor")
timer = logger.start_timer()
# ... do work ...
elapsed_ms = logger.end_timer(timer)
logger.log_metric("intent_extracted", elapsed_ms, tokens_used=150)

Output file (agent_metrics.jsonl) is JSONL format—each line is a complete JSON object for easy parsing

### File 2: json_exporter.py — Query & Analyze JSON Logs

This file reads your JSONL log file and provides helper methods to extract insights (total tokens used, slowest component, error count, etc.).

# Shared_core/logger/json_exporter.py

import json
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from collections import defaultdict

class JSONExporter:
    """Read & analyze JSONL log files for metrics and insights."""
    
    def __init__(self, log_file: str):
        """
        Args:
            log_file: Path to JSONL log file (e.g., "./logs/agent_metrics.jsonl")
        """
        self.log_file = Path(log_file)
    
    def load_logs(self) -> List[Dict]:
        """
        Load all log entries from JSONL file.
        Each line is one JSON object representing an event.
        
        Returns:
            List of log entry dicts
        """
        if not self.log_file.exists():
            return []
        
        logs = []
        with open(self.log_file, "r") as f:
            for line in f:
                if line.strip():
                    logs.append(json.loads(line))
        return logs
    
    def total_tokens(self) -> int:
        """Sum all tokens used across all logged events."""
        logs = self.load_logs()
        return sum(log.get("tokens_used", 0) for log in logs)
    
    def total_wall_time_sec(self) -> float:
        """Sum all wall_time_ms across all events, return in seconds."""
        logs = self.load_logs()
        total_ms = sum(log.get("wall_time_ms", 0) for log in logs)
        return total_ms / 1000
    
    def component_stats(self) -> Dict[str, Dict]:
        """
        Aggregate stats per component (IntentExtractor, SearchPlanner, etc.).
        
        Returns:
            {
                "IntentExtractor": {
                    "events": 5,
                    "total_tokens": 750,
                    "total_wall_time_ms": 1200,
                    "avg_wall_time_ms": 240,
                    "errors": 0
                },
                ...
            }
        """
        logs = self.load_logs()
        stats = defaultdict(lambda: {
            "events": 0, "total_tokens": 0, "total_wall_time_ms": 0, "errors": 0
        })
        
        for log in logs:
            component = log.get("component", "unknown")
            stats[component]["events"] += 1
            stats[component]["total_tokens"] += log.get("tokens_used", 0)
            stats[component]["total_wall_time_ms"] += log.get("wall_time_ms", 0)
            if not log.get("success", True):
                stats[component]["errors"] += 1
        
        # Calculate averages
        for component in stats:
            events = max(stats[component]["events"], 1)  # Avoid division by zero
            stats[component]["avg_wall_time_ms"] = stats[component]["total_wall_time_ms"] / events
        
        return dict(stats)
    
    def slowest_events(self, limit: int = 5) -> List[Dict]:
        """
        Return the N slowest events by wall_time_ms.
        
        Args:
            limit: How many events to return
        
        Returns:
            List of log entries sorted by wall_time_ms descending
        """
        logs = self.load_logs()
        sorted_logs = sorted(logs, key=lambda x: x.get("wall_time_ms", 0), reverse=True)
        return sorted_logs[:limit]
    
    def errors(self) -> List[Dict]:
        """
        Return all events where success=False.
        
        Returns:
            List of failed log entries with their error messages
        """
        logs = self.load_logs()
        return [log for log in logs if not log.get("success", True)]
    
    def export_summary_txt(self, output_file: str):
        """
        Export a human-readable summary report.
        
        Args:
            output_file: Path to write summary (e.g., "./logs/summary.txt")
        """
        total_tokens = self.total_tokens()
        total_time_sec = self.total_wall_time_sec()
        stats = self.component_stats()
        errors = self.errors()
        
        summary = f"""
=== Agent Metrics Summary ===
Generated: {datetime.utcnow().isoformat()}

Total Execution Time: {total_time_sec:.2f} seconds
Total Tokens Used: {total_tokens}
Total Errors: {len(errors)}

--- Per-Component Breakdown ---
"""
        for component, data in sorted(stats.items()):
            summary += f"\n{component}:\n"
            summary += f"  Events: {data['events']}\n"
            summary += f"  Tokens: {data['total_tokens']}\n"
            summary += f"  Wall Time: {data['total_wall_time_ms']:.0f}ms (avg: {data['avg_wall_time_ms']:.1f}ms)\n"
            summary += f"  Errors: {data['errors']}\n"
        
        if errors:
            summary += "\n--- Errors ---\n"
            for error_log in errors:
                summary += f"\n{error_log.get('component')}/{error_log.get('event')}: {error_log.get('error')}\n"
        
        with open(output_file, "w") as f:
            f.write(summary)

Key Concepts:

Concept	Purpose	Used By
load_logs()	Parse JSONL file into Python dicts	All analysis methods
total_tokens()	Track cumulative LLM token spend	Cost accounting + profiling
component_stats()	Per-agent breakdown (events, tokens, latency)	Performance benchmarking
slowest_events()	Find bottlenecks (slowest N operations)	Optimization targets
errors()	Filter only failed events	Debugging + error tracking
export_summary_txt()	Generate human-readable report	Stakeholder communication
JSONL format	One JSON per line = easy to parse + grep-friendly	Log aggregation systems
How It Connects:

StructuredLogger writes JSONL logs; JSONExporter reads them
Example workflow:

# During/after agent run:
logger = StructuredLogger("./logs/agent_metrics.jsonl", "IntentExtractor")
logger.log_metric("query_parsed", wall_time_ms=234, tokens_used=120)

# After run completes, analyze:
exporter = JSONExporter("./logs/agent_metrics.jsonl")
print(f"Total tokens: {exporter.total_tokens()}")
print(f"Slowest step: {exporter.slowest_events(1)}")
exporter.export_summary_txt("./logs/summary.txt")

component_stats() helps identify which agent is slowest/most expensive
Logs are versioned (timestamp per entry) → can compare runs over time
JSONL format: can pipe to grep, jq, or data analysis tools