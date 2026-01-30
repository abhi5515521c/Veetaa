import os
import re
from datetime import datetime
from typing import List, Dict, Any, Optional
from firecrawl import FirecrawlApp
from fallback_service import FallbackScraper
class ScraperService:
    def __init__(self):
        self.api_key = os.getenv("FIRECRAWL_API_KEY")
        self.fallback = FallbackScraper()
        
        # Initialize FirecrawlApp if key is present
        try:
            self.app = FirecrawlApp(api_key=self.api_key) if self.api_key else None
        except Exception as e:
            print(f"Error initializing Firecrawl: {e}")
            self.app = None

    def search_products(self, product_name: str) -> List[Dict[str, Any]]:
        """
        Searches for the product on e-commerce sites.
        Strategy:
        1. Try Firecrawl API (Primary)
        2. If Firecrawl fails or returns empty, switch to Fallback (Scrapy/Requests)
        """
        results = []
        
        # --- STRATEGY 1: FIRECRAWL ---
        if self.app:
            print(f"Scraper: Trying Firecrawl for '{product_name}'...")
            try:
                # We target Indian marketplaces
                query = f"{product_name} price buy online amazon.in flipkart.com"
                
                # Note: Firecrawl params might need adjustment based on version
                # We use a broad search
                params = {
                    "pageOptions": {"fetchPageContent": False},
                    "searchOptions": {"limit": 8}
                }
                fc_results = self.app.search(query, params=params)
                
                # Handle response structure
                items = []
                if isinstance(fc_results, dict) and 'data' in fc_results:
                    items = fc_results['data']
                elif isinstance(fc_results, list):
                    items = fc_results
                
                if items:
                    print(f"Scraper: Firecrawl found {len(items)} results.")
                    results = self._parse_results(items)
                else:
                    print("Scraper: Firecrawl returned 0 results.")
            
            except Exception as e:
                print(f"Scraper: Firecrawl API Failed: {e}")
        
        # --- STRATEGY 2: FALLBACK (Scrapy) ---
        # Trigger if no results found yet (or if Firecrawl failed)
        if not results:
            print("Scraper: Switching to Fallback (Scrapy/Requests)...")
            try:
                fallback_results = self.fallback.search(product_name)
                if fallback_results:
                    print(f"Scraper: Fallback found {len(fallback_results)} results.")
                    results.extend(fallback_results)
                else:
                    print("Scraper: Fallback returned 0 results.")
            except Exception as e:
                print(f"Scraper: Fallback Failed: {e}")

        return results

    def scrape_page(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Uses Firecrawl /scrape endpoint to get full page details, falling back to local.
        """
        # 1. Firecrawl
        if self.app:
            try:
                print(f"Scraper: Firecrawl scraping {url}")
                data = self.app.scrape_url(url, params={'pageOptions': {'onlyMainContent': True}})
                if data:
                    content = data.get('markdown', '') or data.get('content', '')
                    metadata = data.get('metadata', {})
                    price = self._extract_price(content[:2000])
                    
                    return {
                        "price": price,
                        "title": metadata.get('title', ''),
                        "description": metadata.get('description', '') or content[:500],
                        "url": url,
                        "currency": "INR"
                    }
            except Exception as e:
                print(f"Firecrawl Scrape Error: {e}")
        
        # 2. Fallback
        return self.fallback.parse_page(url)

    def _parse_results(self, items: List[Any]) -> List[Dict[str, Any]]:
        snapshots = []
        
        for item in items:
            url = item.get('url', '')
            title = item.get('title', '')
            description = item.get('description', '')
            content = f"{title} {description}"
            
            # Identify Marketplace
            marketplace = None
            if 'amazon.in' in url:
                marketplace = "Amazon"
            elif 'flipkart.com' in url:
                marketplace = "Flipkart"
            elif 'jiomart' in url:
                marketplace = "JioMart"
            elif 'croma' in url:
                marketplace = "Croma"
            else:
                 marketplace = "Online Store"
            # Attempt to extract price from snippet
            price = self._extract_price(content)
            
            # Extract Image (Best effort from metadata)
            images = []
            if 'og:image' in item.get('metadata', {}):
                 images.append(item['metadata']['og:image'])
            
            snapshots.append({
                "marketplace": marketplace,
                "price": price,
                "currency": "INR",
                "url": url,
                "description": description if description else title,
                "images": images,
                "last_updated": datetime.utcnow(),
                "in_stock": price > 0,
                "original_price": None,
                "discount_percentage": None
            })
        
        return snapshots
    def _extract_price(self, text: str) -> float:
        if not text:
            return 0.0
            
        # Normalize text
        text = text.replace('\xa0', ' ') # Remove non-breaking spaces
        
        # Regex for Indian Currency
        # Support: ₹ 1,200 | Rs. 1,200 | INR 1200 | 12,000/-
        patterns = [
            r'(?:₹|Rs\.?|INR)\s*([\d,]+(?:\.\d{1,2})?)',  # Symbols prefix
            r'Price:\s*([\d,]+)',                         # "Price: 1200"
        ]
        
        for pat in patterns:
            matches = re.findall(pat, text, re.IGNORECASE)
            for match in matches:
                try:
                    # Cleanup: remove commas
                    clean_val = match.replace(',', '').strip()
                    # Check if it's a valid float
                    val = float(clean_val)
                    
                    # Heuristics to filter junk (years, phone nums, small nums)
                    if val > 50 and val != 2023 and val != 2024 and val != 2025:
                        return val
                except:
                    continue
                    
        return 0.0
