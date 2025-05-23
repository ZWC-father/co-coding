import sys
import json
import requests
from bs4 import BeautifulSoup

def scrape_quotes():
    base_url = "http://quotes.toscrape.com"
    quotes = []

    try:
        page = 1
        while True:
            url = f"{base_url}/page/{page}/"
            response = requests.get(url)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            quote_elements = soup.select('.quote')

            if not quote_elements:
                break

            for quote in quote_elements:
                text = quote.select_one('.text').get_text(strip=True).strip('“”')
                author = quote.select_one('.author').get_text(strip=True)
                tags = [tag.get_text(strip=True) for tag in quote.select('.tag')]

                quotes.append({
                    'author': author,
                    'text': text,
                    'tags': tags
                })

            page += 1

    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"Error processing data: {e}", file=sys.stderr)
        return []

    return quotes

if __name__ == "__main__":
    quotes = scrape_quotes()
    print(json.dumps(quotes, ensure_ascii=False))