import requests
from bs4 import BeautifulSoup
import pandas as pd
import datetime, time, random, os, re

DATA_FILE   = "data/records.csv"
SCRAPER_KEY = "eeca1defaf74f4c7ce925161bae32f31"

BOOK_IDS = ["9652162","9456285","9852102","8943151","10269620"]

def scraper_get(url):
    api = f"http://api.scraperapi.com?api_key={SCRAPER_KEY}&url={url}&render=true&country_code=cn"
    return requests.get(api, timeout=120)

def fetch_book_info(book_id):
    url = f"https://www.jjwxc.net/onebook.php?novelid={book_id}"
    print(f"  请求: {url}")
    resp = scraper_get(url)
    print(f"  状态码: {resp.status_code}, 长度: {len(resp.text)}")
    if resp.status_code != 200:
        return None
    for enc in ["gb18030","gbk","utf-8"]:
        try:
            text = resp.content.decode(enc)
            break
        except:
            continue
    else:
        text = resp.text
    soup = BeautifulSoup(text, "lxml")
    title_tag = soup.find("span", itemprop="articleSection")
    if not title_tag:
        title_tag = soup.find("h1")
    book_name = title_tag.get_text(strip=True) if title_tag else f"ID{book_id}"
    author_tag = soup.find("span", itemprop="author")
    if not author_tag:
        author_tag = soup.find("a", href=re.compile(r"oneauthor"))
    author = author_tag.get_text(strip=True) if author_tag else "unknown"
    full_text = soup.get_text()
    collection = None
    for pat in [r"收藏[：:]\s*([\d,]+)", r"收藏数[：:]\s*([\d,]+)", r"被收藏\s*([\d,]+)"]:
        m = re.search(pat, full_text)
        if m:
            collection = int(m.group(1).replace(",",""))
            break
    print(f"  结果: {book_name} / {author} / 收藏: {collection}")
    print(f"  页面前200字: {full_text[:200]}")
    return {"book_id": book_id, "book_name": book_name, "author": author, "collection_count": collection}

def main():
    print(f"开始: {datetime.datetime.now()}")
    os.makedirs("data", exist_ok=True)
    today = datetime.date.today().isoformat()
    if os.path.exists(DATA_FILE):
        df_hist = pd.read_csv(DATA_FILE, dtype={"book_id": str})
    else:
        df_hist = pd.DataFrame()
    rows = []
    for i, bid in enumerate(BOOK_IDS):
        print(f"\n[{i+1}/{len(BOOK_IDS)}] ID: {bid}")
        info = fetch_book_info(bid)
        if info and info["collection_count"] is not None:
            growth = 0
            if not df_hist.empty:
                yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
                prev = df_hist[(df_hist["book_id"]==bid) & (df_hist["date"]==yesterday)]
                if not prev.empty:
                    growth = info["collection_count"] - int(prev.iloc[0]["collection_count"])
            rows.append({"date": today, "book_id": bid, "book_name": info["book_name"], "author": info["author"], "collection_count": info["collection_count"], "daily_growth": growth})
        time.sleep(random.uniform(2,5))
    if not rows:
        print("全部失败")
        return
    df_new = pd.DataFrame(rows)
    df_all = pd.concat([df_hist, df_new], ignore_index=True)
    df_all.to_csv(DATA_FILE, index=False, encoding="utf-8-sig")
    print(f"\n保存 {len(rows)} 条到 {DATA_FILE}")

if __name__ == "__main__":
    main()
