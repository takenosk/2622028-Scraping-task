
import csv
import time
from collections import deque
from urllib.parse import urljoin, urldefrag, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup


# ==========================================
# 1. 基本設定
# ==========================================

start_url = "https://www.musashino-u.ac.jp/"
domain = urlparse(start_url).netloc

# テスト時は30件、全件探索するときはNone
MAX_PAGES = None

# 各リクエストの前に待機する秒数
WAIT_SECONDS = 2

headers = {
    "User-Agent": "UniversitySitemapStudy/1.0"
}


# ==========================================
# 2. robots.txt の確認
# ==========================================

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
    # robots.txtが取得できた場合
    robot.parse(robots_res.text.splitlines())

elif robots_res.status_code == 404:
    # robots.txtが存在しない場合
    print("robots.txtが見つかりません（404）")
    robot.parse([])

else:
    # その他のエラーでは停止
    raise SystemExit(
        f"robots.txt取得エラー: {robots_res.status_code}"
    )

# サイトのアクセス間隔を確認
crawl_delay = robot.crawl_delay(headers["User-Agent"])

if crawl_delay is not None:
    WAIT_SECONDS = max(WAIT_SECONDS, crawl_delay)

request_rate = robot.request_rate(headers["User-Agent"])

if request_rate is not None and request_rate.requests > 0:
    WAIT_SECONDS = max(
        WAIT_SECONDS,
        request_rate.seconds / request_rate.requests
    )

# ==========================================
# 3. URLの管理
# ==========================================

queue = deque([start_url])
queued = {start_url}
visited = set()

# URLとタイトルを保存する辞書
pages = {}


# ==========================================
# 4. URLを整理する関数
# ==========================================

def normalize_url(href, base_url):
    url = urljoin(base_url, href)

    # URLの#以降を除去
    url, _ = urldefrag(url)

    parsed = urlparse(url)

    # http/https以外は除外
    if parsed.scheme not in ("http", "https"):
        return None

    # 同じホスト以外は除外
    if parsed.netloc != domain:
        return None

    return url


# ==========================================
# 5. Webページを取得する関数
# ==========================================

def fetch_page(url):
    current = url

    # リダイレクトは最大5回まで
    for _ in range(6):

        # robots.txtを確認
        if not robot.can_fetch(headers["User-Agent"], current):
            print(f"アクセス規則によりスキップ: {current}")
            return None, None

        # 負荷を軽減するため待機
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

        # アクセス制限・サーバー過負荷時は探索を停止
        if res.status_code in (403, 429, 503):
            raise RuntimeError(
                f"アクセスを停止しました: HTTP {res.status_code}"
            )

        # リダイレクト処理
        if res.status_code in (301, 302, 303, 307, 308):
            location = res.headers.get("Location")

            if not location:
                return None, None

            next_url = normalize_url(location, current)

            if next_url is None:
                return None, None

            current = next_url
            continue

        # 正常に取得できなかった場合
        if res.status_code != 200:
            print(f"スキップ {res.status_code}: {current}")
            return None, None

        # HTML以外のファイルを除外
        content_type = res.headers.get("Content-Type", "")

        if "text/html" not in content_type.lower():
            return None, None

        return res, current

    print(f"リダイレクト回数超過: {url}")
    return None, None


# ==========================================
# 6. リンクを順番にたどる
# ==========================================

while queue:

    # テスト時の件数制限
    if MAX_PAGES is not None and len(visited) >= MAX_PAGES:
        break

    url = queue.popleft()

    # すでに確認済みならスキップ
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

    # HTMLを解析
    soup = BeautifulSoup(res.content, "html.parser")

    # ページタイトルを取得
    if soup.title is not None:
        title = soup.title.get_text(strip=True)
    else:
        title = ""

    # 辞書型に保存
    pages[final_url] = title

    print(f"{len(pages)}件目: {final_url}")
    print(f"タイトル: {title}")

    # aタグからリンクを取得
    for a in soup.find_all("a", href=True):

        link = normalize_url(a["href"], final_url)

        if link is None:
            continue

        # 未訪問のURLを追加
        if link not in visited and link not in queued:
            queue.append(link)
            queued.add(link)


# ==========================================
# 7. CSVファイルに保存
# ==========================================

with open(
    "sitemap.csv",
    "w",
    newline="",
    encoding="utf-8-sig"
) as f:

    writer = csv.writer(f)

    # 1行目に見出しを書き込む
    writer.writerow(["URL", "Title"])

    # 辞書の内容を書き込む
    for url, title in pages.items():
        writer.writerow([url, title])


print("スクレイピング終了")
print(f"取得したページ数: {len(pages)}")
print("sitemap.csv に保存しました")