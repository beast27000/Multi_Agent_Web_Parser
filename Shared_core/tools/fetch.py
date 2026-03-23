import asyncio
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from typing import Optional, List, Dict

class URLFetcher:
    """Tim-style Real Parser: Fetch + Content Extraction."""
    
    async def fetch_and_extract(self, url: str) -> Dict[str, str]:
        """Fetch URL and extract clean text from semantic tags."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.set_extra_http_headers({
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                })
                await page.goto(url, wait_until="networkidle", timeout=15000)
                try:
                    await page.wait_for_selector("p, article, main", timeout=5000)
                except:
                    pass
                
                html = await page.content()
                soup = BeautifulSoup(html, 'html.parser')
                for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
                    tag.decompose()
                
                content = []
                for tag in soup.find_all(['h1', 'h2', 'h3', 'p']):
                    text = tag.get_text().strip()
                    if len(text) > 20:
                        content.append(text)
                
                return {
                    "url": url,
                    "text": "\n\n".join(content)[:8000],
                    "status": "success"
                }
            except Exception as e:
                return {"url": url, "text": "", "status": f"failed: {e}"}
            finally:
                await browser.close()
