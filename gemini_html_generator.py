import base64
import os
import json
import mimetypes
from dotenv import load_dotenv
import google.generativeai as genai
import re

# Load environment variables from .env file
load_dotenv()

def save_binary_file(file_name, data):
    """Save binary data to a file."""
    with open(file_name, "wb") as f:
        f.write(data)

def save_text_file(file_name, text):
    """Save text data to a file."""
    with open(file_name, "w", encoding="utf-8") as f:
        f.write(text)

def load_json_data(file_path):
    """Load data from a JSON file."""
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

def get_image_base64(image_path):
    """Convert local image to base64 encoding."""
    try:
        with open(image_path, "rb") as img_file:
            img_data = img_file.read()
            mime_type, _ = mimetypes.guess_type(image_path)
            if not mime_type:
                mime_type = 'image/jpeg'  # Default to JPEG if type can't be determined
            base64_encoded = base64.b64encode(img_data).decode('utf-8')
            return f"data:{mime_type};base64,{base64_encoded}"
    except Exception as e:
        print(f"Error encoding image {image_path}: {e}")
        return None

def process_images_for_prompt(article_data):
    """Process the images data to include in the prompt."""
    images_info = []
    
    # Choose local images if available, otherwise use online images
    image_source = article_data.get('local_images', []) or article_data.get('images', [])
    
    if not image_source:
        return "No images available for this article."
    
    for i, img in enumerate(image_source):
        image_description = {
            "index": i + 1,
            "alt": img.get('alt', ''),
            "title": img.get('title', ''),
            "is_thumbnail": img.get('is_thumbnail', False)
        }
        
        # For local images, use the local path
        if 'local_path' in img and os.path.exists(img['local_path']):
            image_description["source"] = "local"
            image_description["path"] = img['local_path']
        else:
            # For online images, use the URL
            image_description["source"] = "online"
            image_description["url"] = img['url']
        
        images_info.append(image_description)
    
    return images_info

def generate_html_for_article(article_data):
    """Generate HTML content for a single article using Gemini API."""
    # Configure the Gemini API
    genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))
    
    # Use the GenerativeModel class
    model = genai.GenerativeModel("gemini-1.5-flash")
    
    # Process images for the article
    images_info = process_images_for_prompt(article_data)
    
    # Create image description text for the prompt
    images_description = "No images available."
    image_details = []
    if isinstance(images_info, list) and images_info:
        images_description = "\nImages:\n"
        for img in images_info:
            thumbnail_status = "Yes" if img.get("is_thumbnail") else "No"
            image_reference = f"image{img['index']}"
            image_details.append({
                "reference": image_reference,
                "index": img['index'],
                "source": img.get("source"),
                "path": img.get("path"),
                "url": img.get("url"),
                "alt": img.get("alt")
            })
            
            if img["source"] == "online":
                images_description += f"- Image {img['index']}: Reference: '{image_reference}', URL: {img['url']}, Alt: {img['alt']}, Is Thumbnail: {thumbnail_status}\n"
            else:
                images_description += f"- Image {img['index']}: Reference: '{image_reference}', Local Image, Alt: {img['alt']}, Is Thumbnail: {thumbnail_status}\n"
    
    # Prepare the prompt for Gemini with enhanced visual design requirements and image information
    prompt = f"""
    Create a beautiful, professional HTML document for this article with the following characteristics:
    
    1. Use modern HTML5 standards with appropriate semantic tags
    2. Create an exceptionally attractive visual design with:
       - A modern, premium magazine-style layout
       - Beautiful typography using web-safe or Google Fonts
       - Professional color scheme with complementary colors
       - Subtle animations for hover states and transitions
       - Visual hierarchy to highlight important information
       - Proper spacing and padding for readability
       - Responsive design that works on mobile and desktop
       - Card-based design elements where appropriate
       - Attractive blockquote styling for quotes
       - Visual separation between sections
       - Subtle background patterns or gradients
    3. Include social media sharing buttons
    4. Add a professional header with logo placeholder
    5. Add a footer with copyright information
    6. Ensure excellent readability with proper line heights and font sizes
    7. Include appropriate icons (using Font Awesome or Material icons)
    8. Include the article images in the appropriate locations:
       - Place the thumbnail image (if available) at the top of the article
       - Distribute other images throughout the content where they fit contextually
       - Use responsive image techniques
       - Apply attractive styling to images (subtle shadows, borders, etc.)
    
    ARTICLE DATA:
    Title: {article_data['title']}
    URL: {article_data['url']}
    Timestamp: {article_data['timestamp']}
    Content: 
    {article_data['content']}
    
    {images_description}
    
    IMPORTANT: For images, use placeholder references in the src attribute. For example: src="image1" for the first image, src="image2" for the second, etc.
    
    Return only the complete HTML code without any additional text or explanations.
    The CSS should be included in the <head> section of the document.
    """
    
    # Generate content using streaming
    response = model.generate_content(
        prompt,
        stream=True,
        safety_settings={
            "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
            "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
            "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
            "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
        }
    )
    
    # Collect the complete response
    full_response = ""
    for chunk in response:
        if hasattr(chunk, 'text'):
            full_response += chunk.text
    
    # Process the response to replace image references with actual image URLs or base64 data
    if image_details:
        for img in image_details:
            # Pattern to match image references like src="image1", src='image1', etc.
            pattern = f'src=["\']\\s*{img["reference"]}[^"\']*["\']'
            if img["source"] == "local":
                # Generate base64 data for local images
                base64_data = get_image_base64(img["path"])
                if base64_data:
                    # Replace image reference with base64 data
                    full_response = re.sub(pattern, f'src="{base64_data}"', full_response)
            else:
                # Replace image reference with online URL
                full_response = re.sub(pattern, f'src="{img["url"]}"', full_response)
    
    return full_response

def main():
    # Path to the JSON file containing scraped articles
    json_file_path = "crypto_news.json"
    
    # Load the articles from the JSON file
    articles = load_json_data(json_file_path)
    
    # Process each article
    for i, article in enumerate(articles):
        print(f"Generating HTML for article {i+1}/{len(articles)}: {article['title']}")
        
        # Generate HTML content
        html_content = generate_html_for_article(article)
        
        # Create a filename based on the article title
        safe_title = article['title'].replace(' ', '_').replace('/', '_').replace('\\', '_')
        safe_title = ''.join(char for char in safe_title if char.isalnum() or char in '_-')
        output_file = f"{safe_title[:50]}.html"
        
        # Save the HTML content
        save_text_file(output_file, html_content)
        print(f"HTML content saved to: {output_file}")

if __name__ == "__main__":
    main() 