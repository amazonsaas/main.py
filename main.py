from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl
import requests
from bs4 import BeautifulSoup
import re

app = FastAPI(title="Amazon Product Verdict API")

# ScraperAPI configuration
SCRAPERAPI_KEY = "0ffd10481338d1ba06b0aaa980323394"
SCRAPERAPI_URL = "http://api.scraperapi.com"

class VerdictRequest(BaseModel):
    url: HttpUrl

class VerdictResponse(BaseModel):
    product_title: str
    price: str
    reviews_count: int
    bsr: int
    verdict: str

def scrape_amazon_page(url: str) -> str:
    """Fetch HTML content from Amazon using ScraperAPI with JavaScript rendering"""
    params = {
        'api_key': SCRAPERAPI_KEY,
        'url': url,
        'render': 'true'  # Enable JavaScript rendering for Amazon
    }
    
    try:
        response = requests.get(SCRAPERAPI_URL, params=params, timeout=60)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch page: {str(e)}")

def extract_product_data(html: str) -> dict:
    """Extract product information from Amazon HTML"""
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
    if not title or title == 'Not found':
        # Try finding by data attributes
        title_elem = soup.find('span', {'data-automation-id': 'title'})
        if title_elem:
            title = title_elem.get_text(strip=True)
        
        # Try finding any h1 in the product title area
        if not title or title == 'Not found':
            h1_elements = soup.find_all('h1')
            for h1 in h1_elements:
                text = h1.get_text(strip=True)
                if text and len(text) > 10:  # Reasonable title length
                    title = text
                    break
    
    # Extract Price
    price = None
    price_selectors = [
        'span.a-price-whole',
        'span.a-price .a-offscreen',
        '#priceblock_ourprice',
        '#priceblock_dealprice',
        'span.a-price.a-text-price.a-size-medium.apexPriceToPay span.a-offscreen',
        '.a-price.aok-align-center span.a-offscreen'
    ]
    for selector in price_selectors:
        element = soup.select_one(selector)
        if element:
            price_text = element.get_text(strip=True)
            if price_text:
                price = price_text
                break
    
    # If price not found, try alternative method
    if not price:
        price_elem = soup.find('span', class_='a-price-whole')
        if price_elem:
            price = price_elem.get_text(strip=True)
            # Try to get currency symbol
            currency = soup.find('span', class_='a-price-symbol')
            if currency:
                price = currency.get_text(strip=True) + price
    
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
        '#reviewsMedley span',
        'span.a-size-base'
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
                except ValueError:
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
                except ValueError:
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
            except ValueError:
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
                except ValueError:
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
                        except ValueError:
                            continue
                else:
                    try:
                        bsr = int(bsr_match.group(1).replace(',', ''))
                        if bsr > 0:
                            break
                    except ValueError:
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
                except ValueError:
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
                    except ValueError:
                        continue
    
    return {
        'title': title or 'Not found',
        'price': price or 'Not found',
        'reviews_count': reviews_count,
        'bsr': bsr
    }

def calculate_verdict(reviews_count: int, bsr: int) -> str:
    """Calculate verdict based on reviews count and BSR"""
    if bsr is None:
        return '⚠️ RISKY'  # Can't determine without BSR
    
    if bsr < 20000 and reviews_count < 200:
        return '✅ SELL'
    elif reviews_count > 1000:
        return '❌ AVOID'
    else:
        return '⚠️ RISKY'

@app.get("/")
def read_root():
    return {
        "message": "Amazon Product Verdict API",
        "endpoint": "/verdict",
        "usage": "POST /verdict with JSON body: {\"url\": \"https://amazon.com/...\"}"
    }

@app.post("/verdict", response_model=VerdictResponse)
async def get_verdict(request: VerdictRequest):
    """
    Analyze an Amazon product and return verdict
    
    - **url**: Amazon product URL
    """
    url_str = str(request.url)
    
    # Validate it's an Amazon URL
    if 'amazon' not in url_str.lower():
        raise HTTPException(status_code=400, detail="URL must be an Amazon product page")
    
    # Scrape the page
    html = scrape_amazon_page(url_str)
    
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
