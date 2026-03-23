from .search_real import RealSearchTool
from .fetch import URLFetcher

class ETLProcessorTool:
    """The 'Brain' for the ETL process: Search -> Fetch -> Clean."""
    
    def __init__(self):
        self.searcher = RealSearchTool()
        self.fetcher = URLFetcher()
        
    async def run_pipeline(self, query: str):
        print(f"🔍 Starting Search for: {query}")
        results = await self.searcher.search(query)
        if not results:
            return {"status": "error", "message": "No results found."}
            
        print(f"🌐 Found {len(results)} URLs. Starting Extraction...")
        extracted_data = []
        for res in results:
            print(f"   ∟ Processing: {res.url[:50]}...")
            data = await self.fetcher.fetch_and_extract(res.url)
            if data["text"]:
                extracted_data.append(data)
                
        return {
            "status": "success",
            "sources": extracted_data,
            "links": [{"title": r.title, "url": r.url} for r in results]
        }
