from firecrawl import FirecrawlApp
from pydantic import BaseModel
from dotenv import load_dotenv
import os


load_dotenv()

app = FirecrawlApp(api_key=os.getenv("FIRECRAWL_API_KEY"))

class ExtractSchema(BaseModel):
    product_name: str
    price: float
    details: str
    images: list[str]
    colors: list[str]
    brand: str
    seller_info: str
    product_details: str

json_config = JsonConfig(schema=ExtractSchema)

llm_extraction_result = app.scrape_url(
    url="https://www.daraz.com.bd/products/poedagar-stainless-steel-top-luxury-quartz-fashion-watch-for-men-i334810443-s1628421463.html",
    formats=["json"],
    json_options=json_config,
    only_main_content=False,
    timeout=120000
)

print(llm_extraction_result.json)