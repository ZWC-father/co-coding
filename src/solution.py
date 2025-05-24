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
            try:
                response = requests.get(url)
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                print(f"Error fetching page {page}: {str(e)}", file=sys.stderr)
                sys.exit(1)

            soup = BeautifulSoup(response.text, 'html.parser')
            quote_containers = soup.find_all('div', class_='quote')

            if not quote_containers:
                break

            for container in quote_containers:
                quote_data = {}

                text = container.find('span', class_='text')
                if text:
                    quote_data['text'] = text.get_text(strip=True).strip('"')

                author = container.find('small', class_='author')
                if author:
                    quote_data['author'] = author.get_text(strip=True)

                tags = container.find('div', class_='tags')
                tag_list = []
                if tags:
                    for tag in tags.find_all('a', class_='tag'):
                        tag_text = tag.get_text(strip=True)
                        if tag_text:
                            tag_list.append(tag_text)
                quote_data['tags'] = tag_list

                if 'text' in quote_data or 'author' in quote_data:
                    quotes.append(quote_data)

            next_button = soup.find('li', class_='next')
            if not next_button:
                break

            page += 1

    except Exception as e:
        print(f"Error during scraping: {str(e)}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(quotes, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    scrape_quotes()