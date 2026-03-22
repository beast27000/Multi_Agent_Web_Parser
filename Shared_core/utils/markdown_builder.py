# Markdown utilities

# This file builds human-readable markdown tables from agent results (for the final output).

# Shared_core/utils/markdown_builder.py

from typing import List, Dict, Optional
from datetime import datetime

class MarkdownBuilder:
    """Build formatted markdown tables and documents from structured data."""
    
    @staticmethod
    def create_results_table(
        results: List[Dict],
        title: str = "Search Results",
        columns: Optional[List[str]] = None
    ) -> str:
        """
        Create a markdown table from list of result dicts.
        
        Args:
            results: List of dicts (each dict = one row)
            title: Table title
            columns: Column names to include (if None, use all keys from first result)
        
        Returns:
            Markdown table string
        """
        if not results:
            return f"## {title}\n\nNo results found.\n"
        
        # Determine columns
        if columns is None:
            columns = list(results[0].keys())
        
        # Build markdown table
        markdown = f"## {title}\n\n"
        markdown += "| " + " | ".join(columns) + " |\n"
        markdown += "| " + " | ".join(["---"] * len(columns)) + " |\n"
        
        for result in results:
            row_values = []
            for col in columns:
                value = result.get(col, "")
                # Escape pipes in cell values
                value = str(value).replace("|", "\\|")
                row_values.append(value)
            markdown += "| " + " | ".join(row_values) + " |\n"
        
        return markdown
    
    @staticmethod
    def create_comparison_section(
        comparisons: List[Dict],
        metric_name: str = "Comparison Metrics"
    ) -> str:
        """
        Create markdown section for cross-site comparisons.
        
        Args:
            comparisons: List of comparison dicts with 'source', 'metric', 'value'
            metric_name: Section title
        
        Returns:
            Markdown section string
        """
        markdown = f"## {metric_name}\n\n"
        
        for comp in comparisons:
            source = comp.get("source", "Unknown")
            metric = comp.get("metric", "")
            value = comp.get("value", "")
            markdown += f"- **{source}**: {metric} = {value}\n"
        
        return markdown
    
    @staticmethod
    def create_summary_section(
        query: str,
        total_sources: int,
        total_chunks_processed: int,
        top_insight: str
    ) -> str:
        """
        Create markdown summary section at top of doc.
        
        Args:
            query: Original user query
            total_sources: Number of websites fetched
            total_chunks_processed: Total chunks analyzed
            top_insight: Key finding/summary
        
        Returns:
            Markdown section string
        """
        timestamp = datetime.utcnow().isoformat()
        
        markdown = f"""# {query}

**Generated:** {timestamp}

## Summary
{top_insight}

## Metrics
- **Sources:** {total_sources}
- **Chunks Processed:** {total_chunks_processed}
- **Timestamp:** {timestamp}

---

"""
        return markdown
    
    @staticmethod
    def create_full_document(
        query: str,
        summary_insight: str,
        results_table: str,
        comparisons_section: str,
        sources: List[Dict],
        total_chunks: int
    ) -> str:
        """
        Combine all sections into one complete markdown document.
        
        Args:
            query: User query
            summary_insight: Key finding
            results_table: Markdown table from create_results_table()
            comparisons_section: Markdown from create_comparison_section()
            sources: List of source dicts with 'url', 'domain', 'chunks_count'
            total_chunks: Total chunks analyzed
        
        Returns:
            Complete markdown document string
        """
        doc = MarkdownBuilder.create_summary_section(
            query=query,
            total_sources=len(sources),
            total_chunks_processed=total_chunks,
            top_insight=summary_insight
        )
        
        doc += results_table + "\n"
        doc += comparisons_section + "\n"
        
        # Sources section
        doc += "## Sources\n\n"
        for source in sources:
            url = source.get("url", "")
            domain = source.get("domain", "")
            chunks = source.get("chunks_count", 0)
            doc += f"- [{domain}]({url}) — {chunks} chunks\n"
        
        return doc
    
    @staticmethod
    def save_to_file(content: str, output_path: str) -> None:
        """
        Write markdown content to file.
        
        Args:
            content: Markdown string
            output_path: Path to output file (e.g., "./output/result.md")
        """
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)