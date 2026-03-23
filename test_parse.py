import asyncio
from Shared_core.tools.etl_processor import ETLProcessorTool

async def main():
    print("🚀 Initializing Real Parsing Project...")
    etl = ETLProcessorTool()
    query = "Search about latest iphone 16 features and price"
    print(f"🔍 Searching and Parsing for: {query}")
    
    result = await etl.run_pipeline(query)
    
    if result.get("status") == "success":
        print("\n✅ Found Real Content!")
        for idx, source in enumerate(result.get("sources", [])):
            print(f"\n--- Resource {idx+1}: {source['url']} ---")
            print(f"Content Sample: {source['text'][:500]}...")
            
        print("\n📎 Reference Links:")
        for link in result.get("links", []):
            print(f"- {link['title']}: {link['url']}")
    else:
        print(f"❌ Error: {result.get('message', 'Unknown error')}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"🔥 Critical Failure: {e}")
