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
    """Fetch HTML content from Amazon using ScraperAPI"""
    params = {
        'api_key': SCRAPERAPI_KEY,
        'url': url
    }
    
    try:
        response = requests.get(SCRAPERAPI_URL, params=params, timeout=30)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch page: {str(e)}")

def extract_product_data(html: str) -> dict:
    """Extract product information from Amazon HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract Product Title
    title = None
    title_selectors = [
        '#productTitle',
        'h1.a-size-large.product-title-word-break',
        'span#productTitle',
        'h1 span.a-size-large'
    ]
    for selector in title_selectors:
        element = soup.select_one(selector)
        if element:
            title = element.get_text(strip=True)
            break
    
    if not title:
        # Fallback: try to find any h1 with product title
        h1 = soup.find('h1', {'id': 'productTitle'})
        if h1:
            title = h1.get_text(strip=True)
    
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
    
    # Extract Reviews Count
    reviews_count = 0
    reviews_selectors = [
        '#acrCustomerReviewText',
        'span#acrCustomerReviewText',
        'a#acrCustomerReviewLink span',
        '#acrCustomerReviewLink'
    ]
    for selector in reviews_selectors:
        element = soup.select_one(selector)
        if element:
            reviews_text = element.get_text(strip=True)
            # Extract number from text like "1,234 ratings" or "1,234"
            numbers = re.findall(r'[\d,]+', reviews_text.replace(',', ''))
            if numbers:
                try:
                    reviews_count = int(numbers[0].replace(',', ''))
                    break
                except ValueError:
                    continue
    
    # Extract BSR (Best Sellers Rank)
    bsr = None
    # BSR is usually in a section with "Best Sellers Rank"
    bsr_section = soup.find('span', string=re.compile('Best Sellers Rank', re.I))
    if bsr_section:
        # Find the parent and look for rank number
        parent = bsr_section.find_parent()
        if parent:
            bsr_text = parent.get_text()
            # Look for pattern like "#123,456" or "#123456"
            bsr_match = re.search(r'#\s*([\d,]+)', bsr_text)
            if bsr_match:
                try:
                    bsr = int(bsr_match.group(1).replace(',', ''))
                except ValueError:
                    pass
    
    # Alternative BSR extraction method
    if bsr is None:
        bsr_elements = soup.find_all('span', class_=re.compile('rank', re.I))
        for elem in bsr_elements:
            text = elem.get_text()
            if 'Best Sellers Rank' in text or 'BSR' in text:
                numbers = re.findall(r'[\d,]+', text.replace(',', ''))
                if numbers:
                    try:
                        bsr = int(numbers[0].replace(',', ''))
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
