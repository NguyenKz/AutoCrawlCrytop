import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
import time
import csv
import os
import argparse
import sys
from urllib.parse import urlparse, urljoin

def get_article_content(article_url, headers, extract_images=False):
    """
    Fetches the full content of an article from its URL
    
    Parameters:
    - article_url: The URL of the article
    - headers: HTTP headers for the request
    - extract_images: Whether to extract image URLs from the article
    
    Returns:
    - Dictionary with article content and images (if extract_images is True)
    - String with article content (if extract_images is False)
    """
    try:
        # Send HTTP request to the article
        response = requests.get(article_url, headers=headers)
        response.raise_for_status()
        
        # Parse HTML content
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Remove some non-content elements
        for element in soup.select('header, footer, nav, aside, .sidebar, .comments, .related, .share, .social, script, style, [role="banner"], [role="navigation"]'):
            element.decompose()
        
        # Try different approaches to find the main content
        content_container = None
        
        # Approach 1: Look for article or main content elements with specific classes
        content_selectors = [
            'article', 'main', '.post-content', '.entry-content', '.article-content', '.content',
            '.article__body', '.story-body', '.post-body', '.article-body', '.news-content',
            '[itemprop="articleBody"]', '[property="content:encoded"]'
        ]
        for selector in content_selectors:
            containers = soup.select(selector)
            for container in containers:
                if container and len(container.text.strip()) > 200:
                    content_container = container
                    break
            if content_container:
                break
        
        # Approach 2: Look for large text blocks in divs or sections
        if not content_container or len(content_container.text.strip()) < 200:
            for container in soup.find_all(['div', 'section']):
                if len(container.text.strip()) > 500:  # Likely main content
                    paragraphs = container.find_all('p')
                    if len(paragraphs) > 3:  # Multiple paragraphs indicate article content
                        content_container = container
                        break
        
        # Process the content
        content = "Could not extract article content."
        images = []
        
        # Extract images from the whole document if we couldn't find a specific content container
        if not content_container:
            if extract_images:
                # Extract images from the whole page as fallback
                images = extract_article_images(soup, article_url)
            return {"content": content, "images": images} if extract_images else content
        
        # Clean up the content - remove unwanted elements
        for element in content_container.select('.share, .social, .related, .recommended, .advertisements, .ad, .ads'):
            element.decompose()
        
        # Extract images if requested
        if extract_images:
            images = extract_article_images(content_container, article_url)
        
        # Extract paragraphs
        paragraphs = content_container.find_all('p')
        
        # If we have paragraphs, join them
        if paragraphs and len(paragraphs) > 1:
            content = "\n\n".join([p.text.strip() for p in paragraphs if p.text.strip()])
        else:
            # If no paragraphs, use the whole content
            content = content_container.text.strip()
            
        # Clean up the content - normalize whitespace
        content = "\n".join([line.strip() for line in content.splitlines() if line.strip()])
        
        return {"content": content, "images": images} if extract_images else content
        
    except Exception as e:
        error_msg = f"Error fetching article content: {str(e)}"
        return {"content": error_msg, "images": []} if extract_images else error_msg

def extract_article_images(container, base_url):
    """
    Extract image URLs from an article container
    
    Parameters:
    - container: BeautifulSoup element containing the article content
    - base_url: The base URL for resolving relative URLs
    
    Returns:
    - List of image dictionaries with URL, alt text, etc.
    """
    images = []
    
    # Find all img tags
    img_tags = container.find_all('img')
    
    for img in img_tags:
        # Skip tiny images, icons, avatars, etc.
        if img.get('width') and int(img.get('width')) < 100:
            continue
        if img.get('height') and int(img.get('height')) < 100:
            continue
        
        # Skip icons and small images by class/id
        skip_classes = ['icon', 'avatar', 'logo', 'thumbnail', 'thumb', 'badge']
        if any(cls in str(img.get('class', '')).lower() for cls in skip_classes):
            continue
        
        # Get image URL - try different attributes
        img_url = None
        for attr in ['src', 'data-src', 'data-lazy-src', 'data-original']:
            if img.get(attr):
                img_url = img[attr]
                break
        
        if not img_url:
            continue
        
        # Resolve relative URLs
        if not img_url.startswith(('http://', 'https://')):
            img_url = urljoin(base_url, img_url)
        
        # Get alt text and other attributes
        alt_text = img.get('alt', '').strip()
        title = img.get('title', '').strip()
        
        # Add the image to our list
        images.append({
            'url': img_url,
            'alt': alt_text,
            'title': title
        })
    
    # Also look for background images in style attributes
    for element in container.find_all(lambda tag: tag.has_attr('style')):
        style = element['style']
        if 'background-image' in style:
            # Extract URL from background-image: url('...')
            import re
            match = re.search(r"background-image\s*:\s*url\(['\"](.*?)['\"]\)", style)
            if match:
                img_url = match.group(1)
                if not img_url.startswith(('http://', 'https://')):
                    img_url = urljoin(base_url, img_url)
                
                images.append({
                    'url': img_url,
                    'alt': '',
                    'title': ''
                })
    
    return images

def download_image(img_url, folder='images', filename=None):
    """
    Download an image from a URL and save it to disk
    
    Parameters:
    - img_url: URL of the image to download
    - folder: Folder to save the image in
    - filename: Optional filename, if not provided will be derived from URL
    
    Returns:
    - Path to the saved image or None if download failed
    """
    try:
        # Create the folder if it doesn't exist
        os.makedirs(folder, exist_ok=True)
        
        # Generate filename if not provided
        if not filename:
            # Extract filename from URL or generate a random one
            parsed_url = urlparse(img_url)
            path = parsed_url.path
            filename = os.path.basename(path)
            
            # If filename is empty or doesn't have an extension
            if not filename or '.' not in filename:
                # Generate a filename based on the current time
                ext = '.jpg'  # Default extension
                filename = f"image_{int(time.time())}_{hash(img_url) % 10000}{ext}"
        
        # Full path to save the image
        full_path = os.path.join(folder, filename)
        
        # Download the image
        response = requests.get(img_url, stream=True, timeout=10)
        response.raise_for_status()
        
        # Check if it's actually an image
        content_type = response.headers.get('Content-Type', '')
        if not content_type.startswith('image/'):
            return None
        
        # Save the image
        with open(full_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        return full_path
    
    except Exception as e:
        print(f"Error downloading image {img_url}: {str(e)}")
        return None

def get_latest_crypto_news(max_articles=5, show_progress=True, extract_images=False, download_images=False, images_folder='crypto_news_images'):
    """
    Scrapes the latest posts from crypto.news website
    Returns a list of dictionaries containing news details
    
    Parameters:
    - max_articles: Maximum number of articles to fetch (0 for unlimited)
    - show_progress: Whether to display progress messages
    - extract_images: Whether to extract image URLs from articles
    - download_images: Whether to download the images to local storage
    - images_folder: Folder to save downloaded images in
    """
    url = "https://crypto.news/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        # Send HTTP request to the website
        if show_progress:
            print("Connecting to crypto.news...")
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raise exception for HTTP errors
        
        # Parse HTML content
        if show_progress:
            print("Parsing homepage content...")
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # First approach: Look for the "Latest" section
        latest_section = soup.find('h2', string=lambda t: t and 'Latest' in t)
        
        # Alternative approach: Find all article elements directly
        articles = []
        if latest_section:
            # Find the container with latest news items
            latest_container = latest_section.find_next('div')
            articles = latest_container.find_all('article') if latest_container else []
        
        # If no articles found using the first approach, try a more general approach
        if not articles:
            # Try to find articles in the main content area
            articles = soup.find_all('article')
            
            # If still no articles, try to find news items with different structure
            if not articles:
                # Look for news items containing article text
                news_sections = soup.find_all(['div', 'li'], class_=lambda c: c and any(term in str(c).lower() for term in ['news', 'post', 'article', 'item', 'story']))
                for section in news_sections:
                    if section.find('a') and (section.find('h3') or section.find('h4') or section.text.strip()):
                        articles.append(section)
        
        # Try another approach if still no articles found
        if not articles:
            # Try to find div elements containing links that might be news items
            top_stories = soup.find_all('div', class_=lambda c: c and ('top-stories' in str(c).lower() or 'stories' in str(c).lower()))
            if top_stories:
                for story_section in top_stories:
                    story_items = story_section.find_all(['div', 'li', 'article'], recursive=True)
                    for item in story_items:
                        if item.find('a'):
                            articles.append(item)
            
            # Try finding the Read more links that often appear in news items
            read_more_links = soup.find_all('a', string=lambda t: t and 'Read more' in t)
            for link in read_more_links:
                parent = link.find_parent(['div', 'article', 'li'])
                if parent and parent not in articles:
                    articles.append(parent)
        
        # Print debug info if no articles found
        if not articles:
            print("Debug: Could not find article elements on the page.")
            print("Possible sections found:")
            for section in soup.find_all(['h1', 'h2', 'h3']):
                print(f"- {section.text.strip()}")
            return []
        
        if show_progress:
            print(f"Found {len(articles)} potential news items.")
        
        # Extract news items
        news_items = []
        processed_urls = set()  # To avoid duplicates
        
        # Limit the number of articles to process if specified
        if max_articles > 0:
            articles = articles[:max_articles]
        
        # Extract thumbnail images from homepage listings
        for i, article in enumerate(articles):
            # Extract thumbnail image from the article preview
            thumbnail_img = None
            img_element = article.find('img')
            if img_element and 'src' in img_element.attrs:
                thumbnail_url = img_element['src']
                # Check for lazy-loaded images
                if thumbnail_url.endswith('lazy-placeholder.png') and 'data-src' in img_element.attrs:
                    thumbnail_url = img_element['data-src']
                
                if thumbnail_url and not thumbnail_url.endswith(('lazy-placeholder.png', 'blank.gif')):
                    if not thumbnail_url.startswith(('http://', 'https://')):
                        thumbnail_url = urljoin(url, thumbnail_url)
                    thumbnail_img = {
                        'url': thumbnail_url,
                        'alt': img_element.get('alt', ''),
                        'title': img_element.get('title', ''),
                        'is_thumbnail': True
                    }
            
            # Extract URL first to check for duplicates
            url_element = article.find('a')
            if url_element and 'href' in url_element.attrs:
                article_url = url_element['href'] 
                # Add domain if it's a relative URL
                if article_url.startswith('/'):
                    article_url = urljoin(url, article_url)
                elif not article_url.startswith(('http://', 'https://')):
                    article_url = urljoin(url, article_url)
                
                # Skip duplicate URLs
                if article_url in processed_urls:
                    continue
                processed_urls.add(article_url)
            else:
                article_url = None
                
            # Extract title - try multiple approaches
            title = "No title"
            # First look for heading elements
            title_element = article.find(['h2', 'h3', 'h4']) 
            if title_element:
                title = title_element.text.strip()
            else:
                # Try to find a title attribute or class
                title_link = article.find('a', class_=lambda c: c and ('title' in str(c).lower() or 'heading' in str(c).lower()))
                if title_link:
                    title = title_link.text.strip()
                else:
                    # Use the link text if it looks like a title
                    link = article.find('a')
                    if link and link.text.strip() and len(link.text.strip()) > 10:
                        title = link.text.strip()
                        
            # Extract time
            timestamp = "Unknown time"
            time_element = article.find('time') or article.find(lambda tag: tag.name and tag.get('datetime'))
            if time_element:
                timestamp = time_element.text.strip()
            else:
                # Try to find time-like text
                for span in article.find_all(['span', 'div', 'p']):
                    text = span.text.strip().lower()
                    if any(time_word in text for time_word in ['ago', 'hour', 'minute', 'second', 'day', 'week']):
                        if len(text) < 20:  # Likely a timestamp, not article text
                            timestamp = span.text.strip()
                            break
            
            # Extract categories/tags
            tags = []
            tag_elements = article.find_all('a', class_=lambda c: c and any(tag in str(c).lower() for tag in ['category', 'tag', 'topic']))
            for tag_element in tag_elements:
                tag = tag_element.text.strip()
                if tag and len(tag) < 30:  # Avoid getting entire paragraphs
                    tags.append(tag)
            
            # Extract summary
            summary = ""
            # Look for paragraph elements
            summary_element = article.find('p')
            if summary_element and summary_element.text.strip() and len(summary_element.text.strip()) > 10:
                summary = summary_element.text.strip()
                # Avoid using the timestamp as a summary
                if summary.lower() in timestamp.lower() or timestamp.lower() in summary.lower():
                    summary = ""
            
            # If no summary found, try other elements
            if not summary:
                summary_div = article.find('div', class_=lambda c: c and ('summary' in str(c).lower() or 'excerpt' in str(c).lower() or 'content' in str(c).lower()))
                if summary_div and summary_div.text.strip() and len(summary_div.text.strip()) > 10:
                    summary = summary_div.text.strip()
            
            # Fetch full article content if URL is available
            content = ""
            article_images = []
            
            if article_url:
                if show_progress:
                    progress = f"[{i+1}/{len(articles)}]"
                    print(f"{progress} Fetching content for: {title}")
                
                # Get article content and images if requested
                if extract_images:
                    result = get_article_content(article_url, headers, extract_images=True)
                    content = result["content"]
                    article_images = result["images"]
                    
                    # Add the thumbnail to the beginning of the images list if it exists
                    if thumbnail_img and thumbnail_img['url'] not in [img['url'] for img in article_images]:
                        article_images.insert(0, thumbnail_img)
                else:
                    content = get_article_content(article_url, headers)
            
            # Download images if requested
            local_images = []
            if download_images and article_images:
                article_folder = os.path.join(images_folder, f"article_{i+1}")
                if show_progress:
                    print(f"Downloading {len(article_images)} images for article: {title}")
                
                for j, img in enumerate(article_images):
                    img_url = img['url']
                    img_filename = f"image_{j+1}_{os.path.basename(urlparse(img_url).path)}"
                    local_path = download_image(img_url, folder=article_folder, filename=img_filename)
                    
                    if local_path:
                        local_images.append({
                            'url': img_url,
                            'local_path': local_path,
                            'alt': img.get('alt', ''),
                            'title': img.get('title', ''),
                            'is_thumbnail': img.get('is_thumbnail', False)
                        })
            
            # Create news item dictionary
            news_item = {
                "title": title,
                "url": article_url,
                "timestamp": timestamp,
                "tags": tags,
                "summary": summary,
                "content": content,
                "scraped_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "images": article_images if extract_images else [],
                "local_images": local_images if download_images else []
            }
            
            news_items.append(news_item)
        
        if show_progress:
            print(f"Successfully scraped {len(news_items)} news articles.")
        
        return news_items
    
    except requests.exceptions.RequestException as e:
        return {"error": f"Request error: {str(e)}"}
    except Exception as e:
        return {"error": f"An error occurred: {str(e)}"}

def display_news(news_items, show_full_content=False, show_images=False):
    """
    Formats and prints the news items
    
    Parameters:
    - news_items: List of news items to display
    - show_full_content: Whether to show the full article content
    - show_images: Whether to display image information
    """
    if isinstance(news_items, dict) and "error" in news_items:
        print(f"Error: {news_items['error']}")
        return
    
    print(f"\n{'=' * 80}")
    print(f"LATEST CRYPTOCURRENCY NEWS FROM CRYPTO.NEWS")
    print(f"Retrieved at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 80}\n")
    
    if not news_items:
        print("No news items found.")
        return
    
    for i, item in enumerate(news_items, 1):
        print(f"{i}. {item['title']}")
        print(f"   Time: {item['timestamp']}")
        if item['tags']:
            print(f"   Tags: {', '.join(item['tags'])}")
        if item['summary']:
            # Truncate long summaries
            summary = item['summary']
            if len(summary) > 150:
                summary = summary[:147] + "..."
            print(f"   Summary: {summary}")
        if item['url']:
            print(f"   URL: {item['url']}")
        
        # Display image information if available and requested
        if show_images and "images" in item and item["images"]:
            print(f"\n   --- IMAGES ({len(item['images'])}) ---")
            for j, img in enumerate(item["images"], 1):
                print(f"   {j}. {img['url']}")
                if img.get('alt') and img['alt'].strip():
                    print(f"      Alt: {img['alt']}")
        
        # Display local image paths if available
        if show_images and "local_images" in item and item["local_images"]:
            print(f"\n   --- DOWNLOADED IMAGES ({len(item['local_images'])}) ---")
            for j, img in enumerate(item["local_images"], 1):
                print(f"   {j}. Saved to: {img['local_path']}")
        
        # Print article content
        if item['content']:
            print("\n   --- ARTICLE CONTENT ---")
            content_preview = item['content']
            if not show_full_content and len(content_preview) > 500:
                content_preview = content_preview[:500] + "...\n(content truncated for display)"
            print(f"   {content_preview}")
            
        print()

def save_to_json(news_items, filename="crypto_news.json"):
    """
    Save news items to a JSON file
    """
    if isinstance(news_items, dict) and "error" in news_items:
        return False
    
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(news_items, f, ensure_ascii=False, indent=4)
        
        # Print information about images in JSON
        if not isinstance(news_items, dict):
            total_images = sum(len(item.get("images", [])) for item in news_items)
            total_local_images = sum(len(item.get("local_images", [])) for item in news_items)
            print(f"JSON file includes {total_images} image URLs and {total_local_images} local image paths")
        
        return True
    except Exception as e:
        print(f"Error saving to JSON: {str(e)}")
        return False

def save_to_csv(news_items, filename="crypto_news.csv"):
    """
    Save news items to a CSV file
    """
    if isinstance(news_items, dict) and "error" in news_items:
        return False
    
    try:
        if not news_items:
            return False
        
        # Get fieldnames from the first item
        fieldnames = news_items[0].keys()
        
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(news_items)
        return True
    except Exception as e:
        print(f"Error saving to CSV: {str(e)}")
        return False

def save_to_text(news_items, filename="crypto_news.txt"):
    """
    Save news items to a plain text file
    One article per section with clear formatting
    """
    if isinstance(news_items, dict) and "error" in news_items:
        return False
    
    try:
        if not news_items:
            return False
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"LATEST CRYPTOCURRENCY NEWS FROM CRYPTO.NEWS\n")
            f.write(f"Retrieved at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{'=' * 80}\n\n")
            
            for i, item in enumerate(news_items, 1):
                f.write(f"{i}. {item['title']}\n")
                f.write(f"   Time: {item['timestamp']}\n")
                
                if item['tags']:
                    f.write(f"   Tags: {', '.join(item['tags'])}\n")
                
                if item['url']:
                    f.write(f"   URL: {item['url']}\n")
                
                if item['summary']:
                    f.write(f"   Summary: {item['summary']}\n")
                
                # Write image information if available
                if "images" in item and item["images"]:
                    f.write(f"\n   --- IMAGES ({len(item['images'])}) ---\n")
                    for j, img in enumerate(item["images"], 1):
                        f.write(f"   {j}. {img['url']}\n")
                        if img.get('alt') and img['alt'].strip():
                            f.write(f"      Alt: {img['alt']}\n")
                
                # Write local image paths if available
                if "local_images" in item and item["local_images"]:
                    f.write(f"\n   --- DOWNLOADED IMAGES ({len(item['local_images'])}) ---\n")
                    for j, img in enumerate(item["local_images"], 1):
                        f.write(f"   {j}. Saved to: {img['local_path']}\n")
                
                if item['content']:
                    f.write("\n   --- ARTICLE CONTENT ---\n")
                    lines = item['content'].split('\n')
                    for line in lines:
                        f.write(f"   {line}\n")
                
                f.write(f"\n{'=' * 80}\n\n")
        
        return True
    except Exception as e:
        print(f"Error saving to text file: {str(e)}")
        return False

def create_html_report(news_items, filename="crypto_news_report.html"):
    """
    Create an HTML report with images and article content
    """
    if isinstance(news_items, dict) and "error" in news_items:
        return False
    
    try:
        if not news_items:
            return False
        
        with open(filename, 'w', encoding='utf-8') as f:
            # Write HTML header
            f.write("""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cryptocurrency News Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { color: #333; border-bottom: 2px solid #eee; padding-bottom: 10px; }
        .article { margin: 30px 0; border: 1px solid #ddd; padding: 20px; border-radius: 5px; }
        .article h2 { margin-top: 0; color: #2c3e50; }
        .article-meta { font-size: 0.9em; color: #7f8c8d; margin-bottom: 15px; }
        .tag { display: inline-block; background: #eee; padding: 2px 8px; margin-right: 5px; border-radius: 3px; font-size: 0.8em; }
        .summary { font-style: italic; background: #f9f9f9; padding: 10px; border-left: 3px solid #ddd; }
        .images { display: flex; flex-wrap: wrap; gap: 10px; margin: 15px 0; }
        .image-container { margin: 10px 0; }
        .image-container img { max-width: 100%; max-height: 400px; border: 1px solid #ddd; }
        .image-caption { font-size: 0.8em; color: #666; margin-top: 5px; }
        .content { line-height: 1.7; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Cryptocurrency News Report</h1>
        <p>Retrieved at: """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """</p>
""")
            
            # Write each article
            for item in news_items:
                f.write('<div class="article">\n')
                
                # Title with link
                if item['url']:
                    f.write(f'<h2><a href="{item["url"]}" target="_blank">{item["title"]}</a></h2>\n')
                else:
                    f.write(f'<h2>{item["title"]}</h2>\n')
                
                # Article metadata
                f.write('<div class="article-meta">\n')
                f.write(f'<span>Time: {item["timestamp"]}</span>\n')
                
                # Tags
                if item['tags']:
                    f.write('<div class="tags">\n')
                    for tag in item['tags']:
                        f.write(f'<span class="tag">{tag}</span>\n')
                    f.write('</div>\n')
                
                f.write('</div>\n')
                
                # Summary
                if item['summary']:
                    f.write(f'<div class="summary">{item["summary"]}</div>\n')
                
                # Images section
                has_images = False
                
                # Local images first (if available)
                if "local_images" in item and item["local_images"]:
                    has_images = True
                    f.write('<div class="images">\n')
                    for img in item["local_images"]:
                        # Get the relative path for HTML
                        rel_path = os.path.relpath(img['local_path'], os.path.dirname(filename))
                        f.write('<div class="image-container">\n')
                        f.write(f'<img src="{rel_path.replace(os.sep, "/")}" alt="{img["alt"]}">\n')
                        if img['alt'] or img['title']:
                            caption = img['alt'] if img['alt'] else img['title']
                            f.write(f'<p class="image-caption">{caption}</p>\n')
                        f.write('</div>\n')
                    f.write('</div>\n')
                # Remote images if no local images
                elif "images" in item and item["images"] and not has_images:
                    has_images = True
                    f.write('<div class="images">\n')
                    for img in item["images"]:
                        f.write('<div class="image-container">\n')
                        f.write(f'<img src="{img["url"]}" alt="{img["alt"]}">\n')
                        if img['alt'] or img.get('title', ''):
                            caption = img['alt'] if img['alt'] else img.get('title', '')
                            f.write(f'<p class="image-caption">{caption}</p>\n')
                        f.write('</div>\n')
                    f.write('</div>\n')
                
                # Article content
                if item['content']:
                    f.write('<div class="content">\n')
                    # Convert newlines to <p> tags
                    paragraphs = item['content'].split('\n\n')
                    for paragraph in paragraphs:
                        if paragraph.strip():
                            f.write(f'<p>{paragraph.strip()}</p>\n')
                    f.write('</div>\n')
                
                f.write('</div>\n')
            
            # Close HTML
            f.write("""    </div>
</body>
</html>""")
        
        return True
    except Exception as e:
        print(f"Error creating HTML report: {str(e)}")
        return False

def parse_arguments():
    """
    Parse command-line arguments
    """
    parser = argparse.ArgumentParser(description='Scrape latest cryptocurrency news from crypto.news')
    parser.add_argument('--json', help='Save results to JSON file', action='store_true')
    parser.add_argument('--csv', help='Save results to CSV file', action='store_true')
    parser.add_argument('--text', help='Save results to text file', action='store_true')
    parser.add_argument('--html', help='Create HTML report with images', action='store_true')
    parser.add_argument('--output', help='Output filename prefix', default='crypto_news')
    parser.add_argument('--quiet', help='Suppress console output', action='store_true')
    parser.add_argument('--debug', help='Enable debug output', action='store_true')
    parser.add_argument('--limit', type=int, help='Limit the number of articles to fetch', default=5)
    parser.add_argument('--full', help='Display full article content', action='store_true')
    parser.add_argument('--images', help='Extract images from articles', action='store_true')
    parser.add_argument('--download-images', help='Download images to local storage', action='store_true')
    parser.add_argument('--images-folder', help='Folder to save downloaded images in', default='crypto_news_images')
    
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_arguments()
    
    if not args.quiet:
        print("Fetching the latest news from crypto.news...")
    
    # If download-images is specified, we need to enable images extraction as well
    extract_images = args.images or args.download_images
    
    # Get the news articles
    news = get_latest_crypto_news(
        max_articles=args.limit, 
        show_progress=not args.quiet,
        extract_images=extract_images,
        download_images=args.download_images,
        images_folder=args.images_folder
    )
    
    # Display the news if not in quiet mode
    if not args.quiet:
        display_news(news, show_full_content=args.full, show_images=extract_images)
    
    # Save to files if requested
    if args.json:
        json_filename = f"{args.output}.json"
        if save_to_json(news, json_filename):
            print(f"News saved to {json_filename}")
    
    if args.csv:
        csv_filename = f"{args.output}.csv"
        if save_to_csv(news, csv_filename):
            print(f"News saved to {csv_filename}")
    
    if args.text:
        text_filename = f"{args.output}.txt"
        if save_to_text(news, text_filename):
            print(f"News saved to {text_filename}")
    
    if args.html:
        html_filename = f"{args.output}_report.html"
        if create_html_report(news, html_filename):
            print(f"HTML report saved to {html_filename}")