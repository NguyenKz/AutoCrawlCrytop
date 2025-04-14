python crypto_news_scraper.py --limit 10 --download-images --images-folder crypto_images --html --json --full
python gemini_image_processor.py crypto_news.json
python gemini_html_generator.py