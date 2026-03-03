import time
import re
from datetime import datetime
from urllib.parse import urlparse
import pandas as pd

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

OUTPUT_CSV="snapdeal_products.csv"
Headless=True
SCROLL_PAUSE=0.2
LISTING_WAIT=5
PRODUCT_WAIT=5
MAX_PAGES_PER_SUBCAT=5
DEEP_SCRAPE=True
LEFT_X_THRESHOLD=420
MAX_PRODUCTS_PER_SUBCAT=None

BASE_SECTIONS={
    "Accessories":"https://www.snapdeal.com/products/fashion-men?sort=plrty",
    "Footwear":"https://www.snapdeal.com/products/womens-footwear?sort=plrty",
    "Kids Fashion": "https://www.snapdeal.com/products/kids-clothing?sort=plrty",
    "Men's Clothing":"https://www.snapdeal.com/products/men-apparel?sort=plrty",
    "Women's Clothing":"https://www.snapdeal.com/products/womens-ethnicwear?sort=plrty"
}

chrome_opts=Options()
if Headless:
    chrome_opts.add_argument("--headless=new")
chrome_opts.add_argument("--disable-gpu")
chrome_opts.add_argument("--window_size=1920,1080")
chrome_opts.add_argument("--no-sandbox")
chrome_opts.add_argument("--disable-dev-shm-usage")
chrome_opts.add_argument("--disable-extensions")
chrome_opts.add_argument("--disable-plugins")
chrome_opts.add_argument("--disable-background-networking")
prefs={
    "profile.managed_default_content_settings.images":2,
    "profile.deault_content_setting_values.notifications":2,
}

driver=webdriver.Chrome(service=Service(ChromeDriverManager().install()),options=chrome_opts)
wait=WebDriverWait(driver,LISTING_WAIT)

def extract_rating(soup):
    star=soup.select_one("span.filled-stars,div.filled-stars")
    if star and star.has_attr("style"):
        m=re.search(r"(\d+(?:\.\d+)?)%", star["style"])
        if m:
            return round(float(m.group(1))/20,2)
        return None

def human_sleep(sec):
    time.sleep(sec)

def scroll_to_bottom():
    last=driver.execute_script("return document.body.scrollHeight")
    while True:
        driver.execute_script("window.scrollTo(0,document.body.scrollHeight);")
        human_sleep(SCROLL_PAUSE)
        new=driver.execute_script("return document.body.scrollHeight")
        if new == last:
            break
        last = new

def clean_int(text:str)-> int:
    if not text:
        return 0
    nums=re.findall(r"\d+",text)
    return int(nums[0]) if nums else 0

def parse_rating_from_style(style: str)-> str:
    if not style:
        return ""
    m=re.search(r"(\d+(?:\.\d+)?)\s*%",style)
    if not m:
        return ""
    pct=float(m.group(1))
    return f"{round(pct/20,1)}"

def safe_text(e1):
    try:
        return e1.text.strip()
    except:
        return ""

def find_first(selector_list,in_el=None,attr=None,by=By.CSS_SELECTOR):
    ctx=in_el if in_el is not None else driver
    for sel in selector_list:
        try:
            el=ctx.find_element(by,sel)
            return el.get_attribute(attr).strip() if attr else el.text.strip()
        except:
            continue
    return ""

def find_all(selector,in_el=None,by=By.CSS_SELECTOR):
    ctx=in_el if in_el is not None else driver
    try:
        return ctx.find_elements(by,selector)
    except:
        return []

def get_left_subcategory_links():
    subcats=[]
    anchors=driver.find_elements(By.XPATH,"//a[@href]")
    seen=set()
    for a in anchors:
        try:
            href=a.get_attribute("href") or ""
            text=a.text.strip()
            if not text or len(text)>60 or len(text)<3:
                continue

            netloc=urlparse(href).netloc or ""
            if "snapdeal" not in netloc:
                continue
            if ("/products/" not in href) and ("/search" not in href):
                continue

            loc=a.location
            if loc and isinstance(loc.get("x", None), (int, float)) and loc["x"] < LEFT_X_THRESHOLD:
                key=(text,href)
                if key in seen:
                    continue
                lower=text.lower()
                if any(kw in lower for kw in ["price", "brand", "rating", "size", "color", "discount","customer", "ship", "cod", "delivery", "availability", "seller","apply", "clear", "sort", "view", "more", "less", "newest","4★", "3★", "2★", "1★"]):
                    continue

                if re.fullmatch(r"\d[\d,\. ]*", text):
                    continue
                subcats.append({"Subcategory": text,"URL":href})
                seen.add(key)
        except Exception:
            continue

    return subcats

def click_next_page():
    selectors=[
        "a[rel='next']",
        "a.pagination-number.next",
        "a.next",
        "//a[contains(translate(., 'NEXT', 'next'),'next')]",
        ]

    curr_url=driver.current_url
    for sel in selectors:
        try:
            if sel.startswith("//"):
                cand=driver.find_element(By.XPATH,sel)
            else:
                cand=driver.find_element(By.CSS_SELECTOR,sel)
            driver.execute_script("arguments[0].click();", cand)
            human_sleep(0.5)

            try:
                WebDriverWait(driver,4).until(EC.url_changes(curr_url))
            except:
                pass
            if driver.current_url != curr_url:
                return True
        except:
            continue
    return False


def _click_description_tab():
    tab_texts=["Description","Specifications","Product Details","Specification","Details"]
    for text in tab_texts:
        try:
            for xp in[
                f"//*[contains(@class,'tab')]//*[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'{text.lower()}')]",
                f"//*[contains(@class,'pdp')]//*[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'{text.lower()}')]",
                f"//a[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'{text.lower()}') and string-length(normalize-space(.))<30]",
                ]:
                el=driver.find_element(By.XPATH,xp)
                if el and el.is_displayed():
                    driver.execute_script("arguments[0].click();",el)
                    human_sleep(0.3)
                    return
        except Exception:
            continue

def _extract_rating_from_page():
    rating_val=find_first([      #Strategy 1:Text-based Rating
        "span[itemprop='ratingValue']",
        "[itemprop='ratingValue']",
        ".pdp-e-i-rating",
        ".avgRtaing",
        ".rating-value",
        "span.rating",
        ".product-rating",
    ])
    if rating_val:
        m=re.search(r"(\d+\.?\d*)",rating_val.replace(",","."))
        if m:
            return m.group(1).strip()
        
    star_style=find_first([  #Strategy 2:Style-based Rating
        ".filled-stars",
        "span.filled-stars",
        "div.filled-stars",
        "[class*='filled-star']"
    ],attr="style")

    if star_style:
        parsed=parse_rating_from_style(star_style)
        if parsed:
            return parsed
    
    #Strategy 3:Data Attributes
    rating_data=find_first([
        "[data-rating]",
        "[data-avgrating]",
    ],attr="data-rating")
    
    if rating_data:
        return rating_data
    
    style=find_first([".filled-stars",
                    ".star-filled",
                    "[class*='filled-star']"],attr="style")
    if style:
        return parse_rating_from_style(style)
    
    try:
        for xp in[
            "//*[contains(text(),'out of 5')]",
            "//*[contains(text(),'/5')]",
        ]:
            el=driver.find_element(By.XPATH,xp)
            t=(el.text or "").strip()
            m=re.search(r"(\\d+\\.?\\d*)",t)
            if m:
                return m.group(1)
    except Exception:
        pass
    
    return ""

def deep_scrape_product(url):
    data={"Brand":"","Full Description":"","Seller":"","Availability":"","Rating":"","Reviews Count":0,"Breadcrumb":"","Image URLs (detail)":""}
    if not url:
        return data

    parent=driver.current_window_handle
    try:
        driver.execute_script("window.open(arguments[0], '_blank');",url)
        WebDriverWait(driver,PRODUCT_WAIT).until(EC.number_of_windows_to_be(2))
        for h in driver.window_handles:
            if h != parent:
                driver.switch_to.window(h)
                break
            
        human_sleep(0.5)

        data["Brand"]=find_first(["span[itemprop='brand']","a#brand",".pdp-e-i-brand a",".pdp-e-i-brand",])

        data["Rating"]=_extract_rating_from_page()

        rc_text=find_first(["span[itemprop='reviewCount']",
                            "[itemprop='reviewCount']",
                            ".pdp-review-count",
                            ".product-review-count",
                            ".rating-count",
                            ".review-count",
                            "span.count",
                            ".avgRating + span",
                            "[class*='review-count']",
                            ])
        
        data["Reviews Count"]=clean_int(rc_text)
        
        avail=find_first([".sold-out-err","#isCODMsg",".availability-msg"])
        data["Availability"]=avail or "In stock"

        data["Seller"]=find_first(["#sellerName",".pdp-seller-info a",".pdp-seller-info"])
        _click_description_tab()
        human_sleep(0.2)
        
        description_candidates=["#description","#productDesc",
                                ".product-desc",".tab-content .spec-body",
                                ".spec-body",".details-info",
                                ".pdp-e-i-desc",".detailssubbox","#productSpecs"
                                ".productSpecs","div[class*='description']",
                                "div[class*='spec']",".tab-content",
                                "#productOverview",".product-overview",
                                "[id*='description']","[class*='product-desc']"
                                ,]
        
        body=""
        for sel in description_candidates:
            try:
                el=driver.find_element(By.CSS_SELECTOR,sel)
                text=el.text.strip() if el else ""
            except Exception:
                txt=""
            if txt and len(txt)>len(body) and len(txt)>30:
                body=txt
        if not body:
            for sel in description_candidates:
                txt=find_first([sel])
                if txt and len(txt)>len(body) and len(txt)>30:
                    body=txt
        data["Full Description"]=body

        crumbs=find_all("ul.breadcrumb li")
        if crumbs:
            data["Breadcrumb"]=">".join([safe_text(li) for li in crumbs if safe_text(li)])

        detail_imgs=[]
        for img in find_all(".cloudzoom"):
            src=img.get_attribute("src") or img.get_attribute("data-src")
            if src:
                detail_imgs.append(src)
        if not detail_imgs:
            for img in find_all("img"):
                s=img.get_attribute("src") or ""
                if s and "snapdeal" in s and ("images" in s or "img" in s):
                    detail_imgs.append(s)
        data["Image URLs (detail)"]=",".join(dict.fromkeys(detail_imgs))[:2000]

    except Exception as e:
        print(f"Error scraping {url}: {str(e)[:80]} - snapdeal_products_data.py:331")
        pass
    finally:
            try:
                driver.close()
                driver.switch_to.window(parent)
            except:
                pass
            
    return data

def scrape_listing_page(category_name,subcat_name,page_num,max_take=None):
    items=[]
    cards=find_all("div.product-tuple-listing")
    if not cards:
        cards=find_all("div.product-tuple")
        
    for idx,card in enumerate(cards,start=1):
        if max_take and len(items)>=max_take:
            break
        name=find_first(["p.product-title"],in_el=card) or ""
        price=find_first(["span.product-price"],in_el=card) or ""
        original_price=find_first(["span.product-desc-price.strike","span.lfloat.product-desc-price.strike"],in_el=card)
        discount=find_first(["div.product-discount","span.product-discount"],in_el=card)
        rating_list=""
        
        rating_text=find_first([
            "p.prod-rating",
            ".rating",
            ".product-rating",
            ".avgRating",
            "span[itemprop='ratingValue']"
        ],in_el=card)
        
        if rating_text and re.search(r"\d",rating_text):
            rating_list=rating_text
        else:
            rating_style=find_first([
                ".filled-stars",
                ".star-filled",
                "[class*='filled-star']"
            ], in_el=card,attr="style")

        if rating_style:
            rating_list=parse_rating_from_style(rating_style)

        rev_text=find_first(["p.product-rating-count",
                            ".rating-count",".review-count","span[class*='rating-count']",
                            "p[class*='rating']",
                            "[class*='review']"],in_el=card)
        reviews_count=clean_int(rev_text)
        img=find_first(["img.product-image"],in_el=card,attr="src")
        if not img:
            img=find_first(["img"],in_el=card,attr="src")

        url=find_first(["a.dp-widget-link"],in_el=card,attr="href")
        if not url:
            try:
                url=card.find_element(By.TAG_NAME,"a").get_attribute("href")
            except:
                url=""

        short_desc=find_first(["p.product-desc-rating"],in_el=card) or ""

        text_for_audience=f"{name} {short_desc}".lower()

        if any(k in text_for_audience for k in ["women","girl","ladies","female"]):
            audience="Female"
        elif any(k in text_for_audience for k in ["men","boy","male"]):
            audience="Male"
        elif any(k in text_for_audience for k in ["kid","child","children"]):
            audience="Children"
        else:
            audience="Unspecified"

        extra=deep_scrape_product(url) if DEEP_SCRAPE and url else{"Brand":"","Full Description":"","Seller":"","Availability":"","Rating":"","Reviews Count":0,"Breadcrumb":"","Image URLs (detail)":""}

        if not extra.get("Brand"):
            extra["Brand"]=name.split()[0] if name else ""

        row={"Scraped At":datetime.now().strftime("%d-%m-%Y %H:%M"),
            "Top Section":category_name,
            "Subcategory":subcat_name,
            "Product Name":name,
            "Brand (heuristic/listing)":extra.get("Brand",""),
            "Price":price,
            "Original Price":original_price,
            "Discount":discount,
            "Rating (listing)":rating_list,
            "Rating (detail)":extra.get("Rating",""),
            "Reviews Count (listing)":reviews_count,
            "Reviews Count (detail)":extra.get("Reviews Count",0),
            "Target Audience":audience,
            "Availability":extra.get("Availability",""),
            "Seller":extra.get("Seller",""),
            "Product URL":url,
            "Image URL (listing)":img,
            "Image URLs (detail)":extra.get("Image URLs (detail)",""),
            "Short Description":short_desc,
            "Full Description":extra.get("Full Description",""),
            "Breadcrumb":extra.get("Breadcrumb",""),
            "Page":page_num,
            }

        items.append(row)

    return items

all_rows=[]

for section_name,base_url in BASE_SECTIONS.items():
    print(f"\n{'='*80} - snapdeal_products_data.py:442")
    print(f"Section:{section_name} - snapdeal_products_data.py:443")
    print(f"{'='*80} - snapdeal_products_data.py:444")
    driver.get(base_url)
    
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR,"div.product-tuple-listing")))
    except:
        pass

    subcats=get_left_subcategory_links()
    seen_sc=set()
    cleaned_subcats=[]
    for sc in subcats:
        key=(sc["Subcategory"],sc["URL"])
        if key not in seen_sc:
            cleaned_subcats.append(sc)
            seen_sc.add(key)

    if not cleaned_subcats:
        cleaned_subcats=[{"Subcategory":"(ALL)","URL":base_url}]

    print(f"Found{len(cleaned_subcats)} subcategories - snapdeal_products_data.py:464")

    for sc in cleaned_subcats:
        sub_name=sc["Subcategory"]
        sub_url=sc["URL"]
        print(f"\n Subcategory:{sub_name} - snapdeal_products_data.py:469")
        for attempt in range(3):
            try:
                driver.get(sub_url)
                break
            except:
                time.sleep(5)

        total_this_sub=0
        for page in range(1,MAX_PAGES_PER_SUBCAT+1):
            print(f"Page {page} - snapdeal_products_data.py:479")
            scroll_to_bottom()
            items=scrape_listing_page(section_name,sub_name,page,max_take=MAX_PRODUCTS_PER_SUBCAT)
            if not items:
                print("No products found on this page - snapdeal_products_data.py:483")
                break

            all_rows.extend(items)
            total_this_sub += len(items)
            print(f"Scraped {len(items)} products | Subcategory total: {total_this_sub} | Overall total: {len(all_rows)} - snapdeal_products_data.py:488")

            moved=click_next_page()
            if not moved:
                print("No Next button or reached last page - snapdeal_products_data.py:492")
                break

        print(f"Collected {total_this_sub} products from '{sub_name}' - snapdeal_products_data.py:495")

columns=["Scraped At","Top Section","Subcategory","Product Name","Brand (heuristic/listing)","Price","Original Price","Discount",
        "Rating (listing)","Rating (detail)","Reviews Count (listing)","Reviews Count (detail)","Target Audience","Availability","Seller",
        "Product URL","Image URL (listing)","Image URLs (detail)","Short Description","Full Description","Breadcrumb","Page"]

df=pd.DataFrame(all_rows,columns=columns)
df.to_csv(OUTPUT_CSV,index=False,encoding="utf-8-sig")

print(f"\n{'='*80} - snapdeal_products_data.py:504")
print(f"Scraping Completed - snapdeal_products_data.py:505")
print(f"{'='*80} - snapdeal_products_data.py:506")
print(f"Total Products: {len(df):,} - snapdeal_products_data.py:507")
print(f"\nData Quality Summary - snapdeal_products_data.py:508")
print(f"Products with rating (listing): {df['Rating (listing)'].notna().sum():,} ({df['Rating (listing)'].notna().sum()/len(df)*100:.1f}%) - snapdeal_products_data.py:509")
print(f"Products with rating (detail): {df['Rating (detail)'].notna().sum():,} ({df['Rating (detail)'].notna().sum()/len(df)*100:.1f}%) - snapdeal_products_data.py:510")
print(f"Products with reviews count (listing): {(df['Reviews Count (listing)']>0).sum():,} ({(df['Reviews Count (listing)']>0).sum()/len(df)*100:.1f}%) - snapdeal_products_data.py:511")
print(f"Products with reviews count (detail): {(df['Reviews Count (detail)']>0).sum():,} ({(df['Reviews Count (detail)']>0).sum()/len(df)*100:.1f}%) - snapdeal_products_data.py:512")
print(f"{'='*80}\n - snapdeal_products_data.py:513")
driver.quit()
