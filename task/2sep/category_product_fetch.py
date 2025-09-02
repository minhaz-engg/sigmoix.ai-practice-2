import os
import re
import json
import math
import time
import random
import asyncio
from typing import List, Dict, Tuple, Iterable
from pathlib import Path
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

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
MAX_RETRIES = 5                 # max tries per page if we only see previously-seen products
MIN_NEW_PER_PAGE = 1            # require at least this many new items to accept a page
RETRY_BACKOFF_BASE = 1.5        # exponential backoff base (in seconds); was 0.8
ADD_CACHE_BUST = True           # append a harmless cache-busting query param on each retry
SAVE_ONLY_UNIQUE = True         # when writing per-page JSON, keep only products that are new vs. global set
PRODUCTS_PER_PAGE = 40          # ✅ Daraz shows 40 products per page
PAGE_PARAM = "page"             # name of the page query parameter

# Pacing & block-handling
PAGE_PAUSE_RANGE = (1.8, 3.8)   # random sleep between pages to look human
ATTEMPT_JITTER = 0.3            # random +/- jitter added to backoff
BLOCK_COOLDOWN_RANGE = (35, 75) # if blocked, sleep this many seconds before next attempt
# ------------------------------


# ----- Utilities -----
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


def set_query_param(url: str, key: str, value: str) -> str:
    p = urlparse(url)
    q = parse_qsl(p.query, keep_blank_values=True)
    q_dict = dict(q)
    q_dict[key] = value
    new_query = urlencode(q_dict, doseq=True)
    new_url = urlunparse((p.scheme, p.netloc, p.path, p.params, new_query, p.fragment))
    return new_url


def build_page_url(base_url: str, page: int) -> str:
    return set_query_param(base_url, PAGE_PARAM, str(page))


def parse_total_items_from_html(html: str) -> int:
    if not html:
        return 0
    patterns = [
        r'([\d,\.]+)\s*items\s*found',                 # 1114 items found / 1,114 items found in
        r'"totalResults"\s*:\s*(\d+)',                 # "totalResults": 1114
        r'"resultCount"\s*:\s*(\d+)',                  # "resultCount": 1114
        r'"total"\s*:\s*(\d+)',                        # "total": 1114
        r'data-total-items\s*=\s*"(\d+)"',
    ]
    for pat in patterns:
        m = re.search(pat, html, flags=re.IGNORECASE)
        if m:
            raw = m.group(1)
            clean = raw.replace(",", "").replace(".", "")
            try:
                return int(clean)
            except ValueError:
                continue
    return 0


async def detect_total_pages(crawler: AsyncWebCrawler, category_url: str) -> int:
    simple_config = CrawlerRunConfig(
        cache_mode=CacheMode.DISABLED,
        geolocation=GeolocationConfig(latitude=23.8103, longitude=90.4125),
        prettiify=False,
        wait_for_images=False,
        delay_before_return_html=False,
        mean_delay=0.1,      # tiny but non-zero
        scroll_delay=0.2,
        verbose=True,
    )
    url = category_url
    if ADD_CACHE_BUST:
        url = set_query_param(url, "_v", str(int(time.time() * 1000)))
    try:
        results: List[CrawlResult] = await crawler.arun(
            url=url,
            config=simple_config,
            js_code="""await new Promise(r => setTimeout(r, 700));""",
            wait_for="css:body",
        )
    except Exception as e:
        print(f"⚠️ Failed to fetch first page for total count: {e}")
        return 1

    html = ""
    for res in results or []:
        if res and res.html:
            html = res.html
            break

    total_items = parse_total_items_from_html(html)
    if total_items <= 0:
        print("⚠️ Could not parse total items; defaulting to 1 page.")
        return 1
    total_pages = max(1, math.ceil(total_items / PRODUCTS_PER_PAGE))
    print(f"ℹ️ Detected total items: {total_items} → total pages: {total_pages}")
    return total_pages


def get_product_id(product: dict) -> str:
    pid = (product.get("data_item_id") or "").strip()
    if pid:
        return pid
    sku = (product.get("data_sku_simple") or "").strip()
    if sku:
        return sku.split("_", 1)[0].strip()
    return ""


def dedupe_products(products: Iterable[dict]) -> List[dict]:
    seen: set = set()
    deduped = []
    for p in products:
        pid = get_product_id(p)
        if not pid:
            continue
        if pid in seen:
            continue
        seen.add(pid)
        deduped.append(p)
    return deduped


# ----- Block detection -----
BLOCK_KEYWORDS = [
    "captcha", "access denied", "temporarily blocked", "unusual traffic",
    "robot check", "verify you are a human", "request blocked",
    "are you a robot", "forbidden", "not allowed", "blocked due to unusual activity"
]

class BlockedError(Exception):
    pass

def looks_blocked(html: str) -> bool:
    if not html:
        return False
    h = html.lower()
    return any(k in h for k in BLOCK_KEYWORDS)


# ----- LLM schema -----
async def load_or_generate_schema(link: str, sample_html: str) -> dict:
    if os.path.exists(SCHEMA_FILE):
        with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    schema = JsonCssExtractionStrategy.generate_schema(
        html=sample_html,
        llm_config=LLMConfig(
            provider="gemini/gemini-2.0-flash-lite-preview-02-05",
            api_token=os.getenv("GEMINI_API_KEY"),
        ),
        query=(
            f"""From {link} from an ecommerce site,
            I shared one product div. Please generate a schema extracting ALL product info
            Please generate a schema for this product div. i need all all all informations of a product. i also need product detail url for each product, i also need product image url for each product."""
        ),
    )
    atomic_write_json(SCHEMA_FILE, schema)
    return schema


# ----- Crawl primitives -----
async def crawl_once(
    crawler: AsyncWebCrawler,
    url: str,
    config: CrawlerRunConfig,
    page_idx: int,
    attempt: int,
) -> Tuple[List[dict], List[str]]:
    # Simulate more human-like viewing with incremental scrolls
    js_seq = """
        const sleep = ms => new Promise(r => setTimeout(r, ms));
        await sleep(800);
        for (let y=0; y<=3; y++){
            window.scrollBy(0, document.body.scrollHeight/3);
            await sleep(500 + Math.floor(Math.random()*300));
        }
        window.scrollTo(0, 0);
        await sleep(400);
    """

    results: List[CrawlResult] = await crawler.arun(
        url=url,
        config=config,
        js_code=js_seq,
        wait_for="css:.gridItem, .product-item, [data-qa-locator='product-item'], .Bm3ON",
    )

    page_products_aggregated: List[dict] = []
    blocked_detected = False

    for res_idx, result in enumerate(results, start=1):
        if not result.success:
            # If site responded but blocked, result may still be 'success' from a network POV.
            # We'll rely on HTML inspection below.
            continue

        html = result.html or ""
        if looks_blocked(html):
            blocked_detected = True

        try:
            data = json.loads(result.extracted_content)
            page_products = data if isinstance(data, list) else [data]
            page_products_aggregated.extend(page_products)
        except Exception as e:
            # If blocked, content might be non-JSON (captcha/403 page)
            pass

    if blocked_detected and not page_products_aggregated:
        # Nothing usable and the page looks blocked → escalate
        raise BlockedError("Possible bot detection/CAPTCHA page.")

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
    for attempt in range(1, max_retries + 1):
        url = base_url
        if add_cache_bust:
            url = set_query_param(url, "_v", str(int(time.time() * 1000)))

        print(f"--- Crawling page {page_idx} (attempt {attempt}): {url} ---")
        try:
            products, ids = await crawl_once(crawler, url, config, page_idx, attempt)
        except BlockedError as be:
            cooldown = random.uniform(*BLOCK_COOLDOWN_RANGE)
            print(f"🛑 Block detected on page {page_idx}. Cooling down for {cooldown:.1f}s.")
            await asyncio.sleep(cooldown)
            continue
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

        backoff = RETRY_BACKOFF_BASE * (2 ** (attempt - 1)) + random.uniform(-ATTEMPT_JITTER, ATTEMPT_JITTER)
        backoff = max(0.5, backoff)
        await asyncio.sleep(backoff)

    return products, ids, max_retries


# ----- Main flow -----
async def demo_css_structured_extraction_no_schema(link: str):
    print("\n=== CSS-Based Structured Extraction with Auto Page Range + Anti-Block ===")

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
    extraction_strategy = JsonCssExtractionStrategy(schema, verbose=True)

    # Optional proxy rotation via .env PROXY_LIST="http://user:pass@host1:port,http://user:pass@host2:port"
    # proxies = [p.strip() for p in (os.getenv("PROXY_LIST") or "").split(",") if p.strip()]
    # proxy_rotation_strategy = ProxyRotationStrategy(proxies=proxies) if proxies else None

    config = CrawlerRunConfig(
        extraction_strategy=extraction_strategy,
        cache_mode=CacheMode.DISABLED,
        geolocation=GeolocationConfig(latitude=48.8566, longitude=2.3522),
        prettiify=True,
        wait_for_images=True,
        delay_before_return_html=True,
        mean_delay=0.7,        # be less robotic
        scroll_delay=0.6,
        verbose=True,
        # wait_until="networkidle",
        # proxy_rotation_strategy=proxy_rotation_strategy,
    )

    # Load existing products (so we detect repeats across runs)
    existing_products_list = load_json_if_exists(OUTPUT_FILE, default=[])
    existing_products_list = existing_products_list if isinstance(existing_products_list, list) else []
    all_products_by_id: Dict[str, dict] = {pid: p for p in existing_products_list if (pid := get_product_id(p))}
    known_ids = set(all_products_by_id.keys())

    pages_index = load_json_if_exists(PAGES_INDEX_FILE, default={})  # page -> list of ids

    browser_config = BrowserConfig(
        headless=False,
        # enable_stealth=True,   # ✅ important
        # user_data_dir=str(RESULT_DIR / "user_data"),  # ⬅️ enable if your crawl4ai supports persistent sessions
        # viewport_width=1366, viewport_height=768,
    )

    total_new_added = 0

    async with AsyncWebCrawler(config=browser_config) as crawler:
        total_pages = await detect_total_pages(crawler, link)
        urls = [build_page_url(link, page) for page in range(1, total_pages + 1)]

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
                # longer pause before next page after a tough page
                await asyncio.sleep(random.uniform(*PAGE_PAUSE_RANGE) + 1.5)
                continue

            page_new_products: List[dict] = []
            for p in products:
                pid = get_product_id(p)
                if pid and pid not in known_ids:
                    known_ids.add(pid)
                    all_products_by_id[pid] = p
                    page_new_products.append(p)

            pages_index[str(page_idx)] = ids
            to_save_page = page_new_products if SAVE_ONLY_UNIQUE else products

            if to_save_page:
                atomic_write_json(RESULT_DIR / f"page_{page_idx}.json", to_save_page)
                total_new_added += len(page_new_products)
                print(f"✅ Page {page_idx}: saved {len(to_save_page)} items "
                      f"({len(page_new_products)} new).")
            else:
                print(f"ℹ️ Page {page_idx}: produced no new items after {attempts_used} attempts; skipping per-page save.")

            # polite pause between pages
            await asyncio.sleep(random.uniform(*PAGE_PAUSE_RANGE))

    all_products_unique = list(all_products_by_id.values())
    atomic_write_json(OUTPUT_FILE, all_products_unique)
    atomic_write_json(PAGES_INDEX_FILE, pages_index)

    print(f"✅ Finished. Pages crawled: {len(urls)}, total unique products now: {len(all_products_unique)}, "
          f"new added this run: {total_new_added}")


async def main():
    print("=== Crawl4AI (auto pages + anti-block) ===")
    link = "https://www.daraz.com.bd/hoses-pipes/"  # any category/search URL
    await demo_css_structured_extraction_no_schema(link)
    print("\n=== Demo Complete ===")
    print(f"Check {OUTPUT_FILE} for extracted products.")


if __name__ == "__main__":
    asyncio.run(main())
