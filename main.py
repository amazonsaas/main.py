from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup
import os
import re
from urllib.parse import urlencode, urlparse

app = FastAPI(title="Amazon Product Verdict API")

# ScraperAPI Key - Pehle Environment se lega, nahi toh yahan manually dalein
API_KEY = os.getenv("SCRAPER_API_KEY", "0ffd10481338d1ba06b0aaa980323394")

class ProductRequest(BaseModel):
    url: str

class VerdictResponse(BaseModel):
    product_title: str
    price: str
    reviews_count: int
    bsr: int
    verdict: str

def validate_amazon_url(url: str) -> bool:
    """Validate if the URL is a valid Amazon product URL"""
    try:
        parsed = urlparse(url)
        # Check if it's a valid URL
        if not parsed.scheme or not parsed.netloc:
            return False
        # Check if it's an Amazon domain
        if 'amazon' not in parsed.netloc.lower():
            return False
        # Check if it looks like a product page (has /dp/ or /gp/product/ or /product/)
        path = parsed.path.lower()
        if '/dp/' in path or '/gp/product/' in path or '/product/' in path:
            return True
        return False
    except Exception:
        return False

def scrape_amazon_page(url: str) -> str:
    """Fetch HTML content from Amazon using ScraperAPI with JavaScript rendering"""
    if not API_KEY or API_KEY == "YOUR_ACTUAL_KEY_HERE":
        raise HTTPException(status_code=500, detail="ScraperAPI Key is missing!")
    
    # Properly encode URL parameters
    params = {
        'api_key': API_KEY,
        'url': url,
        'render': 'true'
    }
    
    try:
        response = requests.get("http://api.scraperapi.com", params=params, timeout=60)
        response.raise_for_status()
        
        # Check if response is empty
        if not response.text or len(response.text.strip()) == 0:
            raise HTTPException(status_code=500, detail="ScraperAPI returned empty response")
        
        # Check for common error indicators in HTML
        html_lower = response.text.lower()
        if 'error' in html_lower and ('access denied' in html_lower or 'blocked' in html_lower):
            raise HTTPException(status_code=500, detail="ScraperAPI: Access denied or blocked by Amazon")
        
        return response.text
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Request timeout: ScraperAPI took too long to respond")
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=503, detail="Connection error: Could not reach ScraperAPI")
    except requests.exceptions.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code if e.response else 500, 
                          detail=f"ScraperAPI HTTP error: {str(e)}")
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch page: {str(e)}")

def extract_product_data(html: str) -> dict:
    """Extract product information from Amazon HTML"""
    if not html or len(html.strip()) == 0:
        return {
            'title': 'Not found',
            'price': 'Not found',
            'reviews_count': 0,
            'bsr': None
        }
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract Product Title - Multiple selectors for different Amazon layouts
    title = None
    title_selectors = [
        '#productTitle',
        'span#productTitle',
        'h1#productTitle',
        'h1.a-size-large.product-title-word-break',
        'h1.a-size-large',
        'h1 span.a-size-large',
        'h1[data-automation-id="title"]',
        '.product-title-word-break',
        '#title_feature_div h1',
        '#titleSection h1',
        'h1.a-text-normal'
    ]
    for selector in title_selectors:
        element = soup.select_one(selector)
        if element:
            title = element.get_text(strip=True)
            if title and len(title) > 0:
                break
    
    # Additional fallback methods
    if not title:
        # Try finding by data attributes
        title_elem = soup.find('span', {'data-automation-id': 'title'})
        if title_elem:
            title = title_elem.get_text(strip=True)
        
        # Try finding any h1 in the product title area
        if not title:
            h1_elements = soup.find_all('h1')
            for h1 in h1_elements:
                text = h1.get_text(strip=True)
                if text and len(text) > 10:  # Reasonable title length
                    title = text
                    break
    
    # Extract Price - Improved extraction with currency
    price = None
    price_selectors = [
        'span.a-price-whole',
        'span.a-price .a-offscreen',
        '#priceblock_ourprice',
        '#priceblock_dealprice',
        'span.a-price.a-text-price.a-size-medium.apexPriceToPay span.a-offscreen',
        '.a-price.aok-align-center span.a-offscreen',
        'span.a-price.aok-align-center.reinventPricePriceToPayMargin.priceToPay span.a-offscreen'
    ]
    
    for selector in price_selectors:
        element = soup.select_one(selector)
        if element:
            price_text = element.get_text(strip=True)
            if price_text:
                price = price_text
                break
    
    # If price not found, try alternative method with currency symbol
    if not price:
        price_container = soup.find('span', class_='a-price')
        if price_container:
            # Try to get the whole price including currency
            whole_price = price_container.find('span', class_='a-price-whole')
            symbol = price_container.find('span', class_='a-price-symbol')
            if whole_price:
                price = whole_price.get_text(strip=True)
                if symbol:
                    price = symbol.get_text(strip=True) + price
            else:
                # Try offscreen price
                offscreen = price_container.find('span', class_='a-offscreen')
                if offscreen:
                    price = offscreen.get_text(strip=True)
    
    # Extract Reviews Count - Multiple methods
    reviews_count = 0
    reviews_selectors = [
        '#acrCustomerReviewText',
        'span#acrCustomerReviewText',
        'a#acrCustomerReviewLink span',
        '#acrCustomerReviewLink',
        '#acrCustomerReviewLink span',
        'a[data-hook="acr-link"]',
        'span[data-hook="acr-link"]',
        '#averageCustomerReviews span',
        '.averageCustomerReviews span',
        'a[href*="#customerReviews"] span',
        '#reviewsMedley span'
    ]
    
    for selector in reviews_selectors:
        element = soup.select_one(selector)
        if element:
            reviews_text = element.get_text(strip=True)
            # Extract number from text like "1,234 ratings", "1,234", "1,234 customer reviews"
            numbers = re.findall(r'[\d,]+', reviews_text.replace(',', ''))
            if numbers:
                try:
                    reviews_count = int(numbers[0].replace(',', ''))
                    if reviews_count > 0:
                        break
                except (ValueError, IndexError):
                    continue
    
    # Alternative: Search in text content for review patterns
    if reviews_count == 0:
        # Look for patterns like "X ratings" or "X customer reviews"
        review_patterns = [
            r'([\d,]+)\s*(?:customer\s*)?reviews?',
            r'([\d,]+)\s*ratings?',
            r'([\d,]+)\s*global\s*ratings?'
        ]
        page_text = soup.get_text()
        for pattern in review_patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                try:
                    reviews_count = int(match.group(1).replace(',', ''))
                    if reviews_count > 0:
                        break
                except (ValueError, IndexError):
                    continue
    
    # Extract BSR (Best Sellers Rank) - Multiple extraction methods
    bsr = None
    
    # Method 1: Find by text content containing "Best Sellers Rank"
    bsr_text_patterns = [
        r'Best\s+Sellers?\s+Rank[:\s]*#?\s*([\d,]+)',
        r'#\s*([\d,]+)\s+in\s+.*?Best\s+Sellers',
        r'Best\s+Sellers?\s+Rank[:\s]*([\d,]+)',
        r'#([\d,]+)\s+in\s+[^#]*Best\s+Sellers'
    ]
    
    # Search in all text elements
    all_text = soup.get_text()
    for pattern in bsr_text_patterns:
        match = re.search(pattern, all_text, re.IGNORECASE)
        if match:
            try:
                bsr = int(match.group(1).replace(',', ''))
                if bsr > 0:
                    break
            except (ValueError, IndexError):
                continue
    
    # Method 2: Find span/li elements containing BSR text
    if bsr is None:
        # Also try specific ID selectors first
        sales_rank_elem = soup.find('span', {'id': 'SalesRank'}) or soup.find('span', {'id': 'productDetails_salesRank'})
        if sales_rank_elem:
            rank_text = sales_rank_elem.get_text()
            bsr_match = re.search(r'#\s*([\d,]+)', rank_text)
            if bsr_match:
                try:
                    bsr = int(bsr_match.group(1).replace(',', ''))
                except (ValueError, IndexError):
                    pass
        
        # Search for elements with BSR-related text
        if bsr is None:
            for elem in soup.find_all(['span', 'li', 'div']):
                text = elem.get_text()
                if 'Best Sellers Rank' in text or ('BSR' in text and 'rank' in text.lower()):
                    # Extract number from the element or its siblings
                    bsr_match = re.search(r'#\s*([\d,]+)', text)
                    if not bsr_match:
                        bsr_match = re.search(r'([\d,]+)\s+in\s+.*?Best\s+Sellers', text, re.IGNORECASE)
                    if not bsr_match:
                        # Just find the first large number in the text
                        numbers = re.findall(r'([\d,]{3,})', text.replace(',', ''))
                        if numbers:
                            try:
                                potential_bsr = int(numbers[0].replace(',', ''))
                                if 1000 < potential_bsr < 10000000:  # Reasonable BSR range
                                    bsr = potential_bsr
                                    break
                            except (ValueError, IndexError):
                                continue
                    else:
                        try:
                            bsr = int(bsr_match.group(1).replace(',', ''))
                            if bsr > 0:
                                break
                        except (ValueError, IndexError):
                            continue
    
    # Method 3: Look in product details section
    if bsr is None:
        product_details = soup.find('div', {'id': 'productDetails_db_sections'}) or \
                         soup.find('div', {'id': 'detailBullets_feature_div'}) or \
                         soup.find('table', {'id': 'productDetails_detailBullets_sections1'}) or \
                         soup.find('div', {'id': 'productDetails_feature_div'})
        
        if product_details:
            details_text = product_details.get_text()
            bsr_match = re.search(r'Best\s+Sellers?\s+Rank[:\s]*#?\s*([\d,]+)', details_text, re.IGNORECASE)
            if bsr_match:
                try:
                    bsr = int(bsr_match.group(1).replace(',', ''))
                except (ValueError, IndexError):
                    pass
    
    # Method 4: Search in table rows (common Amazon structure)
    if bsr is None:
        for row in soup.find_all('tr'):
            row_text = row.get_text()
            if 'Best Sellers Rank' in row_text:
                # Look for number in the same row
                numbers = re.findall(r'([\d,]{3,})', row_text.replace(',', ''))
                if numbers:
                    try:
                        potential_bsr = int(numbers[0].replace(',', ''))
                        if 1000 < potential_bsr < 10000000:  # Reasonable BSR range
                            bsr = potential_bsr
                            break
                    except (ValueError, IndexError):
                        continue
    
    return {
        'title': title or 'Not found',
        'price': price or 'Not found',
        'reviews_count': reviews_count,
        'bsr': bsr
    }

def calculate_verdict(reviews_count: int, bsr: int) -> str:
    """Calculate verdict based on reviews count and BSR"""
    if bsr is None or bsr == 0:
        return '⚠️ RISKY'  # Can't determine without BSR
    
    if bsr < 20000 and reviews_count < 200:
        return '✅ SELL'
    elif reviews_count > 1000:
        return '❌ AVOID'
    else:
        return '⚠️ RISKY'

@app.get("/")
def home():
    return {"status": "API is Running", "docs": "/docs"}

@app.post("/verdict", response_model=VerdictResponse)
def get_verdict(request: ProductRequest):
    """
    Analyze an Amazon product and return verdict
    
    - **url**: Amazon product URL
    """
    if not API_KEY or API_KEY == "YOUR_ACTUAL_KEY_HERE":
        raise HTTPException(status_code=500, detail="ScraperAPI Key is missing!")
    
    # Validate URL format
    if not request.url or not request.url.strip():
        raise HTTPException(status_code=400, detail="URL cannot be empty")
    
    # Validate it's an Amazon URL
    if not validate_amazon_url(request.url):
        raise HTTPException(status_code=400, detail="URL must be a valid Amazon product page (e.g., https://www.amazon.com/dp/PRODUCT_ID)")
    
    try:
        # Scrape the page
        html = scrape_amazon_page(request.url)
        
        # Extract product data
        product_data = extract_product_data(html)
        
        # Calculate verdict
        verdict = calculate_verdict(product_data['reviews_count'], product_data['bsr'])
        
        # Return response
        return VerdictResponse(
            product_title=product_data['title'],
            price=product_data['price'],
            reviews_count=product_data['reviews_count'],
            bsr=product_data['bsr'] if product_data['bsr'] is not None else 0,
            verdict=verdict
        )
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        # Catch any unexpected errors
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
