import os
import asyncio
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode, GeolocationConfig
from crawl4ai import LLMConfig
from crawl4ai.content_filter_strategy import LLMContentFilter
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

async def test_llm_filter():
    # Create an HTML source that needs intelligent filtering
    url = "https://www.daraz.com.bd/products/brushless-motor-drone-4k-camera-esc-obstacle-avoidance-brushless-motor-foldable-quadcopter-wifi-fpv-optical-flow-localization-drone-i325583733-s1564351257.html?&search=pdp_v2v?spm=a2a0e.pdp_revamp.recommendation_2.3.3f7a558eMgPAJJ&mp=1&scm=1007.38553.419544.0&clickTrackInfo=09d7be72-6338-439b-9d79-838ec868e5ca__325583733__9608__hero_item__419526__0.0__0.046145446598529816__0.0__0.0__0.0__0.0__2____334600617__334600617__0.0________22083.0__0.4117647058823529__0.0__0__12990.0__773085,1970133,2000545,398179,679978,1963322,1952953,2000274,1960330,539252,1960294,1957368,1960336,523991,525892,1955255,1970080,1955325,1957297,12005,1970153,1970373,1995484____________32104____0.0__0.0__0.0__0.0____0.0____0.0__0.0__0.0____________0.0"
    
    browser_config = BrowserConfig(
        headless=True,
        verbose=True
    )
    
    # run_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)
    run_config = CrawlerRunConfig(
        cache_mode=CacheMode.ENABLED,
        geolocation=GeolocationConfig(latitude=23.8103, longitude=90.4125),
        prettiify=False,
        wait_for_images=False,
        delay_before_return_html=False,
        mean_delay=0.1,      # tiny but non-zero
        scroll_delay=0.2,
        verbose=True,
        wait_until="networkidle"
    )
    
    async with AsyncWebCrawler(config=browser_config) as crawler:
        # First get the raw HTML
        result = await crawler.arun(url, config=run_config)
        html = result.cleaned_html

        # Initialize LLM filter with focused instruction
        filter = LLMContentFilter(
            llm_config=LLMConfig(
            provider="gemini/gemini-2.0-flash-lite-preview-02-05",
            api_token=os.getenv("GEMINI_API_KEY"),
        ),
            instruction="""
            Focus on extracting the core detail content about the product.
            Include:
            - product specifications details. all details about the product inside the div id "module_product_detail"
            
            Format the output as clean markdown with proper code blocks and headers.
            """,
            verbose=True
        )
        
        filter = LLMContentFilter(
            llm_config=LLMConfig(
            provider="gemini/gemini-2.0-flash-lite-preview-02-05",
            api_token=os.getenv("GEMINI_API_KEY"),
        ),
            chunk_token_threshold=2 ** 12 * 2, # 2048 * 2
            ignore_cache = True,
            instruction="""
            Extract the product detail while preserving its original wording and substance completely. Your task is to:

            1. Maintain the exact language and terminology used in the main content
            2. Keep all technical explanations, 
            3. Preserve the original flow and structure of the core content

            The goal is to create a clean markdown version that reads exactly like the original product detail, 
            keeping all valuable content but free from distracting elements. Imagine you're creating 
            a perfect reading experience where nothing valuable is lost, but all noise is removed.
            """,
            verbose=True
        )        

        # Apply filtering
        filtered_content = filter.filter_content(html)
        
        # Show results
        print("\nFiltered Content Length:", len(filtered_content))
        print("\nFirst 500 chars of filtered content:")
        if filtered_content:
            print(filtered_content[0][:500])
        
        # Save on disc the markdown version
        with open("filtered_content.md", "w", encoding="utf-8") as f:
            f.write("\n".join(filtered_content))
        
        # Show token usage
        filter.show_usage()

if __name__ == "__main__":
    asyncio.run(test_llm_filter())