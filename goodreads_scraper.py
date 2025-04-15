import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime
import time  # For adding delays between requests

def get_better_cover_url(title, author):
    """Try to get a better cover image from Open Library"""
    try:
        # Clean up the title and author for the API
        # Remove series information in parentheses
        if '(' in title:
            clean_title = title.split('(')[0].strip()
        else:
            clean_title = title.strip()
            
        # Handle author format (Last, First)
        if ',' in author:
            parts = author.split(',')
            if len(parts) >= 2:
                clean_author = f"{parts[1].strip()} {parts[0].strip()}"
            else:
                clean_author = author.strip()
        else:
            clean_author = author.strip()
        
        # URL encode for the API
        clean_title = clean_title.replace(' ', '+')
        clean_author = clean_author.replace(' ', '+')
        
        # Query Open Library
        search_url = f"https://openlibrary.org/search.json?title={clean_title}&author={clean_author}"
        print(f"Searching Open Library: {search_url}")
        
        response = requests.get(search_url)
        data = response.json()
        
        if data.get('docs') and len(data['docs']) > 0:
            # Get the first result's cover ID
            cover_id = data['docs'][0].get('cover_i')
            if cover_id:
                # Return the large cover URL
                cover_url = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
                print(f"Found better cover for '{clean_title}': {cover_url}")
                return cover_url
            
            # If no cover_i, try ISBN
            for isbn_field in ['isbn', 'lccn', 'oclc', 'olid']:
                if data['docs'][0].get(isbn_field) and len(data['docs'][0][isbn_field]) > 0:
                    identifier = data['docs'][0][isbn_field][0]
                    cover_url = f"https://covers.openlibrary.org/b/{isbn_field}/{identifier}-L.jpg"
                    print(f"Found ISBN cover for '{clean_title}': {cover_url}")
                    return cover_url
    except Exception as e:
        print(f"Error getting better cover for {title}: {e}")
    
    print(f"No better cover found for '{title}'")
    return None

def scrape_goodreads_books(user_id, shelf="read"):
    """Scrape books from a Goodreads shelf and save to JSON"""
    
    books = []
    page = 1
    more_books = True
    
    # Load hidden books list
    hidden_books = []
    if os.path.exists('hidden_books.json'):
        try:
            with open('hidden_books.json', 'r', encoding='utf-8') as f:
                hidden_data = json.load(f)
                hidden_books = hidden_data.get('hidden_books', [])
                print(f"Loaded {len(hidden_books)} hidden books")
        except Exception as e:
            print(f"Error loading hidden books: {e}")
    
    print(f"Scraping Goodreads books for user {user_id}, shelf: {shelf}")
    
    # Add headers to make the request appear more like a regular browser
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    while more_books:
        url = f"https://www.goodreads.com/review/list/{user_id}?shelf={shelf}&page={page}"
        print(f"Fetching page {page} from URL: {url}")
        
        try:
            response = requests.get(url, headers=headers)
            # Check if the request was successful
            response.raise_for_status()
            
            # Debug information
            print(f"Response status code: {response.status_code}")
            
            # Save the HTML response for debugging (only first page)
            if page == 1:
                with open('goodreads_response.html', 'w', encoding='utf-8') as f:
                    f.write(response.text)
                print("Saved HTML response to goodreads_response.html for debugging")
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find all book entries - try different selectors if the original doesn't work
            book_rows = soup.select('tr.bookalike')
            
            if not book_rows:
                print("Alternative selector check: trying different HTML selectors...")
                # Try alternative selectors
                book_rows = soup.select('tr.review')
                
                if not book_rows:
                    book_rows = soup.select('tr[itemtype="http://schema.org/Book"]')
                
                if not book_rows:
                    print("No books found on this page with any selector")
                    more_books = False
                    continue
            
            print(f"Found {len(book_rows)} books on page {page}")
            
            for book in book_rows:
                try:
                    # Extract book data with more robust selectors
                    title_element = book.select_one('td.title a, .title a')
                    title = title_element.text.strip() if title_element else "Unknown Title"
                    
                    # Extract book ID from URL to check against hidden list
                    book_url = title_element['href'] if title_element and 'href' in title_element.attrs else ""
                    book_id = book_url.split('show/')[1].split('-')[0] if 'show/' in book_url else ""
                    
                    # Skip this book if it's in the hidden list
                    if book_id in hidden_books:
                        print(f"Skipping hidden book: {title} (ID: {book_id})")
                        continue
                    
                    # Also check title for Maze Runner series
                    title_lower = title.lower()
                    if any(phrase in title_lower for phrase in ["maze runner", "scorch trials", "kill order", "fever code", "death cure"]):
                        print(f"Skipping Maze Runner book by title: {title}")
                        continue
                    
                    author_element = book.select_one('td.author a, .author a')
                    author = author_element.text.strip() if author_element else "Unknown Author"
                    
                    # Get cover URL from Goodreads as fallback
                    cover_element = book.select_one('td.cover img, .cover img')
                    goodreads_cover = cover_element['src'] if cover_element and 'src' in cover_element.attrs else ""
                    
                    # Try to get a better cover from Open Library
                    better_cover = get_better_cover_url(title, author)
                    cover_url = better_cover if better_cover else goodreads_cover
                    
                    # Try different rating selectors
                    rating_element = book.select_one('td.rating .staticStars, .rating span.staticStars')
                    if rating_element and 'title' in rating_element.attrs:
                        rating_text = rating_element['title']
                        rating = rating_text.split()[1] if len(rating_text.split()) > 1 else rating_text
                    else:
                        # Try another selector for ratings
                        rating_element = book.select_one('.avg_rating')
                        rating = rating_element.text.strip() if rating_element else "0"
                    
                    date_read_element = book.select_one('td.date_read span, .date_read span')
                    date_read = date_read_element.text.strip() if date_read_element else ""
                    
                    goodreads_url = f"https://www.goodreads.com{title_element['href']}" if title_element and 'href' in title_element.attrs else ""
                    
                    books.append({
                        'title': title,
                        'author': author,
                        'cover_url': cover_url,
                        'goodreads_cover': goodreads_cover,  # Keep the original as backup
                        'rating': rating,
                        'date_read': date_read,
                        'goodreads_url': goodreads_url,
                        'book_id': book_id  # Store the ID for future reference
                    })
                    
                    print(f"Added: {title} by {author}")
                    
                    # Add a small delay between Open Library API calls
                    time.sleep(0.5)
                    
                except Exception as e:
                    print(f"Error processing a book: {e}")
            
            page += 1
            
            # Check if there's a next page - try different selectors
            next_page = soup.select_one('a.next_page, .next_page')
            if not next_page:
                print("No next page button found")
                more_books = False
            
            # Add a delay to avoid rate limiting
            time.sleep(2)
            
        except requests.exceptions.RequestException as e:
            print(f"Error making request: {e}")
            more_books = False
    
    # Sort books by date read (newest first)
    books.sort(key=lambda x: x.get('date_read', ''), reverse=True)
    
    # Save to JSON file
    with open('books.json', 'w', encoding='utf-8') as f:
        json.dump({
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'books': books
        }, f, ensure_ascii=False, indent=2)
    
    print(f"Scraping complete. Found {len(books)} books.")
    return books

if __name__ == "__main__":
    # Your Goodreads user ID
    USER_ID = "40486952"  # The ID from your URL
    
    # Run the scraper
    books = scrape_goodreads_books(USER_ID, "read")
    
    # Print summary
    if books:
        print(f"Successfully scraped {len(books)} books")
    else:
        print("No books were scraped. Check the HTML response file for debugging.")