import requests
from bs4 import BeautifulSoup
import pandas as pd
import datetime
import time
import random
import os
import re

DATA_FILE = "data/records.csv"
RANK_URL  = "https://www.jjwxc.net/topten.php?orderstr=12&t=0"
HEADERS   = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer":         "https://www.jjwxc.net/",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def fetch_rank_list(session):
    print(f"正在请求榜单: {RANK_URL}")
    resp = session.get(RANK_URL, headers=HEADERS, timeout=20)
    resp.encoding = "gb18030"

    if resp.status_code != 200:
        raise Exception(f"请求失败，状态码: {resp.status_code}")

    soup  = BeautifulSoup(resp.text, "lxml")
    books = []
    rows  = soup.find_all("tr")

    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 3:
            continue

        rank_text = cells[0].get_text(strip=True)
        if not rank_text.isdigit():
            continue
        rank = int(rank_text)

        author    = cells[1].get_text(strip=True)
        book_cell = cells[2]
        link      = book_cell.find("a", href=re.compile(r"novelid=\d+"))
        if not link:
            continue

        book_name = link.get_text(strip=True)
        match     = re.search(r"novelid=(\d+)", link["href"])
        if not match or not book_name:
            continue

        books.append({
            "rank":      rank,
            "book_id":   match.group(1),
            "book_name": book_name,
            "author":    author,
        })

    print(f"榜单解析完成，共找到 {len(books)} 本书")
    return books


def fetch_book_collection(book_id, session):
    url  = f"https://www.jjwxc.net/onebook.php?novelid={book_id}"
    resp = session.get(url, headers=HEADERS, timeout=15)
    resp.encoding = "gb18030"

    if resp.status_code != 200:
        return None

    soup     = BeautifulSoup(resp.text, "lxml")
    text     = soup.get_text()
    patterns = [
        r"收藏[：:]\s*([\d,]+)",
        r"收藏本书[（(]([\d,]+)[）)]",
        r"被收藏\s*([\d,]+)\s*次",
        r"收藏数[：:]\s*([\d,]+)",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return int(m.group(1).replace(",", ""))

    for tag in soup.find_all(["span", "td", "div"]):
        tag_text = tag.get_text(strip=True)
        if "收藏" in tag_text and len(tag_text) < 30:
            nums = re.findall(r"\d+", tag_text)
            if nums:
                return int(nums[0])

    return None


def load_history():
    os.makedirs("data", exist_ok=True)
    if os.path.exists(DATA_FILE):
        df = pd.read_csv(DATA_FILE, dtype={"book_id": str})
        print(f"已加载历史数据，共 {len(df)} 条记录")
        return df
    print("未找到历史数据，将创建新文件")
    return pd.DataFrame(columns=[
        "date", "rank", "book_id", "book_name", "author",
        "collection_count", "daily_growth", "growth_rate_pct"
    ])


def save_history(df):
    os.makedirs("data", exist_ok=True)
    df.to_csv(DATA_FILE, index=False, encoding="utf-8-sig")
    print(f"已保存 {len(df)} 条记录到 {DATA_FILE}")


def calculate_growth(df_history, today_rows):
    today_str     = datetime.date.today().isoformat()
    yesterday_str = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()

    df_yesterday = df_history[df_history["date"] == yesterday_str][
        ["book_id", "collection_count"]
    ].rename(columns={"collection_count": "yesterday_count"})

    df_today         = pd.DataFrame(today_rows)
    df_today["date"] = today_str
    df_merged        = df_today.merge(df_yesterday, on="book_id", how="left")

    df_merged["daily_growth"] = (
        df_merged["collection_count"] - df_merged["yesterday_count"]
    ).fillna(0).astype(int)

    df_merged["growth_rate_pct"] = df_merged.apply(
        lambda r: round(r["daily_growth"] / r["yesterday_count"] * 100, 2)
        if pd.notna(r.get("yesterday_count")) and r["yesterday_count"] > 0
        else 0.0,
        axis=1
    )

    return df_merged.drop(columns=["yesterday_count"])


def print_report(df_today):
    today_str = datetime.date.today().isoformat()
    print(f"\n{'='*75}")
    print(f"  晋江完结全订榜  收藏涨幅日报  {today_str}")
    print(f"{'='*75}")
    print(f"{'排名':<5} {'书名':<20} {'作者':<10} {'书籍ID':<12} {'收藏数':<10} {'日涨幅':<8} {'涨幅%'}")
    print(f"{'-'*75}")

    for _, row in df_today.sort_values("daily_growth", ascending=False).iterrows():
        growth_str = f"+{row['daily_growth']}" if row['daily_growth'] >= 0 else str(row['daily_growth'])
        print(
            f"#{int(row['rank']):<4} "
            f"{str(row['book_name']):<20} "
            f"{str(row['author']):<10} "
            f"{str(row['book_id']):<12} "
            f"{int(row['collection_count']):<10} "
            f"{growth_str:<8} "
            f"{row['growth_rate_pct']}%"
        )
    print(f"{'='*75}\n")


def main():
    print(f"\n🚀 任务开始: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    session    = requests.Session()
    df_history = load_history()
    today_str  = datetime.date.today().isoformat()

    if not df_history.empty and (df_history["date"] == today_str).any():
        print("⚠️  今日数据已存在，直接展示")
        print_report(df_history[df_history["date"] == today_str])
        return

    try:
        books = fetch_rank_list(session)
    except Exception as e:
        print(f"❌ 获取榜单失败: {e}")
        return

    if not books:
        print("❌ 榜单解析为空")
        return

    print(f"\n榜单预览（前5名）:")
    for b in books[:5]:
        print(f"  #{b['rank']} {b['book_name']} / {b['author']} (ID: {b['book_id']})")

    today_rows = []
    print(f"\n开始获取各书收藏数...")
    for i, book in enumerate(books):
        print(f"[{i+1:>3}/{len(books)}] {book['book_name']} (ID: {book['book_id']}) ...", end=" ", flush=True)
        count = fetch_book_collection(book["book_id"], session)

        if count is not None:
            print(f"收藏: {count:,}")
            today_rows.append({
                "rank":             book["rank"],
                "book_id":          book["book_id"],
                "book_name":        book["book_name"],
                "author":           book["author"],
                "collection_count": count,
            })
        else:
            print("⚠️  获取失败，跳过")

        time.sleep(random.uniform(2, 5))

    if not today_rows:
        print("❌ 所有书籍收藏数获取失败")
        return

    df_today = calculate_growth(df_history, today_rows)
    df_all   = pd.concat([df_history, df_today], ignore_index=True)
    save_history(df_all)
    print_report(df_today)
    print(f"✅ 完成: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
