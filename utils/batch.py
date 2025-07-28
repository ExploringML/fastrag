from utils.scraper import fetch_page, extract_main_content, html_to_xml, extract_sections_from_xml
from utils.database import FastHTMLDatabase
import time
from typing import List, Dict, Any

# Your URL list
fasthtml_doc_urls = [
    "https://www.fastht.ml/docs/",
    "https://www.fastht.ml/docs/tutorials/by_example.html",
    "https://www.fastht.ml/docs/tutorials/quickstart_for_web_devs.html",
    "https://www.fastht.ml/docs/tutorials/e2e.html",
    "https://www.fastht.ml/docs/tutorials/jupyter_and_fasthtml.html",
    "https://www.fastht.ml/docs/explains/background_tasks.html",
    "https://www.fastht.ml/docs/explains/explaining_xt_components.html",
    "https://www.fastht.ml/docs/explains/faq.html",
    "https://www.fastht.ml/docs/explains/minidataapi.html",
    "https://www.fastht.ml/docs/explains/oauth.html",
    "https://www.fastht.ml/docs/explains/routes.html",
    "https://www.fastht.ml/docs/explains/stripe.html",
    "https://www.fastht.ml/docs/explains/websockets.html",
    "https://www.fastht.ml/docs/ref/concise_guide.html",
    "https://www.fastht.ml/docs/ref/best_practice.html",
    "https://www.fastht.ml/docs/ref/defining_xt_component.html",
    "https://www.fastht.ml/docs/ref/handlers.html",
    "https://www.fastht.ml/docs/ref/live_reload.html",
    "https://www.fastht.ml/docs/ref/response_types.html",
    "https://www.fastht.ml/docs/api/core.html",
    "https://www.fastht.ml/docs/api/components.html",
    "https://www.fastht.ml/docs/api/xtend.html",
    "https://www.fastht.ml/docs/api/js.html",
    "https://www.fastht.ml/docs/api/pico.html",
    "https://www.fastht.ml/docs/api/svg.html",
    "https://www.fastht.ml/docs/api/jupyter.html",
    "https://www.fastht.ml/docs/api/oauth.html",
    "https://www.fastht.ml/docs/api/cli.html"
]

def process_single_url(db: FastHTMLDatabase, url: str) -> Dict[str, Any]:
    """Process a single URL and return status"""
    try:
        # Check if already exists
        if db.url_exists(url):
            return {"url": url, "status": "cached", "error": None}
        
        # Scrape and process
        soup = fetch_page(url)
        main_content = extract_main_content(soup)
        xml_content = html_to_xml(main_content, url)
        
        # Extract title from XML
        from bs4 import BeautifulSoup
        xml_soup = BeautifulSoup(xml_content, 'xml')
        title_elem = xml_soup.find('title')
        title = title_elem.string if title_elem else url.split('/')[-1]
        
        # Store document
        doc_id = db.store_document(url, xml_content, title)
        
        # Extract and store chunks
        sections = extract_sections_from_xml(xml_content)
        db.store_chunks(doc_id, url, sections)
        
        return {"url": url, "status": "processed", "error": None, "sections": len(sections)}
        
    except Exception as e:
        return {"url": url, "status": "error", "error": str(e)}

def batch_process_urls(progress_callback=None):
    """Process all URLs with optional progress callback"""
    db = FastHTMLDatabase()
    results = []
    
    total_urls = len(fasthtml_doc_urls)
    
    for i, url in enumerate(fasthtml_doc_urls):
        print(f"Processing {i+1}/{total_urls}: {url}")
        
        result = process_single_url(db, url)
        results.append(result)
        
        if progress_callback:
            progress_callback(i + 1, total_urls, result)
        
        # Small delay to be nice to the server
        time.sleep(0.5)
    
    return results

if __name__ == "__main__":
    print("Starting batch processing...")
    results = batch_process_urls()
    
    # Print summary
    processed = sum(1 for r in results if r["status"] == "processed")
    cached = sum(1 for r in results if r["status"] == "cached")
    errors = sum(1 for r in results if r["status"] == "error")
    
    print(f"\nSummary:")
    print(f"Processed: {processed}")
    print(f"Cached: {cached}")
    print(f"Errors: {errors}")
    
    if errors > 0:
        print("\nErrors:")
        for r in results:
            if r["status"] == "error":
                print(f"  {r['url']}: {r['error']}")
