import asyncio
import os
from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CrawlerRunConfig,
    CacheMode,
    LLMConfig,
    LLMExtractionStrategy
)
from typing import Dict
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


# CSS Selector Example
async def simple_example_with_css_selector():
    print("\n--- Using CSS Selectors ---")
    browser_config = BrowserConfig(headless=True)
    crawler_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS, css_selector=".pdp-product-detail"
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(
            url="https://www.daraz.com.bd/products/vivo-samsung-huawei-xiaomi-oppo-vivo-35mm-i234040073-s1176850650.html", config=crawler_config
        )
        print(result)


async def extract_structured_data_using_llm(
    provider: str, api_token: str = None, extra_headers: Dict[str, str] = None
):
    print(f"\n--- Extracting Structured Data with {provider} ---")

    if api_token is None and provider != "ollama":
        print(f"API token is required for {provider}. Skipping this example.")
        return

    browser_config = BrowserConfig(headless=True)

    extra_args = {"temperature": 0, "top_p": 0.9, "max_tokens": 2000}
    if extra_headers:
        extra_args["extra_headers"] = extra_headers

    crawler_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        word_count_threshold=1,
        page_timeout=80000,
        extraction_strategy=LLMExtractionStrategy(
            llm_config=LLMConfig(provider=provider,api_token=api_token),
            # schema=OpenAIModelFee.model_json_schema(),
            extraction_type="schema",
            instruction="""this is a product detail page. extract all the information about the product in json format.
            make sure to include the following fields if available: product name, price, description, specifications""",
            extra_args=extra_args,
        ),
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(
            url="https://www.daraz.com.bd/products/vivo-samsung-huawei-xiaomi-oppo-vivo-35mm-i234040073-s1176850650.html", config=crawler_config
        )
        print(result.extracted_content)


# Main execution
async def main():
   
    # await simple_example_with_css_selector()
    await extract_structured_data_using_llm(
        "gemini/gemini-2.0-flash-lite-preview-02-05", os.getenv("GEMINI_API_KEY")
    )

    


if __name__ == "__main__":
    asyncio.run(main())