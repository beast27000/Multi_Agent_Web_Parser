# JSON output

"""
This file reads your JSONL log file and provides helper methods to extract insights (total tokens used, slowest component, error count, etc.).
"""

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