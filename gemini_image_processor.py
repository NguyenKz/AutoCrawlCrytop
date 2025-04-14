import base64
import json
import os
import shutil
import time
import re
from io import BytesIO
from uuid import uuid4
import mimetypes
from google import genai
from google.genai import types
from PIL import Image

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

def decode_base64_to_binary(data):
    """
    Decode base64 data to binary
    """
    try:
        # Check if data starts with data:image format
        if isinstance(data, str) and data.startswith('data:image'):
            # Extract base64 part
            _, encoded = data.split(',', 1)
            return base64.b64decode(encoded)
        
        # Direct base64 string
        elif isinstance(data, str):
            try:
                return base64.b64decode(data)
            except:
                return data.encode('utf-8')
        
        # Already binary
        else:
            return data
    except Exception as e:
        print(f"Error decoding data: {e}")
        return data

def save_image(output_path, data):
    """
    Save image data to a file
    """
    try:
        with open(output_path, 'wb') as f:
            f.write(data)
        print(f"Saved image to: {output_path}")
        return True
    except Exception as e:
        print(f"Error saving image: {e}")
        return False

def fix_image_data(data):
    """
    Try to fix problematic image data
    """
    try:
        # Check if the data is base64 encoded
        if isinstance(data, str):
            # First attempt: standard base64 decode
            try:
                return base64.b64decode(data)
            except:
                pass
            
            # Second attempt: if data starts with 'iVBOR', it's likely a PNG in base64
            if 'iVBOR' in data:
                # Extract just the base64 part without headers
                pattern = r'[A-Za-z0-9+/=]+'
                matches = re.findall(pattern, data)
                if matches:
                    longest_match = max(matches, key=len)
                    if len(longest_match) > 100:  # Likely a valid base64 string
                        try:
                            return base64.b64decode(longest_match)
                        except:
                            pass
        
        # Return original data if all fixes fail
        return data
    except:
        return data

def process_image(image_path, output_dir="output", create_backups=True, overwrite_original=True):
    """
    Process an image using Gemini API:
    1. Create backup of original if requested
    2. Send to Gemini for color enhancement and logo removal
    3. Save the result (either overwriting original or to a new file)
    """
    # Ensure paths are absolute
    image_path = os.path.abspath(image_path)
    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)
    
    # Create backup if requested
    backup_path = None
    if create_backups:
        backup_path = create_backup(image_path)
    
    # Load original image
    try:
        image = Image.open(image_path)
        print(f"Processing image: {image_path}")
        # Get original format for later
        original_format = image.format
    except Exception as e:
        print(f"Error loading image {image_path}: {e}")
        return None
    
    # Convert to RGB if needed (some formats require this)
    if image.mode == 'RGBA':
        image = image.convert('RGB')
    
    # Convert to bytes for API
    img_bytes = BytesIO()
    image.save(img_bytes, format="JPEG")
    img_data = img_bytes.getvalue()
    
    # Initialize Gemini client
    client = genai.Client(
        api_key="AIzaSyCvIauqTqYTjcy7c-DXSjhYECCy0z4r5_8",
    )
    
    # Set up prompt
    model = "gemini-2.0-flash-exp-image-generation"
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(text="""
Modify this image by:
1. Enhance the color style to make it more vibrant and professional
2. COMPLETELY remove ALL logos, watermarks, and text overlays
3. Maintain the original aspect ratio and content of the image

Return only the edited image without any text explanation.
"""),
                types.Part.from_bytes(
                    mime_type="image/jpeg",
                    data=img_data
                )
            ],
        ),
    ]
    
    # Configure API request
    generate_content_config = types.GenerateContentConfig(
        response_modalities=["image", "text"],
        safety_settings=[
            types.SafetySetting(
                category="HARM_CATEGORY_CIVIC_INTEGRITY",
                threshold="OFF",
            ),
        ],
    )
    
    # Try up to 3 times
    for attempt in range(3):
        print(f"Attempt {attempt+1}/3...")
        try:
            # Get response from Gemini
            for chunk in client.models.generate_content_stream(
                model=model,
                contents=contents,
                config=generate_content_config,
            ):
                if not chunk.candidates or not chunk.candidates[0].content or not chunk.candidates[0].content.parts:
                    continue
                
                # Process inline data (image)
                if chunk.candidates[0].content.parts[0].inline_data:
                    inline_data = chunk.candidates[0].content.parts[0].inline_data
                    
                    # Create temporary files for processing
                    temp_file = os.path.join(output_dir, f"temp_{uuid4().hex[:8]}.bin")
                    temp_fixed = os.path.join(output_dir, f"temp_fixed_{uuid4().hex[:8]}.bin")
                    
                    # Save raw response first
                    with open(temp_file, 'wb') as f:
                        f.write(inline_data.data)
                    
                    # Determine if it's base64 or binary
                    is_base64 = False
                    try:
                        with open(temp_file, 'r', encoding='utf-8', errors='ignore') as f:
                            first_bytes = f.read(100)
                            if any(marker in first_bytes for marker in ['iVBOR', 'data:image', '/9j/']):
                                is_base64 = True
                    except:
                        pass
                    
                    # Process the data
                    if is_base64:
                        try:
                            # Read the file as text
                            with open(temp_file, 'r', encoding='utf-8', errors='ignore') as f:
                                base64_data = f.read()
                            
                            # Try to decode
                            try:
                                binary_data = decode_base64_to_binary(base64_data)
                                with open(temp_fixed, 'wb') as f:
                                    f.write(binary_data)
                                
                                # Verify it's a valid image
                                try:
                                    Image.open(temp_fixed)
                                    print("Successfully decoded base64 image")
                                    processed_file = temp_fixed
                                except:
                                    # Fallback to alternate method
                                    try:
                                        fixed_data = fix_image_data(base64_data)
                                        with open(temp_fixed, 'wb') as f:
                                            f.write(fixed_data)
                                        Image.open(temp_fixed)
                                        print("Fixed image using alternate method")
                                        processed_file = temp_fixed
                                    except:
                                        print("All decoding methods failed")
                                        processed_file = temp_file
                            except:
                                processed_file = temp_file
                        except:
                            processed_file = temp_file
                    else:
                        # It's already binary
                        processed_file = temp_file
                    
                    # Determine output path
                    if overwrite_original:
                        final_path = image_path
                        print(f"Overwriting original: {final_path}")
                    else:
                        # Create new filename in output directory
                        base_name = os.path.splitext(os.path.basename(image_path))[0]
                        file_extension = os.path.splitext(image_path)[1]
                        final_path = os.path.join(output_dir, f"{base_name}_edited{file_extension}")
                        print(f"Saving to new file: {final_path}")
                    
                    # Try to open processed image to verify it's valid
                    valid_image = False
                    try:
                        img = Image.open(processed_file)
                        img.verify()
                        valid_image = True
                    except:
                        print("Warning: Processed image may not be valid")
                        
                    # If the image is valid or we want to try anyway
                    if valid_image or not overwrite_original:
                        # Copy to final destination
                        try:
                            shutil.copy2(processed_file, final_path)
                            print(f"Successfully saved edited image to: {final_path}")
                            
                            # Clean up temp files
                            try:
                                if os.path.exists(temp_file):
                                    os.remove(temp_file)
                                if os.path.exists(temp_fixed):
                                    os.remove(temp_fixed)
                            except:
                                pass
                                
                            return final_path
                        except Exception as e:
                            print(f"Error saving final image: {e}")
                    
                    # If overwriting and not valid, restore from backup
                    if overwrite_original and not valid_image and backup_path:
                        print(f"Restoring from backup: {backup_path}")
                        shutil.copy2(backup_path, image_path)
                        
                    # Clean up temp files
                    try:
                        if os.path.exists(temp_file):
                            os.remove(temp_file)
                        if os.path.exists(temp_fixed):
                            os.remove(temp_fixed)
                    except:
                        pass
                    
                    return final_path if valid_image else None
                
                # Handle text response with potential base64 image
                elif hasattr(chunk.candidates[0].content.parts[0], 'text'):
                    text = chunk.candidates[0].content.parts[0].text
                    
                    # Check for base64 image data
                    if "data:image" in text:
                        print("Found base64 image data in text response")
                        match = re.search(r'data:image/[^;]+;base64,([^"\')\s]+)', text)
                        if match:
                            image_data = match.group(0)
                            
                            # Decode and save
                            try:
                                binary_data = decode_base64_to_binary(image_data)
                                
                                # Determine output path
                                if overwrite_original:
                                    output_path = image_path
                                else:
                                    base_name = os.path.splitext(os.path.basename(image_path))[0]
                                    output_path = os.path.join(output_dir, f"{base_name}_edited.png")
                                
                                # Save image
                                with open(output_path, 'wb') as f:
                                    f.write(binary_data)
                                
                                # Verify image
                                Image.open(output_path)
                                print(f"Successfully saved image from text response to: {output_path}")
                                return output_path
                            except Exception as e:
                                print(f"Error saving image from text: {e}")
            
            # If we reach here, retry
            print("No valid response, retrying...")
            time.sleep(3)
        
        except Exception as e:
            print(f"Error during processing: {e}")
            time.sleep(3)
    
    print(f"Failed to process {image_path} after multiple attempts")
    return None

def process_images_from_json(json_file, output_dir="output", create_backups=True, overwrite_original=True):
    """
    Process images listed in a JSON file
    """
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    try:
        # Load JSON file
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Extract image paths
        image_paths = []
        
        # Format 1: Direct list of strings
        if isinstance(data, list) and all(isinstance(item, str) for item in data):
            image_paths = data
        
        # Format 2: Object with 'images' array
        elif isinstance(data, dict) and 'images' in data:
            image_paths = data['images']
        
        # Format 3: Array of articles with local_images
        elif isinstance(data, list) and any('local_images' in item for item in data):
            for article in data:
                if 'local_images' in article and isinstance(article['local_images'], list):
                    for img in article['local_images']:
                        if isinstance(img, dict) and 'local_path' in img:
                            image_paths.append(img['local_path'])
        
        # No images found, search recursively
        if not image_paths:
            # Try to find any image lists in nested dictionary
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
                
            # Process the image
            output_path = process_image(img_path, output_dir, create_backups, overwrite_original)
            
            if output_path:
                # Record successful processing
                results.append({
                    'original': img_path,
                    'backup': f"{os.path.splitext(img_path)[0]}_backup{os.path.splitext(img_path)[1]}" if create_backups else None,
                    'edited': output_path
                })
            
            # Avoid rate limiting
            time.sleep(5)
        
        # Save results to a JSON file
        results_file = os.path.join(output_dir, 'results.json')
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        
        print(f"Processing complete. {len(results)} of {len(image_paths)} images successfully processed.")
        print(f"Results saved to: {results_file}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description='Process images using Gemini AI')
    parser.add_argument('json_file', type=str, nargs='?', 
                        help='Path to JSON file with image paths')
    parser.add_argument('--output-dir', type=str, default='output', 
                        help='Directory to save processed images (default: output)')
    parser.add_argument('--backup', action='store_true', default=True, 
                        help='Create backups of original images with _backup suffix')
    parser.add_argument('--no-backup', dest='backup', action='store_false', 
                        help='Do not create backups of original images')
    parser.add_argument('--overwrite', action='store_true', default=True, 
                        help='Overwrite original images with edited versions')
    parser.add_argument('--no-overwrite', dest='overwrite', action='store_false', 
                        help='Save edited images separately without overwriting originals')
    
    args = parser.parse_args()
    
    if args.json_file:
        json_file = args.json_file
    else:
        json_file = input("Enter the path to your JSON file with image paths: ")
    
    process_images_from_json(json_file, args.output_dir, args.backup, args.overwrite)