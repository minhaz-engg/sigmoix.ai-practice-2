import os
import json
import asyncio
from typing import List
from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CacheMode,
    CrawlResult,
    CrawlerRunConfig,
    GeolocationConfig,
    LLMConfig,
    JsonCssExtractionStrategy,
    ProxyRotationStrategy,
)
from crawl4ai.async_crawler_strategy import AsyncPlaywrightCrawlerStrategy
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

__cur_dir__ = Path(__file__).parent

# 🔹 Create a "result" directory inside current folder
RESULT_DIR = __cur_dir__ / "result_product"
RESULT_DIR.mkdir(exist_ok=True)

# 🔹 Save schema + output inside result/
PRIMARY_SCHEMA_FILE = RESULT_DIR / "primary_product_schema.json"
OUTPUT_FILE = RESULT_DIR / "product.json"

async def load_or_generate_schema(link: str, sample_html: str) -> dict:
    """Load schema from file or generate with LLM if not exists."""
    if os.path.exists(PRIMARY_SCHEMA_FILE):
        with open(PRIMARY_SCHEMA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    schema = JsonCssExtractionStrategy.generate_schema(
        html=sample_html,
        llm_config=LLMConfig(
            provider="gemini/gemini-2.0-flash-lite-preview-02-05",
            api_token=os.getenv("GEMINI_API_KEY", os.getenv('GEMINI_API_KEY')),
        ),
        query=(
            f"""From {link} from an ecommerce single product page,
            I shared a div for some unstructured detail data about the product. 
            Please generate a schema those information. for extract all writing and convert it to plain paragraph
            """
        ),
    )

    with open(PRIMARY_SCHEMA_FILE, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)

    return schema


async def demo_css_structured_extraction_no_schema(link: str):
    """Extract structured data using CSS selectors"""
    print("\n=== 5. CSS-Based Structured Extraction ===")
    # Sample HTML for schema generation (one-time cost)
    product_primary_html = """
    <div class="pdp-product-desc ">...</div>
    """
    schema = await load_or_generate_schema(link, product_primary_html)

    
    # Create no-LLM extraction strategy with the generated schema
    extraction_strategy = JsonCssExtractionStrategy(schema)
    config = CrawlerRunConfig(
        cache_mode=CacheMode.DISABLED,
        geolocation=GeolocationConfig(latitude=23.8103, longitude=90.4125),
        prettiify=False,
        wait_for_images=False,
        delay_before_return_html=False,
        mean_delay=0.1,      # tiny but non-zero
        scroll_delay=0.2,
        verbose=True,
        )

    # Use the fast CSS extraction (no LLM calls during extraction)
    async with AsyncWebCrawler() as crawler:
        results: List[CrawlResult] = await crawler.arun(
            url=link,
            config=config
        )

        print(results[0].extracted_content)


async def main():
    """Run all demo functions sequentially"""
    print("=== Comprehensive Crawl4AI Demo ===")
    print("Note: Some examples require API keys or other configurations")
    link = "https://www.daraz.com.bd/products/haier-15-ton-hsu-18turbocool-i234355205-s1342661867.html"
    await demo_css_structured_extraction_no_schema(link)

    # Clean up any temp files that may have been created
    print("\n=== Demo Complete ===")
    print("Check for any generated files (screenshots, PDFs) in the current directory")

if __name__ == "__main__":
    asyncio.run(main())