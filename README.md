# Crypto.news Scraper

This Python script scrapes the latest cryptocurrency news articles from the [crypto.news](https://crypto.news/) website.

## Features

- Fetches the latest cryptocurrency news articles
- Extracts title, URL, timestamp, tags, and summary for each article
- Displays the information in a readable format
- Saves results to JSON or CSV files
- Command-line interface with various options

## Requirements

- Python 3.6 or higher
- Required packages: requests, beautifulsoup4

## Installation

1. Clone this repository or download the script files
2. Install the required packages:

```bash
pip install -r requirements.txt
```

## Usage

### Basic Usage

Run the script with Python:

```bash
python crypto_news_scraper.py
```

This will fetch the latest news and display it in the console.

### Command-line Options

The script supports several command-line arguments:

```
usage: crypto_news_scraper.py [-h] [--json] [--csv] [--output OUTPUT] [--quiet]

Scrape latest cryptocurrency news from crypto.news

options:
  -h, --help       show this help message and exit
  --json           Save results to JSON file
  --csv            Save results to CSV file
  --output OUTPUT  Output filename prefix (default: crypto_news)
  --quiet          Suppress console output
```

### Examples

Save results to a JSON file:

```bash
python crypto_news_scraper.py --json
```

Save results to a CSV file with a custom filename:

```bash
python crypto_news_scraper.py --csv --output my_crypto_news
```

Save to both JSON and CSV formats without displaying in the console:

```bash
python crypto_news_scraper.py --json --csv --quiet
```

## Data Format

Each news item contains the following information:

- `title`: The title of the news article
- `url`: The URL of the article
- `timestamp`: When the article was published
- `tags`: List of tags or categories
- `summary`: A brief summary of the article (if available)
- `scraped_at`: Timestamp when the data was scraped

## Customization

You can modify the script to:
- Extract additional information
- Filter articles by specific tags or keywords
- Change the formatting of the output
- Add more export formats

## Notes

- This script is for educational purposes
- Web scraping might be subject to the website's terms of service
- The script may need updates if the website structure changes 