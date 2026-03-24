import requests
from bs4 import BeautifulSoup
import pandas as pd
import datetime, time, random, os, re

DATA_FILE  = "data/records.csv"
RANK_URL   = "https://www.jjwxc.net/topten.php?orderstr=12&t=0"
SCRAPER_KEY = "eeca1defaf74f4c7ce925161bae32f31"

def scraper_get(url):
    api = f"http://api.scraperapi.com?api_key={SCRAPER_KEY}&url={url}&render=true&country_code=cn"
    r = requests.get(api, timeout=120)
    return r

def fetch_rank_list():
    print(f"正在请求榜单: {RANK_URL}")
    resp = scraper_get(RANK_URL)
    print(f"状态码: {resp.status_code}, 长度: {len(resp.text)}")

    for enc in ["gb18030", "gbk", "utf-8"]:
        try:
            text = resp.content.decode(enc)
            print(f"编码: {enc}")
            break
        except:
            continue
    else:
        text = resp.text

    print(f"页面前300字: {text[:300]}")

    soup = BeautifulSoup(text, "lxml")
    rows = soup.find_all("tr")
    print(f"找到 {len(rows)} 个tr")

    books = []
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 3:
            continue
        rank_text = cells[0].get_text(strip=True)
        if not rank_text.isdigit():
            continue
        rank = int(rank_text)
        author = cells[1].get_text(strip=True)
        link = cells[2].find("a", href=re.compile(r"novelid=\d+"))
        if not link:
            link = cells[2].find("a")
        if not link:
            continue
        book_name = link.get_text(strip=True)
        m = re.search(r"novelid=(\d+)", link.get("href",""))
        if not m or not book_name:
            continue
        books.append({"rank": rank, "book_id": m.group(1), "book_name": book_name, "author": author})
        print(f"  ✅ #{rank} {book_name} / {author}")

    if not books:
        all_links = soup.find_all("a", href=re.compile(r"novelid=\d+"))
        print(f"备用: 找到 {len(all_links)} 个novelid链接")
        for a in all_links[:10]:
            print(f"  {a.get('href')} -> {a.get_text(strip=True)}")

    print(f"共找到 {len(books)} 本书")
    return books

def fetch_collection(book_id):
    url = f"https://www.jjwxc.net/onebook.php?novelid={book_id}"
    resp = scraper_get(url)
    if resp.status_code != 200:
        return None
    for enc in ["gb18030", "gbk", "utf-8"]:
        try:
            text = resp.content.decode(enc)
            break
        except:
            continue
    else:
        text = resp.text
    soup = BeautifulSoup(text, "lxml")
    full = soup.get_text()
    for pat in [r"收藏[：:]\s*([\d,]+)", r"收藏数[：:]\s*([\d,]+)", r"被收藏\s*([\d,]+)"]:
        m = re.search(pat, full)
        if m:
            return int(m.group(1).replace(",",""))
    return None

def main():
    print(f"\n🚀 开始: {datetime.datetime.now()}")
    os.makedirs("data", exist_ok=True)

    if os.path.exists(DATA_FILE):
        df_hist = pd.read_csv(DATA_FILE, dtype={"book_id": str})
    else:
        df_hist = pd.DataFrame()

    today = datetime.date.today().isoformat()

    books = fetch_rank_list()
    if not books:
        print("❌ 没有数据"); return

    rows = []
    for i, b in enumerate(books):
        print(f"[{i+1}/{len(books)}] {b['book_name']}...", end=" ", flush=True)
        c = fetch_collection(b["book_id"])
        if c:
            print(f"收藏:{c:,}")
            rows.append({**b, "date": today, "collection_count": c, "daily_growth": 0, "growth_rate_pct": 0.0})
        else:
            print("跳过")
        time.sleep(random.uniform(1,3))

    if not rows:
        print("❌ 全部失败"); return

    df_new = pd.DataFrame(rows)
    df_all = pd.concat([df_hist, df_new], ignore_index=True)
    df_all.to_csv(DATA_FILE, index=False, encoding="utf-8-sig")
    print(f"✅ 保存 {len(df_new)} 条到 {DATA_FILE}")

if __name__ == "__main__":
    main()
