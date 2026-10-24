
import csv
import time
from collections import deque
from urllib.parse import urljoin, urldefrag, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup


start_url = "https://www.musashino-u.ac.jp/"
domain = urlparse(start_url).netloc

MAX_PAGES = None

WAIT_SECONDS = 5

headers = {
    "User-Agent": "UniversitySitemapStudy/1.0"
}



robots_url = urljoin(start_url, "/robots.txt")

robot = RobotFileParser()

try:
    robots_res = requests.get(
        robots_url,
        headers=headers,
        timeout=15
    )

except requests.RequestException as e:
    raise SystemExit(f"通信エラー: {e}")

if robots_res.status_code == 200:
    robot.parse(robots_res.text.splitlines())

elif robots_res.status_code == 404:
    print("robots.txtが見つかりません（404）")
    robot.parse([])

else:
    raise SystemExit(
        f"robots.txt取得エラー: {robots_res.status_code}"
    )

crawl_delay = robot.crawl_delay(headers["User-Agent"])

if crawl_delay is not None:
    WAIT_SECONDS = max(WAIT_SECONDS, crawl_delay)

request_rate = robot.request_rate(headers["User-Agent"])

if request_rate is not None and request_rate.requests > 0:
    WAIT_SECONDS = max(
        WAIT_SECONDS,
        request_rate.seconds / request_rate.requests
    )


queue = deque([start_url])
queued = {start_url}
visited = set()

pages = {}


def normalize_url(href, base_url):
    url = urljoin(base_url, href)

    
    url, _ = urldefrag(url)

    parsed = urlparse(url)

    
    if parsed.scheme not in ("http", "https"):
        return None

    
    if parsed.netloc != domain:
        return None

    return url



def fetch_page(url):
    current = url

    for _ in range(6):

        if not robot.can_fetch(headers["User-Agent"], current):
            print(f"アクセス規則によりスキップ: {current}")
            return None, None

        time.sleep(WAIT_SECONDS)

        try:
            res = requests.get(
                current,
                headers=headers,
                timeout=15,
                allow_redirects=False
            )

        except requests.RequestException as e:
            print(f"通信エラー: {current}: {e}")
            return None, None

        if res.status_code in (403, 429, 503):
            raise RuntimeError(
                f"アクセスを停止しました: HTTP {res.status_code}"
            )

        if res.status_code in (301, 302, 303, 307, 308):
            location = res.headers.get("Location")

            if not location:
                return None, None

            next_url = normalize_url(location, current)

            if next_url is None:
                return None, None

            current = next_url
            continue

        if res.status_code != 200:
            print(f"スキップ {res.status_code}: {current}")
            return None, None

        content_type = res.headers.get("Content-Type", "")

        if "text/html" not in content_type.lower():
            return None, None

        return res, current

    print(f"リダイレクト回数超過: {url}")
    return None, None


while queue:

    if MAX_PAGES is not None and len(visited) >= MAX_PAGES:
        break

    url = queue.popleft()

    if url in visited:
        continue

    visited.add(url)

    try:
        res, final_url = fetch_page(url)
    except RuntimeError as e:
        print(e)
        break

    if res is None:
        continue

    visited.add(final_url)

    soup = BeautifulSoup(res.content, "html.parser")

    if soup.title is not None:
        title = soup.title.get_text(strip=True)
    else:
        title = ""

    pages[final_url] = title

    print(f"{len(pages)}件目: {final_url}")
    print(f"タイトル: {title}")

    for a in soup.find_all("a", href=True):

        link = normalize_url(a["href"], final_url)

        if link is None:
            continue

        if link not in visited and link not in queued:
            queue.append(link)
            queued.add(link)



with open(
    "sitemap.csv",
    "w",
    newline="",
    encoding="utf-8-sig"
) as f:

    writer = csv.writer(f)

    writer.writerow(["URL", "Title"])

    for url, title in pages.items():
        writer.writerow([url, title])


print("スクレイピング終了")
print(f"取得したページ数: {len(pages)}")
print("sitemap.csv に保存しました")