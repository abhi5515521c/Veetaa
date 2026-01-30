from pathlib import Path
from dotenv import load_dotenv
import os
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
# ---- Load .env safely ----
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
print("DEBUG FIRECRAWL_API_KEY:", "SET" if FIRECRAWL_API_KEY else "MISSING")
print("DEBUG OPENAI_API_KEY:", "SET" if OPENAI_API_KEY else "MISSING")
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
app = FastAPI(title="VEETAA Prototype API")
# ---- CORS ----
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ---- Serve Frontend ----
# We will mount this at the end of the file or use a specific route for root
# ---- Global error handler ----
@app.exception_handler(Exception)
async def debug_exception_handler(request: Request, exc: Exception):
    import traceback
    print("FULL TRACEBACK:")
    traceback.print_exc()
    return JSONResponse(status_code=500, content={"error": str(exc)})
# ---- Models ----
class SearchRequest(BaseModel):
    product_name: str = Field(..., min_length=2)
    marketplaces: List[str] = ["Amazon", "Flipkart"]
    country: str = "IN"
class PriceSnapshot(BaseModel):
    marketplace: str
    price: float
    currency: str
    url: str
    description: Optional[str] = None
    images: List[str] = []
    last_updated: datetime
    in_stock: bool = True
    original_price: Optional[float] = None
    discount_percentage: Optional[float] = None
class InspectRequest(BaseModel):
    url: str
class ProductInfo(BaseModel):
    flash_pid: str
    brand: str
    product_name: str
    normalized_title: str
    category: Optional[str]
    confidence_score: float
class SearchResponse(BaseModel):
    product: ProductInfo
    prices: List[PriceSnapshot]
    best_price: Optional[PriceSnapshot]
    metadata: Dict[str, Any]
# ---- Helpers ----
def generate_flash_pid(product_name: str, brand: str) -> str:
    import hashlib
    content = f"{brand.lower()}:{product_name.lower()}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]
# ---- Health ----
@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "firecrawl": bool(FIRECRAWL_API_KEY),
        "openai": bool(OPENAI_API_KEY),
        "timestamp": datetime.utcnow().isoformat()
    }
from scraper_service import ScraperService
# Initialize Service
scraper = ScraperService()
# ---- Stage 1 search (With Firecrawl Integration) ----
@app.post("/api/search", response_model=SearchResponse)
def search(req: SearchRequest):
    brand = req.product_name.split()[0]
    flash_pid = generate_flash_pid(req.product_name, brand)
    # 1. Try to scrape real data
    real_prices = scraper.search_products(req.product_name)
    
    # Adapt to Pydantic model
    price_snapshots = []
    best_price_snapshot = None
    min_price = float('inf')
    for p in real_prices:
        snapshot = PriceSnapshot(
            marketplace=p["marketplace"],
            price=p["price"],
            currency=p["currency"],
            url=p["url"],
            last_updated=p["last_updated"]
        )
        price_snapshots.append(snapshot)
        
        if p["price"] > 0 and p["price"] < min_price:
            min_price = p["price"]
            best_price_snapshot = snapshot
    # 2. Confidence Score logic (Placeholder)
    confidence = 0.8 if price_snapshots else 0.1
    product = ProductInfo(
        flash_pid=flash_pid,
        brand=brand,
        product_name=req.product_name,
        normalized_title=req.product_name,
        category="Electronics", # Placeholder
        confidence_score=confidence
    )
    return SearchResponse(
        product=product,
        prices=price_snapshots,
        best_price=best_price_snapshot,
        metadata={
            "stage": "2",
            "note": "Live Scraping via Firecrawl" if price_snapshots else "No results found or Scraper inactive",
            "timestamp": datetime.utcnow().isoformat()
        }
    )
# ---- Serve Frontend ----
app.mount("/", StaticFiles(directory="veetaa-frontend", html=True), name="static")
# ---- Inspect Endpoint ----
@app.post("/api/inspect")
def inspect_url(req: InspectRequest):
    print(f"Inspecting URL: {req.url}")
    
    # 1. Try Firecrawl Scrape first (Best for description/content)
    try:
        data = scraper.scrape_page(req.url)
        if data:
            return data
    except Exception as e:
        print(f"Inspect Error (Firecrawl): {e}")
    # 2. Fallback
    try:
        data = scraper.fallback.parse_page(req.url)
        return data
    except Exception as e:
        print(f"Inspect Error (Fallback): {e}")
        return {"error": "Could not scrape URL"}
if __name__ == "__main__":
    import uvicorn
    print("Starting server at http://127.0.0.1:8001")
    uvicorn.run(app, host="127.0.0.1", port=8001)