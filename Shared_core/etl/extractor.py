#  fetch raw HTML

"""
The Concept
The Extractor is the first stage of your ETL pipeline. It takes raw HTML fetched from websites and converts it into clean, usable text. Think of it as a "HTML → Text converter" that:

Removes noise (scripts, styles, ads, navigation menus)
Extracts semantic content (headings, paragraphs, lists, tables)
Preserves structure (relationships between sections)
Adds metadata (URLs, timestamps, source identifiers)
Handles encoding (UTF-8, special characters)
The Extractor doesn't split into chunks yet — that's the Transformer's job. It just produces clean, structured text ready for processing.
"""


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