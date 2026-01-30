import requests
from fake_useragent import UserAgent
import urllib.parse
from datetime import datetime
import time
import random
import re
from bs4 import BeautifulSoup
from scrapy import Selector

class FallbackScraper:
    def __init__(self):
        self.ua = UserAgent()
        self.session = requests.Session()
        # Common headers to look like a browser
        self.session.headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })

    def search(self, product_name: str):
        print(f"Fallback Scraper: Searching for '{product_name}'...")
        results = []
        
        # 1. Search Engine Aggregation (DuckDuckGo) - Most reliable for finding links/prices across multiple sites
        print("Fallback: Attempting Multi-Source Search (Bing/DDG)...")
        search_results = self.scrape_search_engine(product_name)
        results.extend(search_results)

        # 2. Direct Marketplace Scraping (Amazon/Flipkart) - High risk of blocking, but we try casually
        if len(results) < 2:
            print("Fallback: Search engine results low, attempting direct scrape...")
            try:
                # Add delay
                time.sleep(random.uniform(1, 2))
                amz_results = self.scrape_amazon(product_name)
                results.extend(amz_results)
            except Exception as e:
                print(f"Amazon Error: {e}")

            try:
                time.sleep(random.uniform(1, 2))
                fk_results = self.scrape_flipkart(product_name)
                results.extend(fk_results)
            except Exception as e:
                print(f"Flipkart Error: {e}")

        # Deduplicate
        unique_results = []
        seen_urls = set()
        for r in results:
            if r['url'] not in seen_urls:
                unique_results.append(r)
                seen_urls.add(r['url'])

        return unique_results

    def get_random_header(self):
        return {
            'User-Agent': self.ua.random,
            'Referer': 'https://www.google.com/'
        }

    def scrape_search_engine(self, query):
        """
        Scrapes DuckDuckGo HTML to find price snippets key marketplaces.
        """
        products = []
        try:
            url = "https://html.duckduckgo.com/html/"
            q = f"{query} price india buy online"
            
            # Using POST for DDG HTML
            resp = self.session.post(url, data={'q': q}, headers=self.get_random_header(), timeout=15)
            
            if resp.status_code != 200:
                print(f"DDG returned {resp.status_code}")
                return []
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # DDG result items
            results = soup.select('.result')
            
            for res in results[:12]:
                title_tag = res.select_one('.result__a')
                snippet_tag = res.select_one('.result__snippet')
                
                if not title_tag: continue
                
                title = title_tag.get_text(strip=True)
                link = title_tag['href']
                snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""
                full_text = f"{title} {snippet}"
                
                # Identify Marketplace
                marketplace = self._identify_marketplace(link)
                
                # Price extraction
                price = self._parse_price(full_text)
                
                # Filter: Must be a known marketplace OR have a valid price
                if marketplace or price > 0:
                    products.append({
                        "marketplace": marketplace if marketplace else "Online Store",
                        "price": price,
                        "currency": "INR",
                        "url": link,
                        "last_updated": datetime.utcnow(),
                        "in_stock": True,
                        "original_price": None,
                        "discount_percentage": None
                    })
                    
        except Exception as e:
            print(f"Search Engine Scrape Error: {e}")
            
        return products

    def scrape_amazon(self, query):
        print("Fallback: Scraping Amazon Direct...")
        products = []
        try:
            base_url = "https://www.amazon.in/s"
            params = {'k': query}
            url = f"{base_url}?{urllib.parse.urlencode(params)}"
            
            response = self.session.get(url, headers=self.get_random_header(), timeout=10)
            if response.status_code != 200: return []

            sel = Selector(text=response.text)
            
            for item in sel.css('div.s-search-result')[:4]:
                title = item.css('h2 span::text').get()
                if not title: continue

                price_text = item.css('.a-price .a-offscreen::text').get()
                price = self._parse_price(price_text)
                
                link = item.css('h2 a::attr(href)').get()
                full_link = f"https://www.amazon.in{link}" if link else ""

                # Image Extraction
                img = item.css('.s-image::attr(src)').get()
                images = [img] if img else []

                if price > 0:
                    products.append({
                        "marketplace": "Amazon",
                        "price": price,
                        "currency": "INR",
                        "url": full_link,
                        "images": images,
                        "last_updated": datetime.utcnow(),
                        "in_stock": True,
                        "original_price": None,
                        "discount_percentage": None
                    })
        except Exception:
            pass
        return products

    def scrape_flipkart(self, query):
        print("Fallback: Scraping Flipkart Direct...")
        products = []
        try:
            base_url = "https://www.flipkart.com/search"
            params = {'q': query}
            url = f"{base_url}?{urllib.parse.urlencode(params)}"
            
            response = self.session.get(url, headers=self.get_random_header(), timeout=10)
            if response.status_code != 200: return []

            sel = Selector(text=response.text)
            
            # Grid/List selector strategies
            cards = sel.css('div._1AtVbE') 
            
            count = 0
            for card in cards:
                if count >= 4: break
                price_text = card.css('div._30jeq3::text').get()
                if not price_text: continue

                # Look for link
                link_tag = card.css('a._1fQZEK') or card.css('a.s1Q9rs') or card.css('a.wjcEIp')
                if not link_tag: continue
                
                link = link_tag.attrib.get('href', '')
                full_link = f"https://www.flipkart.com{link}" if link else ""

                # Image Extraction
                img = card.css('img._396cs4::attr(src)').get() or card.css('img._2r_T1I::attr(src)').get()
                images = [img] if img else []

                price = self._parse_price(price_text)
                
                if price > 0:
                    products.append({
                        "marketplace": "Flipkart",
                        "price": price,
                        "currency": "INR",
                        "url": full_link,
                        "images": images,
                        "last_updated": datetime.utcnow(),
                        "in_stock": True,
                        "original_price": None,
                        "discount_percentage": None
                    })
                    count += 1
        except Exception:
            pass
        return products

    def _identify_marketplace(self, url):
        u = url.lower()
        if 'amazon.in' in u: return 'Amazon'
        if 'flipkart.com' in u: return 'Flipkart'
        if 'croma.com' in u: return 'Croma'
        if 'reliancedigital' in u: return 'Reliance Digital'
        if 'jiomart' in u: return 'JioMart'
        if 'tatacliq' in u: return 'Tata Cliq'
        return None

    def parse_page(self, url: str):
        """
        Scrape a specific URL for details
        """
        print(f"Fallback: Parsing Page {url}")
        try:
            resp = self.session.get(url, headers=self.get_random_header(), timeout=10)
            if resp.status_code != 200: return None
            
            sel = Selector(text=resp.text)
            
            # Generic Extractors
            # Title
            title = sel.css('h1::text').get() or sel.css('title::text').get() or ""
            title = title.strip()
            
            # Meta Description
            desc = sel.css('meta[name="description"]::attr(content)').get() or ""
            
            # Price (Try multiple selectors for Amazon/Flipkart/General)
            price_text = (
                sel.css('.a-price .a-offscreen::text').get() or # Amazon
                sel.css('div._30jeq3._16Jk6d::text').get() or # Flipkart
                sel.css('.price::text').get() or
                sel.css('[itemprop="price"]::text').get()
            )
            
            price = self._parse_price(price_text)
            # Try searching whole body if selector fails (expensive but useful fallback)
            if price == 0:
                 price = self._parse_price(resp.text[:5000])

            return {
                "price": price,
                "title": title,
                "description": desc,
                "url": url,
                "currency": "INR"
            }
        except Exception as e:
            print(f"Fallback Parse Error: {e}")
            return None

    def _parse_price(self, text):
        if not text: return 0.0
        try:
            # Cleanup
            text = text.replace('\xa0', ' ').strip()
            
            # patterns
            # 1. Standard currency prefix: ₹ 1,200
            # 2. Suffix: 1200 Rs
            # 3. Just symbol: ₹1200
            patterns = [
                 r'(?:₹|Rs\.?|INR)\s*([\d,]+(?:\.\d{1,2})?)',
                 r'([\d,]+)\s*(?:Rs\.?|INR)'
            ]

            for pat in patterns:
                matches = re.findall(pat, text, re.IGNORECASE)
                for m in matches:
                    try:
                        clean = m.replace(',', '')
                        val = float(clean)
                        # Filter out unlikely prices or years
                        if val > 49 and val < 10000000: # Max 1 crore cap to avoid phone numbers
                             return val
                    except:
                        continue
        except:
            pass
        return 0.0
