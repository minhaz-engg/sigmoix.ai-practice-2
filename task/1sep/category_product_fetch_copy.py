import os
import json
import time
import random
import hashlib
import asyncio
from typing import List, Dict, Tuple, Iterable
from pathlib import Path

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
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

__cur_dir__ = Path(__file__).parent

# 🔹 Create a "result" directory inside current folder
RESULT_DIR = __cur_dir__ / "result"
RESULT_DIR.mkdir(exist_ok=True)

# 🔹 Save schema + output inside result/
SCHEMA_FILE = RESULT_DIR / "schema.json"
OUTPUT_FILE = RESULT_DIR / "products.json"
PAGES_INDEX_FILE = RESULT_DIR / "pages_index.json"  # page -> list of item ids (optional but helpful)

# ---------- Tunables ----------
MAX_RETRIES = 5              # max tries per page if we only see previously-seen products
MIN_NEW_PER_PAGE = 1         # require at least this many new items to accept a page
RETRY_BACKOFF_BASE = 0.8     # base seconds for exponential backoff between retries
ADD_CACHE_BUST = True        # append a harmless cache-busting query param on each retry
SAVE_ONLY_UNIQUE = True      # when writing per-page JSON, keep only products that are new vs. global set
# -----------------------------


def atomic_write_json(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def load_json_if_exists(path: Path, default):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def get_product_id(product: dict) -> str:
    """
    Returns a stable product id from the item.
    Prefers 'data_item_id'. Falls back to first token of 'data_sku_simple' (e.g., '318713152' from '318713152_BD-...').
    Returns '' if we can't find anything.
    """
    pid = (product.get("data_item_id") or "").strip()
    if pid:
        return pid
    sku = (product.get("data_sku_simple") or "").strip()
    if sku:
        # often looks like "318713152_BD-1546085288" -> "318713152"
        return sku.split("_", 1)[0].strip()
    return ""


def dedupe_products(products: Iterable[dict]) -> List[dict]:
    seen: set = set()
    deduped = []
    for p in products:
        pid = get_product_id(p)
        if not pid:
            # skip items without any stable id
            continue
        if pid in seen:
            continue
        seen.add(pid)
        deduped.append(p)
    return deduped


async def load_or_generate_schema(link: str, sample_html: str) -> dict:
    """Load schema from file or generate with LLM if not exists."""
    if os.path.exists(SCHEMA_FILE):
        with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    # ⚠️ Consider using an environment variable for the API key instead of hardcoding it.
    schema = JsonCssExtractionStrategy.generate_schema(
        html=sample_html,
        llm_config=LLMConfig(
            provider="gemini/gemini-2.0-flash-lite-preview-02-05",
            api_token=os.getenv("GEMINI_API_KEY", os.getenv('GEMINI_API_KEY')),
        ),
        query=(
            f"""From {link} from an ecommerce site,
            I shared one product div. Please generate a schema extracting ALL product info
            Please generate a schema for this product div. i need all all all informations of a product. i also need product detail url for each product, i also need product image url for each product."""
        ),
    )

    atomic_write_json(SCHEMA_FILE, schema)
    return schema


async def crawl_once(
    crawler: AsyncWebCrawler,
    url: str,
    config: CrawlerRunConfig,
    page_idx: int,
    attempt: int,
) -> Tuple[List[dict], List[str]]:
    """
    Execute a single crawl attempt for a URL, returning:
      - list of parsed product dicts
      - list of product ids (as strings, empty filtered out)
    Also dumps result HTMLs for debugging.
    """

    results: List[CrawlResult] = await crawler.arun(
        url=url,
        config=config,
        js_code="""
            // give the page time to render + lazy-load
            await new Promise(resolve => setTimeout(resolve, 2000));
            window.scrollTo(0, document.body.scrollHeight);
            await new Promise(resolve => setTimeout(resolve, 1500));
            window.scrollTo(0, 0);
        """,
        wait_for="css:.gridItem, .product-item, [data-qa-locator='product-item']",
    )

    page_products_aggregated: List[dict] = []

    for res_idx, result in enumerate(results, start=1):
        if not result.success:
            print(f"❌ Failed to extract data from {result.url}")
            continue

        # # Save raw HTML for debugging (per result + attempt)
        # with open(RESULT_DIR / f"page_{page_idx}_attempt_{attempt}_{res_idx}.html", "w", encoding="utf-8") as f:
        #     f.write(result.html)

        try:
            data = json.loads(result.extracted_content)
            if isinstance(data, list):
                page_products = data
            else:
                page_products = [data]
            page_products_aggregated.extend(page_products)
        except Exception as e:
            print(f"⚠️ JSON parse error for page {page_idx}, result {res_idx}: {e}")

    # normalize + dedupe within this attempt
    page_products_aggregated = dedupe_products(page_products_aggregated)
    ids = [get_product_id(p) for p in page_products_aggregated if get_product_id(p)]
    return page_products_aggregated, ids


async def fetch_until_new(
    crawler: AsyncWebCrawler,
    base_url: str,
    config: CrawlerRunConfig,
    known_ids: set,
    page_idx: int,
    max_retries: int = MAX_RETRIES,
    min_new: int = MIN_NEW_PER_PAGE,
    add_cache_bust: bool = ADD_CACHE_BUST,
) -> Tuple[List[dict], List[str], int]:
    """
    Try fetching a page multiple times until we see at least `min_new` product ids
    not in `known_ids`. Returns (products, product_ids, attempts_used).
    """

    for attempt in range(1, max_retries + 1):
        # Optional cache-busting (harmless param typically ignored by servers)
        if add_cache_bust:
            sep = "&" if "?" in base_url else "?"
            url = f"{base_url}{sep}_v={int(time.time()*1000)}"
        else:
            url = base_url

        print(f"--- Crawling page {page_idx} (attempt {attempt}): {url} ---")
        try:
            products, ids = await crawl_once(crawler, url, config, page_idx, attempt)
        except Exception as e:
            print(f"❌ arun failed for {url}: {e}")
            products, ids = [], []

        if not products:
            print(f"⚠️ Page {page_idx}, attempt {attempt}: no products collected; retrying...")
        else:
            new_ids = [pid for pid in ids if pid not in known_ids]
            print(f"ℹ️ Page {page_idx}, attempt {attempt}: {len(products)} items, "
                  f"{len(new_ids)} new vs. global.")
            if len(new_ids) >= min_new:
                return products, ids, attempt

        # backoff before next attempt to give the site time to serve a fresh page
        await asyncio.sleep(RETRY_BACKOFF_BASE * (2 ** (attempt - 1)) + random.random() * 0.2)

    # Return last attempt even if it had no/insufficient new products
    return products, ids, max_retries


async def demo_css_structured_extraction_no_schema(link: str, page_range: range):
    """Extract structured product data sequentially with retries until new content is seen."""
    print("\n=== Efficient CSS-Based Structured Extraction with New-Content Retries ===")

    # Minimal product div to help schema generation
    sample_html = """
    <div class="Bm3ON" data-qa-locator="product-item" data-tracking="product-card" data-sku-simple="424381164_BD-2071091963" data-item-id="" data-listno="37" data-utlogmap="{&quot;listno&quot;:37,&quot;pageIndex&quot;:1,&quot;pvid&quot;:&quot;fa3d5fb4c8afef0f723af80f05fbf47f&quot;,&quot;query&quot;:&quot;other+projector+accessories&quot;,&quot;style&quot;:&quot;wf&quot;,&quot;x_item_ids&quot;:&quot;424381164&quot;,&quot;x_object_id&quot;:&quot;424381164&quot;,&quot;x_object_type&quot;:&quot;item&quot;}" data-aplus-ae="x41_55a80716" data-spm-anchor-id="a2a0e.searchlist.list.i41.2a1629f5kghtJd" data-aplus-clk="x41_55a80716">
        <div class="Ms6aG">
            <div class="qmXQo">
                <div class="ICdUp">
                    <div class="_95X4G">
                        <a href="..." data-spm-anchor-id="...">
                            <div class="picture-wrapper jBwCF ">
                                <img type="product" alt="..." src="..." data-spm-anchor-id="a2a0e.searchlist.list.i43.2a1629f5kghtJd" style="object-fit: fill;">
                            </div>
                        </a>
                    </div>
                </div>
                <div class="buTCk">
                    <div class="ajfs+"></div>
                    <div class="RfADt">
                        <a href="..." title="" data-spm-anchor-id="...">
                            ...
                        </a>
                    </div>
                    <div class="aBrP0">
                        <span class="ooOxS">
                            ...
                        </span>
                    </div>
                    <div class="WNoq3">
                        <span class="ic-dynamic-badge ic-dynamic-badge-text ic-dynamic-badge-153138 ic-dynamic-group-2" style="color: rgb(237, 136, 41); background-color: rgb(253, 243, 234);">
                            ...
                        </span>
                    </div>
                    <div class="_6uN7R">
                        <span class="oa6ri " title="Overseas">
                            ...
                        </span>
                    </div>
                </div>
            </div>
        </div>
    </div>
    """
    schema = await load_or_generate_schema(link, sample_html)

    # Setup extraction config
    extraction_strategy = JsonCssExtractionStrategy(schema, verbose=True)

    config = CrawlerRunConfig(
        extraction_strategy=extraction_strategy,
        cache_mode=CacheMode.DISABLED,
        geolocation=GeolocationConfig(latitude=48.8566, longitude=2.3522),
        prettiify=True,
        wait_for_images=True,
        delay_before_return_html=True,
        mean_delay=0.0000001,
        scroll_delay=0.0000001,
        verbose=True,
        # bypass_cache=True,           # ✅ helps ensure fresh responses from the browser context
        # wait_until="networkidle",  # You can uncomment to ensure network settles before extraction
    )

    # Generate list of page URLs
    urls = [f"{link}?page={page}" for page in page_range]

    # Load existing products (so we detect repeats across runs)
    existing_products_list = load_json_if_exists(OUTPUT_FILE, default=[])
    existing_products_list = existing_products_list if isinstance(existing_products_list, list) else []
    # Index by product id
    all_products_by_id: Dict[str, dict] = {get_product_id(p): p for p in existing_products_list if get_product_id(p)}
    known_ids = set(all_products_by_id.keys())

    pages_index = load_json_if_exists(PAGES_INDEX_FILE, default={})  # page -> list of ids

    browser_config = BrowserConfig(
        headless=False,
        # enable_stealth=True,
        # viewport_width=1920,
        # viewport_height=1080
    )

    total_new_added = 0

    async with AsyncWebCrawler(config=browser_config) as crawler:
        # 🔹 Crawl each page sequentially
        for page_idx, base_url in enumerate(urls, start=1):
            products, ids, attempts_used = await fetch_until_new(
                crawler=crawler,
                base_url=base_url,
                config=config,
                known_ids=known_ids,
                page_idx=page_idx,
                max_retries=MAX_RETRIES,
                min_new=MIN_NEW_PER_PAGE,
                add_cache_bust=ADD_CACHE_BUST,
            )

            if not products:
                print(f"⚠️ Page {page_idx}: no products found after {attempts_used} attempts.")
                continue

            # Only keep *new* products for saving (optional, but aligns with your goal)
            page_new_products: List[dict] = []
            for p in products:
                pid = get_product_id(p)
                if not pid:
                    continue
                if pid not in known_ids:
                    known_ids.add(pid)
                    all_products_by_id[pid] = p
                    page_new_products.append(p)

            pages_index[str(page_idx)] = ids  # record what we saw for this page (new or not)

            if SAVE_ONLY_UNIQUE:
                to_save_page = page_new_products
            else:
                to_save_page = products  # save everything the page had, even repeats

            if to_save_page:
                # 🔹 Save per-page aggregated JSON (only new items if SAVE_ONLY_UNIQUE=True)
                atomic_write_json(RESULT_DIR / f"page_{page_idx}.json", to_save_page)
                total_new_added += len(page_new_products)
                print(f"✅ Page {page_idx}: saved {len(to_save_page)} items "
                      f"({len(page_new_products)} new).")
            else:
                print(f"ℹ️ Page {page_idx}: produced no new items after {attempts_used} attempts; skipping per-page save.")

    # 🔹 Save all extracted products to JSON inside result/ (unique by id)
    all_products_unique = list(all_products_by_id.values())
    atomic_write_json(OUTPUT_FILE, all_products_unique)
    atomic_write_json(PAGES_INDEX_FILE, pages_index)

    print(f"✅ Finished. Pages crawled: {len(urls)}, total unique products now: {len(all_products_unique)}, "
          f"new added this run: {total_new_added}")


async def main():
    print("=== Crawl4AI Optimized Demo (sequential with new-content retries) ===")
    link = "https://www.daraz.com.bd/hoses-pipes/"
    page_range = range(1, 25)
    await demo_css_structured_extraction_no_schema(link, page_range)
    print("\n=== Demo Complete ===")
    print(f"Check {OUTPUT_FILE} for extracted products.")


if __name__ == "__main__":
    asyncio.run(main())