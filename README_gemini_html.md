# Gemini HTML Generator

This script uses Google's Gemini API to generate well-formatted HTML pages from scraped article data stored in a JSON file.

## Prerequisites

- Python 3.6+
- Google Gemini API key

## Setup

1. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Create a `.env` file in the same directory as the script with your Google API key:
   ```
   GOOGLE_API_KEY=your_api_key_here
   ```

## Usage

1. Make sure your scraped data is in a JSON file named `crypto_news.json` in the same directory.
   The JSON should contain an array of article objects with at least the following fields:
   - `title`: The article title
   - `url`: The article URL
   - `timestamp`: The publication time
   - `content`: The article content

2. Run the script:
   ```
   python gemini_html_generator.py
   ```

3. The script will generate HTML files for each article in the JSON file, with filenames based on the article titles.

## How It Works

The script:
1. Loads scraped article data from the JSON file
2. For each article, it sends a request to the Gemini API, asking it to format the article as clean HTML
3. Saves the generated HTML to individual files named after each article

## Customization

You can modify the `generate_html_for_article` function to change the prompt sent to Gemini, which will affect the style and formatting of the generated HTML. 