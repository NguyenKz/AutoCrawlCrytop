import base64
import json
from io import BytesIO
import os
import shutil
import mimetypes
import time
from uuid import uuid4
from google import genai
from google.genai import types
from PIL import Image

def save_binary_file(file_name, data):
    """Save binary data to a file"""
    with open(file_name, "wb") as f:
        f.write(data)

def create_backup(original_path):
    """Create a backup of the original image with _backup suffix"""
    # Get the directory and filename
    file_dir = os.path.dirname(original_path)
    file_name = os.path.basename(original_path)
    name, ext = os.path.splitext(file_name)
    
    # Create backup filename
    backup_name = f"{name}_backup{ext}"
    backup_path = os.path.join(file_dir, backup_name)
    
    # Copy the original file to backup
    shutil.copy2(original_path, backup_path)
    print(f"Created backup: {backup_path}")
    
    return backup_path

def process_image(image_path, output_dir="output", create_backups=True, overwrite_original=True):
    """
    Process an image using Gemini API to:
    1. Change color style
    2. Remove any logos
    """
    # Create backup of original image if requested
    backup_path = None
    if create_backups:
        backup_path = create_backup(image_path)
    
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    # Load the image
    try:
        image = Image.open(image_path)
        print(f"Successfully loaded image: {image_path}")
    except Exception as e:
        print(f"Error loading image {image_path}: {e}")
        return None
    
    # Initialize Gemini client
    client = genai.Client(
        api_key="AIzaSyCvIauqTqYTjcy7c-DXSjhYECCy0z4r5_8",
    )
    
    # Convert image to RGB mode if it's in RGBA (to avoid JPEG incompatibility)
    if image.mode == 'RGBA':
        image = image.convert('RGB')
        
    # Convert image to bytes
    im_file = BytesIO()
    image.save(im_file, format="JPEG")
    im_bytes = im_file.getvalue()

    # Set up the model and prompt
    model = "gemini-2.0-flash-exp-image-generation"
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(text="""
Modify this image by:
1. Adjust the color style to make it more vibrant and professional
2. Remove all logos and watermarks from the image
Keep all other aspects of the image intact. Return just the modified image.
"""),
                types.Part.from_bytes(
                    mime_type="image/jpeg",
                    data=im_bytes
                )
            ],
        ),
    ]
    
    # Configure the API request
    generate_content_config = types.GenerateContentConfig(
        response_modalities=[
            "image",
            "text",
        ],
        safety_settings=[
            types.SafetySetting(
                category="HARM_CATEGORY_CIVIC_INTEGRITY",
                threshold="OFF",
            ),
        ],
        response_mime_type="text/plain",
    )
    
    # Try to generate content up to 3 times
    for attempt in range(3):
        print(f"Processing image {os.path.basename(image_path)}, attempt {attempt+1}...")
        try:
            for chunk in client.models.generate_content_stream(
                model=model,
                contents=contents,
                config=generate_content_config,
            ):
                if not chunk.candidates or not chunk.candidates[0].content or not chunk.candidates[0].content.parts:
                    continue
                
                if chunk.candidates[0].content.parts[0].inline_data:
                    # Process received data
                    inline_data = chunk.candidates[0].content.parts[0].inline_data
                    
                    # First, try to decode if it's base64 data 
                    try:
                        decoded_data = None
                        # Check if it's a string (likely base64)
                        if isinstance(inline_data.data, str):
                            if inline_data.data.startswith('data:image'):
                                # Format like data:image/png;base64,ABC123...
                                header, encoded = inline_data.data.split(",", 1)
                                decoded_data = base64.b64decode(encoded)
                            else:
                                # Try direct base64 decode
                                try:
                                    decoded_data = base64.b64decode(inline_data.data)
                                except:
                                    # Not base64, use as is
                                    decoded_data = inline_data.data.encode('utf-8')
                        else:
                            # Already binary data
                            decoded_data = inline_data.data
                        
                        # If overwriting original, use the original path as output path
                        if overwrite_original:
                            output_path = image_path
                            print(f"Overwriting original image: {output_path}")
                        else:
                            # Save to output directory with a new name
                            base_name = os.path.splitext(os.path.basename(image_path))[0]
                            file_name = f"{base_name}_edited_{uuid4().hex[:8]}"
                            file_extension = mimetypes.guess_extension(inline_data.mime_type) or ".jpg"
                            output_path = os.path.join(output_dir, f"{file_name}{file_extension}")
                        
                        # Save the edited image
                        save_binary_file(output_path, decoded_data)
                        
                        # Try to validate the image
                        try:
                            Image.open(output_path)
                            print(f"Successfully saved edited image to: {output_path}")
                        except Exception as e:
                            print(f"Warning: Image may not be valid: {e}")
                            # If we're in overwrite mode and validation failed, restore from backup
                            if overwrite_original and backup_path and os.path.exists(backup_path):
                                print(f"Restoring from backup: {backup_path}")
                                shutil.copy2(backup_path, image_path)
                                return None
                        
                        return output_path
                    
                    except Exception as e:
                        print(f"Error processing image data: {e}")
                        # Save original format as fallback
                        if overwrite_original:
                            output_path = image_path
                        else:
                            base_name = os.path.splitext(os.path.basename(image_path))[0]
                            file_name = f"{base_name}_edited_{uuid4().hex[:8]}"
                            file_extension = mimetypes.guess_extension(inline_data.mime_type) or ".jpg"
                            output_path = os.path.join(output_dir, f"{file_name}{file_extension}")
                        
                        save_binary_file(output_path, inline_data.data)
                        print(f"Saved edited image to: {output_path}")
                        
                        return output_path
                else:
                    print(chunk.text)
            
            # If we got here without returning, there was an issue with the response
            print(f"No valid image in response for {image_path}, retrying...")
            time.sleep(5)  # Wait before retrying
            
        except Exception as e:
            print(f"Error processing {image_path}: {e}")
            time.sleep(5)  # Wait before retrying
    
    print(f"Failed to process {image_path} after multiple attempts")
    return None

def process_images_from_json(json_file_path, output_dir="output", create_backups=True, overwrite_original=True):
    """
    Read a JSON file containing image paths and process each image
    """
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Check if the data is in the expected format - multiple formats supported
        image_paths = []
        
        # Format 1: Direct list of images
        if isinstance(data, list) and all(isinstance(item, str) for item in data):
            image_paths = data
        
        # Format 2: Object with 'images' key containing paths
        elif not isinstance(data, list) and 'images' in data:
            if isinstance(data['images'], list):
                image_paths = data['images']
        
        # Format 3: List of articles with 'local_images'
        elif isinstance(data, list) and any('local_images' in item for item in data):
            for article in data:
                if 'local_images' in article and isinstance(article['local_images'], list):
                    for image in article['local_images']:
                        if isinstance(image, dict) and 'local_path' in image:
                            image_paths.append(image['local_path'])
        
        # If no images found yet, try to find an images list in any nested structure
        if not image_paths:
            # Try to find an images list in the data
            for key, value in data.items() if isinstance(data, dict) else []:
                if isinstance(value, list) and key.lower().endswith('images'):
                    for img in value:
                        if isinstance(img, str):
                            image_paths.append(img)
                        elif isinstance(img, dict):
                            for img_key in ['path', 'url', 'local_path']:
                                if img_key in img:
                                    image_paths.append(img[img_key])
                                    break
        
        if not image_paths:
            print("No images found in the JSON file")
            return
        
        print(f"Found {len(image_paths)} images to process")
        
        # Process each image
        results = []
        for img_path in image_paths:
            # Skip non-local paths
            if isinstance(img_path, str) and img_path.startswith(('http://', 'https://')):
                print(f"Skipping non-local image: {img_path}")
                continue
            
            # Check if file exists
            if not os.path.exists(img_path):
                print(f"Image file not found: {img_path}")
                continue
                
            output_path = process_image(img_path, output_dir, create_backups, overwrite_original)
            if output_path:
                results.append({
                    'original': img_path,
                    'backup': f"{os.path.splitext(img_path)[0]}_backup{os.path.splitext(img_path)[1]}" if create_backups else None,
                    'edited': output_path
                })
            
            # Avoid rate limiting
            time.sleep(2)
        
        # Save results to a new JSON file
        results_file = os.path.join(output_dir, 'processing_results.json')
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        
        print(f"Processing complete. Results saved to {results_file}")
        print(f"Total images processed: {len(results)}")
        
    except Exception as e:
        print(f"Error processing JSON file: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description='Process images using Gemini AI')
    parser.add_argument('json_file', type=str, nargs='?', help='Path to JSON file with image paths')
    parser.add_argument('--output-dir', type=str, default='output', help='Directory to save processed images (default: output)')
    parser.add_argument('--create-backups', action='store_true', default=True, help='Create backups of original images with _backup suffix')
    parser.add_argument('--no-backups', dest='create_backups', action='store_false', help='Do not create backups of original images')
    parser.add_argument('--overwrite', action='store_true', default=True, help='Overwrite original image files with edited versions')
    parser.add_argument('--no-overwrite', dest='overwrite', action='store_false', help='Do not overwrite original images, save edited versions separately')
    
    args = parser.parse_args()
    
    if args.json_file:
        json_file = args.json_file
    else:
        json_file = input("Enter the path to your JSON file with image paths: ")
    
    process_images_from_json(json_file, args.output_dir, args.create_backups, args.overwrite)
