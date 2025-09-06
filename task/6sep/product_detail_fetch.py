import asyncio
import os
import json
from pathlib import Path
from typing import List

from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode, CrawlResult

from crawl4ai import JsonCssExtractionStrategy
from crawl4ai import LLMConfig
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

__cur_dir__ = Path(__file__).parent

async def demo_css_structured_extraction_no_schema():
    """Extract structured data using CSS selectors"""
    print("\n=== 5. CSS-Based Structured Extraction ===")
    # Sample HTML for schema generation (one-time cost)
    sample_html = """
<div id="block-v5ORciPkKSv" class="pdp-block pdp-block__product-detail">
   <div id="module_flash_sale" class="pdp-block module"></div>
   <div id="module_crazy_deal" class="pdp-block module"></div>
   <div id="module_redmart_top_promo_banner" class="pdp-block module"></div>
   <div id="module_product_title_1" class="pdp-block module">
      <div class="pdp-product-title">
         <div class="pdp-mod-product-badge-wrapper">
            <h1 class="pdp-mod-product-badge-title" data-spm-anchor-id="a2a0e.pdp_revamp.0.i0.44746796p9Pm5f">High quality men's shoes ( imported)</h1>
         </div>
      </div>
   </div>
   <div id="module_pre-order-tag" class="pdp-block module"></div>
   <div id="block-Yd7Db7ZOjL5" class="pdp-block pdp-block__rating-questions-summary">
      <div id="block-NA-owqLNMDJ" class="pdp-block pdp-block__rating-questions">
         <div id="module_product_review_star_1" class="pdp-block module">
            <div class="pdp-review-summary">
               <div class="container-star pdp-review-summary__stars pdp-stars_size_s"><img class="star" src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAB4AAAAeCAMAAAAM7l6QAAAABGdBTUEAALGPC/xhBQAAAAFzUkdCAK7OHOkAAAA/UExURf/XAPakAPalAPenAPakAPalAPenAEdwTP+vAP69APalAPivAPemAPmrAP+1APelAPakAPalAPmvAPioAPajAHElIkoAAAAUdFJOUxr0zm3rwngADSm3TZRFBqfggTda/y+eEwAAAPRJREFUKM+N09mShCAMBdCwNjuC9/+/dQDLaaCnrcmDVeSQCIL0egxah0Y8smbmgY1EeWANLs1XNlJF6K8s4Mkt5TMnqYjWctqKaS2f2BytmMjP5Z2TjSK4A6OYSIHxXM5qBpeWR88EMZSqDmrkJLf0MgrOW9qjCoazN28uPpQsbzre/Zdfeq08OehdmX9vbPdb732nPHvTuH6WxPLEv8d6s0GZmsuwccU5sVIbC9Sr73hmtnFgPX1yFvoEDVpZ8XZWCkdGn+CxrVzm6CBFetkMWex9qHcTHJD6ugfVtUFeOIKV9yWJCnxhEdYb7VdO//vH9vgB7woXsbjqY50AAAAASUVORK5CYII="><img class="star" src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAB4AAAAeCAMAAAAM7l6QAAAABGdBTUEAALGPC/xhBQAAAAFzUkdCAK7OHOkAAAA/UExURf/XAPakAPalAPenAPakAPalAPenAEdwTP+vAP69APalAPivAPemAPmrAP+1APelAPakAPalAPmvAPioAPajAHElIkoAAAAUdFJOUxr0zm3rwngADSm3TZRFBqfggTda/y+eEwAAAPRJREFUKM+N09mShCAMBdCwNjuC9/+/dQDLaaCnrcmDVeSQCIL0egxah0Y8smbmgY1EeWANLs1XNlJF6K8s4Mkt5TMnqYjWctqKaS2f2BytmMjP5Z2TjSK4A6OYSIHxXM5qBpeWR88EMZSqDmrkJLf0MgrOW9qjCoazN28uPpQsbzre/Zdfeq08OehdmX9vbPdb732nPHvTuH6WxPLEv8d6s0GZmsuwccU5sVIbC9Sr73hmtnFgPX1yFvoEDVpZ8XZWCkdGn+CxrVzm6CBFetkMWex9qHcTHJD6ugfVtUFeOIKV9yWJCnxhEdYb7VdO//vH9vgB7woXsbjqY50AAAAASUVORK5CYII="><img class="star" src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAB4AAAAeCAMAAAAM7l6QAAAABGdBTUEAALGPC/xhBQAAAAFzUkdCAK7OHOkAAAA/UExURf/XAPakAPalAPenAPakAPalAPenAEdwTP+vAP69APalAPivAPemAPmrAP+1APelAPakAPalAPmvAPioAPajAHElIkoAAAAUdFJOUxr0zm3rwngADSm3TZRFBqfggTda/y+eEwAAAPRJREFUKM+N09mShCAMBdCwNjuC9/+/dQDLaaCnrcmDVeSQCIL0egxah0Y8smbmgY1EeWANLs1XNlJF6K8s4Mkt5TMnqYjWctqKaS2f2BytmMjP5Z2TjSK4A6OYSIHxXM5qBpeWR88EMZSqDmrkJLf0MgrOW9qjCoazN28uPpQsbzre/Zdfeq08OehdmX9vbPdb732nPHvTuH6WxPLEv8d6s0GZmsuwccU5sVIbC9Sr73hmtnFgPX1yFvoEDVpZ8XZWCkdGn+CxrVzm6CBFetkMWex9qHcTHJD6ugfVtUFeOIKV9yWJCnxhEdYb7VdO//vH9vgB7woXsbjqY50AAAAASUVORK5CYII="><img class="star" src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAB4AAAAeCAMAAAAM7l6QAAAABGdBTUEAALGPC/xhBQAAAAFzUkdCAK7OHOkAAAA/UExURf/XAPakAPalAPenAPakAPalAPenAEdwTP+vAP69APalAPivAPemAPmrAP+1APelAPakAPalAPmvAPioAPajAHElIkoAAAAUdFJOUxr0zm3rwngADSm3TZRFBqfggTda/y+eEwAAAPRJREFUKM+N09mShCAMBdCwNjuC9/+/dQDLaaCnrcmDVeSQCIL0egxah0Y8smbmgY1EeWANLs1XNlJF6K8s4Mkt5TMnqYjWctqKaS2f2BytmMjP5Z2TjSK4A6OYSIHxXM5qBpeWR88EMZSqDmrkJLf0MgrOW9qjCoazN28uPpQsbzre/Zdfeq08OehdmX9vbPdb732nPHvTuH6WxPLEv8d6s0GZmsuwccU5sVIbC9Sr73hmtnFgPX1yFvoEDVpZ8XZWCkdGn+CxrVzm6CBFetkMWex9qHcTHJD6ugfVtUFeOIKV9yWJCnxhEdYb7VdO//vH9vgB7woXsbjqY50AAAAASUVORK5CYII="><img class="star" src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAB4AAAAeCAMAAAAM7l6QAAAABGdBTUEAALGPC/xhBQAAAAFzUkdCAK7OHOkAAAA/UExURf/XAPakAPalAPenAPakAPalAPenAEdwTP+vAP69APalAPivAPemAPmrAP+1APelAPakAPalAPmvAPioAPajAHElIkoAAAAUdFJOUxr0zm3rwngADSm3TZRFBqfggTda/y+eEwAAAPRJREFUKM+N09mShCAMBdCwNjuC9/+/dQDLaaCnrcmDVeSQCIL0egxah0Y8smbmgY1EeWANLs1XNlJF6K8s4Mkt5TMnqYjWctqKaS2f2BytmMjP5Z2TjSK4A6OYSIHxXM5qBpeWR88EMZSqDmrkJLf0MgrOW9qjCoazN28uPpQsbzre/Zdfeq08OehdmX9vbPdb732nPHvTuH6WxPLEv8d6s0GZmsuwccU5sVIbC9Sr73hmtnFgPX1yFvoEDVpZ8XZWCkdGn+CxrVzm6CBFetkMWex9qHcTHJD6ugfVtUFeOIKV9yWJCnxhEdYb7VdO//vH9vgB7woXsbjqY50AAAAASUVORK5CYII="></div>
               <a class="pdp-link pdp-link_size_s pdp-link_theme_blue pdp-review-summary__link">No Ratings</a>
            </div>
         </div>
      </div>
      <div id="block-8mV_sBWU8UA" class="pdp-block pdp-block__share">
         <div id="block-CY_96LuQuUf" class="pdp-block" style="display: inline-block; width: 24px; height: 54px;">
            <div id="module_product_share_1" class="pdp-block module">
               <div class="lazyload-wrapper ">
                  <div class="pdp-share">
                     <div class="pdp-share__share-button">
                        <span class="pdp-share__share-button-icon">
                           <svg class="lazadaicon lazada-icon svgfont " aria-hidden="true">
                              <use xlink:href="#lazadaicon_largeShare"></use>
                           </svg>
                        </span>
                     </div>
                  </div>
               </div>
            </div>
         </div>
         <div id="block-zHNbEnATKRN" class="pdp-block" style="display: inline-block;">
            <div id="module_product_wishlist_1" class="pdp-block module">
               <div class="pdp-mod-wishlist">
                  <span class="wishlist-icon ">
                     <svg class="lazadaicon lazada-icon svgfont " aria-hidden="true">
                        <use xlink:href="#lazadaicon_emptyHeart"></use>
                     </svg>
                  </span>
               </div>
            </div>
         </div>
      </div>
   </div>
   <div id="module_product_brand_1" class="pdp-block module">
      <div class="pdp-product-brand">
         <span class="pdp-product-brand__name">Brand: </span><a class="pdp-link pdp-link_size_s pdp-link_theme_blue pdp-product-brand__brand-link" target="_self" href="https://www.daraz.com.bd/no-brand-1/?type=brand">No Brand</a>
         <div class="pdp-product-brand__divider"></div>
         <a class="pdp-link pdp-link_size_s pdp-link_theme_blue pdp-product-brand__suggestion-link" target="_self" href="https://www.daraz.com.bd/mens-fashion/no-brand-1/" style="max-width: calc(100% - 106px);">More Men from No Brand</a>
      </div>
   </div>
   <div id="module_product_attrs" class="pdp-block module"></div>
   <div id="block-6LMEH49-SCr" class="pdp-block module"></div>
   <div id="module_product_price_1" class="pdp-block module">
      <div class="pdp-mod-product-price" data-spm-anchor-id="a2a0e.pdp_revamp.0.i3.44746796p9Pm5f">
         <div class="pdp-product-price">
            <span class="notranslate pdp-price pdp-price_type_normal pdp-price_color_orange pdp-price_size_xl">৳ 5,900</span>
            <div class="origin-block"><span class="notranslate pdp-price pdp-price_type_deleted pdp-price_color_lightgray pdp-price_size_xs">৳ 8,500</span><span class="pdp-product-price__discount">-31%</span></div>
         </div>
      </div>
   </div>
   <div id="module_redmart_product_price" class="pdp-block module"></div>
   <div id="module_promotion_tags" class="pdp-block module"></div>
   <div id="module_installment" class="pdp-block module"></div>
   <div id="module_sku-select" class="pdp-block module">
      <div class="sku-selector">
         <div class="sku-prop">
            <div class="pdp-mod-product-info-section sku-prop-selection">
               <h6 class="section-title">Color Family</h6>
               <div class="section-content">
                  <div class="sku-prop-content-header"><span class="sku-name ">Blue</span></div>
                  <div class="sku-prop-content sku-prop-content-">
                     <span class="sku-variable-img-wrap">
                        <div class="pdp-common-image sku-variable-img">
                           <div class="lazyload-wrapper "><img class="image" alt="" src="https://img.drz.lazcdn.com/g/kf/S3fdbe5876a9a4f2894fd157c85636216h.jpg_80x80q80.jpg_.webp"></div>
                        </div>
                     </span>
                     <span class="sku-variable-img-wrap">
                        <div class="pdp-common-image sku-variable-img">
                           <div class="lazyload-wrapper "><img class="image" alt="" src="https://img.drz.lazcdn.com/g/kf/S9185b43613754f109dcd15ba4178ace8Y.jpg_80x80q80.jpg_.webp"></div>
                        </div>
                     </span>
                     <span class="sku-variable-img-wrap-selected">
                        <div class="pdp-common-image sku-variable-img">
                           <div class="lazyload-wrapper "><img class="image" alt="" src="https://img.drz.lazcdn.com/g/kf/S31d477f103ca415ab15c53f9ed38b6afS.jpg_80x80q80.jpg_.webp"></div>
                        </div>
                        <span class="lzd-svg-icon lzd-svg-icon_name_optionChecked sku-variable-img-icon">
                           <svg class="lazadaicon lazada-icon svgfont " aria-hidden="true">
                              <use xlink:href="#lazadaicon_optionChecked"></use>
                           </svg>
                        </span>
                     </span>
                  </div>
               </div>
            </div>
            <span class="pdp_center_target"></span>
         </div>
         <div class="sku-prop">
            <div class="pdp-mod-product-info-section sku-prop-selection">
               <h6 class="section-title">Size</h6>
               <div class="section-content">
                  <div class="sku-prop-content-header"><span class="sku-size-drop sku-size-drop-single"><span class="sku-tabpath-single"> Full Look </span></span></div>
                  <div class="sku-prop-content sku-prop-content-"><span class="sku-variable-size-selected" title=" 36"> 36</span><span class="sku-variable-size" title=" 38"> 38</span><span class="sku-variable-size" title=" 40"> 40</span><span class="sku-variable-size" title=" 42"> 42</span><span class="sku-variable-size" title=" 44"> 44</span></div>
               </div>
            </div>
            <span class="pdp_center_target"></span>
         </div>
      </div>
   </div>
   <div id="module_quantity-input" class="pdp-block module">
      <div class="pdp-mod-product-info-section sku-quantity-selection">
         <h6 class="section-title">Quantity</h6>
         <div class="section-content">
            <div class="next-number-picker next-number-picker-inline">
               <div class="next-number-picker-handler-wrap"><a unselectable="unselectable" class="next-number-picker-handler next-number-picker-handler-up "><span unselectable="unselectable" class="next-number-picker-handler-up-inner"><i class="next-icon next-icon-add next-icon-medium"></i></span></a><a unselectable="unselectable" class="next-number-picker-handler next-number-picker-handler-down next-number-picker-handler-down-disabled"><span unselectable="unselectable" class="next-number-picker-handler-down-inner"><i class="next-icon next-icon-minus next-icon-medium"></i></span></a></div>
               <div class="next-number-picker-input-wrap"><span class="next-input next-input-single next-input-medium next-number-picker-input"><input min="1" max="10" step="1" autocomplete="off" type="text" height="100%" value="1"></span></div>
            </div>
            <span class="quantity-content-default"></span>
         </div>
      </div>
   </div>
   <div id="module_sms-phone-input" class="pdp-block module"></div>
   <div id="module_add_to_cart" class="pdp-block module">
      <div class="pdp-cart-concern">
         <button class="add-to-cart-buy-now-btn  pdp-button pdp-button_type_text pdp-button_theme_bluedaraz pdp-button_size_xl"><span class="pdp-button-text"><span class="">Buy Now</span></span></button><button class="add-to-cart-buy-now-btn  pdp-button pdp-button_type_text pdp-button_theme_orange pdp-button_size_xl"><span class="pdp-button-text"><span class="">Add to Cart</span></span></button>
         <form method="post" action=""><input name="buyParams" type="hidden" value="{&quot;items&quot;:[{&quot;itemId&quot;:&quot;378023244&quot;,&quot;skuId&quot;:&quot;1895600854&quot;,&quot;quantity&quot;:1,&quot;attributes&quot;:null}]}"></form>
      </div>
   </div>
   <div id="module_redmart_add_to_cart" class="pdp-block module"></div>
</div>
    """

    # Check if schema file exists
    schema_file_path = f"{__cur_dir__}/schema.json"
    if os.path.exists(schema_file_path):
        with open(schema_file_path, "r") as f:
            schema = json.load(f)
    else:
        # Generate schema using LLM (one-time setup)
        schema = JsonCssExtractionStrategy.generate_schema(
            html=sample_html,
            llm_config=LLMConfig(
            provider="gemini/gemini-2.0-flash-lite-preview-02-05",
            api_token=os.getenv("GEMINI_API_KEY", os.getenv('GEMINI_API_KEY')),
        ),
           query=(
            f"""this is a div from an ecommerce single product page,
            I shared a div for some detail data about the product. 
            Please generate a schema those information. 
            """
        ),
    )

    print(f"Generated schema: {json.dumps(schema, indent=2)}")
    # Save the schema to a file , and use it for future extractions, in result for such extraction you will call LLM once
    with open(f"{__cur_dir__}/schema.json", "w") as f:
        json.dump(schema, f, indent=2)

    # Create no-LLM extraction strategy with the generated schema
    extraction_strategy = JsonCssExtractionStrategy(schema)
    config = CrawlerRunConfig(extraction_strategy=extraction_strategy)

    # Use the fast CSS extraction (no LLM calls during extraction)
    async with AsyncWebCrawler() as crawler:
        results: List[CrawlResult] = await crawler.arun(
            "https://www.daraz.com.bd/products/high-quality-mens-shoes-imported-i378023244-s1895600858.html", config=config
        )

        for result in results:
            print(f"URL: {result.url}")
            print(f"Success: {result.success}")
            if result.success:
                data = json.loads(result.extracted_content)
                print(json.dumps(data, indent=2))
            else:
                print("Failed to extract structured data")


async def main():
    """Run all demo functions sequentially"""
    print("=== Comprehensive Crawl4AI Demo ===")
    print("Note: Some examples require API keys or other configurations")

    # Run all demos

    await demo_css_structured_extraction_no_schema()

    # Clean up any temp files that may have been created
    print("\n=== Demo Complete ===")
    print("Check for any generated files (screenshots, PDFs) in the current directory")

if __name__ == "__main__":
    asyncio.run(main())