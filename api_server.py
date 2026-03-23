from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os
import uvicorn
from Shared_core.tools.etl_processor import ETLProcessorTool

app = FastAPI()

# Input model
class QueryRequest(BaseModel):
    query: str

@app.get("/")
async def get_index():
    return FileResponse("frontend/index.html")

@app.post("/api/query")
async def process_query(request: QueryRequest):
    """
    Main API Endpoint: Uses RealSearchTool + URLFetcher + ETLProcessorTool.
    No Mocks. Returns real summaries and links.
    """
    try:
        print(f"Incoming Real Parsing Request: {request.query}")
        etl = ETLProcessorTool()
        result = await etl.run_pipeline(request.query)
        
        if result.get("status") == "success":
            return result
        else:
            raise HTTPException(status_code=404, detail=result.get("message", "No results"))
            
    except Exception as e:
        print(f"❌ API Failure: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    print("Starting Production API Server (Real Parsing v2.1)...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
