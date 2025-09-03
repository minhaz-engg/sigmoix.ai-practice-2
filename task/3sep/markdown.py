import asyncio

from crawl4ai import AsyncWebCrawler, CrawlResult, CrawlerRunConfig, DefaultMarkdownGenerator, PruningContentFilter


async def demo_fit_markdown():
    """Generate focused markdown with LLM content filter"""
    print("\n=== 3. Fit Markdown with LLM Content Filter ===")

    async with AsyncWebCrawler() as crawler:
        result: CrawlResult = await crawler.arun(
            url = "https://www.daraz.com.bd/products/brushless-motor-drone-4k-camera-esc-obstacle-avoidance-brushless-motor-foldable-quadcopter-wifi-fpv-optical-flow-localization-drone-i325583733-s1564351257.html?&search=pdp_v2v?spm=a2a0e.pdp_revamp.recommendation_2.3.3f7a558eMgPAJJ&mp=1&scm=1007.38553.419544.0&clickTrackInfo=09d7be72-6338-439b-9d79-838ec868e5ca__325583733__9608__hero_item__419526__0.0__0.046145446598529816__0.0__0.0__0.0__0.0__2____334600617__334600617__0.0________22083.0__0.4117647058823529__0.0__0__12990.0__773085,1970133,2000545,398179,679978,1963322,1952953,2000274,1960330,539252,1960294,1957368,1960336,523991,525892,1955255,1970080,1955325,1957297,12005,1970153,1970373,1995484____________32104____0.0__0.0__0.0__0.0____0.0____0.0__0.0__0.0____________0.0",
            config=CrawlerRunConfig(
                markdown_generator=DefaultMarkdownGenerator(
                    content_filter=PruningContentFilter()
                )
            ),
        )
        # Save raw markdown
        with open("raw_markdown.md", "w", encoding="utf-8") as raw_file:
            raw_file.write(result.markdown.raw_markdown)
        print("✅ Saved raw markdown to raw_markdown.md")

        # Save fit markdown
        with open("fit_markdown.md", "w", encoding="utf-8") as fit_file:
            fit_file.write(result.markdown.fit_markdown)
        print("✅ Saved fit markdown to fit_markdown.md")

        
        # Print stats and save the fit markdown
        print(f"Raw: {len(result.markdown.raw_markdown)} chars")
        print(f"Fit: {len(result.markdown.fit_markdown)} chars")


async def main():
    """Run all demo functions sequentially"""
    print("=== Comprehensive Crawl4AI Demo ===")
    print("Note: Some examples require API keys or other configurations")

    # Run all demos
    await demo_fit_markdown()

    # Clean up any temp files that may have been created
    print("\n=== Demo Complete ===")
    print("Check for any generated files (screenshots, PDFs) in the current directory")

if __name__ == "__main__":
    asyncio.run(main())