# User agents, headers

# When Playwright fetches websites, servers can detect it as a bot. This file generates realistic browser headers to look human.

# Shared_core/utils/stealth_headers.py

import random
from typing import Dict

class StealthHeadersManager:
    """Generate realistic browser headers to avoid bot detection."""
    
    # Popular user agents (rotated to appear as different browsers)
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.2) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1.1 Safari/605.1.15",
    ]
    
    # Realistic accept-language headers (common locales)
    ACCEPT_LANGUAGES = [
        "en-US,en;q=0.9",
        "en-GB,en;q=0.8",
        "en-US,en;q=0.9,es;q=0.8",
        "en-US,en;q=0.9,fr;q=0.8",
    ]
    
    @staticmethod
    def get_random_headers() -> Dict[str, str]:
        """
        Generate a random set of realistic browser headers.
        Call this before every request to appear as a different client.
        
        Returns:
            Dict of HTTP headers
        """
        return {
            "User-Agent": random.choice(StealthHeadersManager.USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": random.choice(StealthHeadersManager.ACCEPT_LANGUAGES),
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        }
    
    @staticmethod
    def get_headers_for_domain(domain: str) -> Dict[str, str]:
        """
        Get headers customized for a specific domain (add domain-specific referrer).
        
        Args:
            domain: Target domain (e.g., "amazon.com")
        
        Returns:
            Dict of HTTP headers with domain-specific referer
        """
        headers = StealthHeadersManager.get_random_headers()
        headers["Referer"] = f"https://www.google.com/search?q={domain}"
        return headers
    
    @staticmethod
    def get_headers_with_custom_ua(user_agent: str) -> Dict[str, str]:
        """
        Get headers with a specific user agent override.
        
        Args:
            user_agent: Custom user agent string
        
        Returns:
            Dict of HTTP headers with custom UA
        """
        headers = StealthHeadersManager.get_random_headers()
        headers["User-Agent"] = user_agent
        return headers


# Convenience functions for quick usage
def get_random_headers() -> Dict[str, str]:
    """Get random stealth headers."""
    return StealthHeadersManager.get_random_headers()


def get_headers_for_domain(domain: str) -> Dict[str, str]:
    """Get headers for a specific domain."""
    return StealthHeadersManager.get_headers_for_domain(domain)