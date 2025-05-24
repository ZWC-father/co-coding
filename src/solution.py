import sys
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

def fetch_quotes():
    url = "http://quotes.toscrape.com/"
    try:
        response = requests.get(url)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {str(e)}", file=sys.stderr)
        sys.exit(1)

    soup = BeautifulSoup(response.text, 'html.parser')
    quotes = soup.find_all('div', class_='quote')

    result = []
    for quote in quotes:
        try:
            text = quote.find('span', class_='text').get_text(strip=True)
            author = quote.find('small', class_='author').get_text(strip=True)
            tags = [tag.get_text(strip=True) for tag in quote.find_all('a', class_='tag')]

            result.append({
                "author": author,
                "text": text,
                "tags": tags
            })
        except AttributeError as e:
            print(f"Warning: Failed to parse a quote - {str(e)}", file=sys.stderr)
            continue

    return sorted(result, key=lambda x: x['author'])

def main():
    quotes = fetch_quotes()
    print(json.dumps(quotes, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()