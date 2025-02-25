#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import os
from collections import deque
import pandas as pd

# クロール対象のURLは以下の3つのみ（/以降のすべてのURLが対象）
ALLOWED_SOURCE_PREFIXES = [
    "https://good-apps.jp/media/column/",
    "https://good-apps.jp/media/category/",
    "https://good-apps.jp/media/app/"
]

BASE_DOMAIN = "good-apps.jp"  # 内部リンクの判定に使用

# 404エラー検知の上限（必要に応じて調整可能）
ERROR_LIMIT = 30

visited = set()
# broken_links のタプル形式は (発生元記事URL, 壊れているリンクURL, ステータス)
broken_links = []

# ブラウザ風の User-Agent を設定
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/115.0.0.0 Safari/537.36"
    )
}

# Slack Webhook 用の設定
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")

def is_internal_link(url):
    """
    URL が内部リンク (good-apps.jp) かどうかを判定
    """
    parsed = urlparse(url)
    return (parsed.netloc == "" or parsed.netloc.endswith(BASE_DOMAIN))

def is_excluded_domain(url):
    """
    Google系など、404チェック不要のドメインが含まれていれば True を返す
    """
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    exclude_keywords = [
        "google.com",
        "play.google.com",
        "google.co.jp",
        "gstatic.com",
        "apps.apple.com",
        "g.co",
        "youtu.be",
        "amazon.co.jp",
        "youtube.com",
    ]
    return any(k in domain for k in exclude_keywords)

def is_allowed_source(url):
    """
    発生元記事またはクロール対象として許可されているかを判定
    許可対象は ALLOWED_SOURCE_PREFIXES に含まれるURLのみ
    """
    return any(url.startswith(prefix) for prefix in ALLOWED_SOURCE_PREFIXES)

def record_broken_link(source, url, status):
    """
    許可対象の記事 (source) における壊れたリンク (url) を記録
    """
    if source and is_allowed_source(source):
        broken_links.append((source, url, status))

def crawl():
    # 初期キューは許可対象の3つのURL
    queue = deque(ALLOWED_SOURCE_PREFIXES)
    while queue:
        if len(broken_links) >= ERROR_LIMIT:
            print(f"[DEBUG] Reached error limit of {ERROR_LIMIT}. Stopping crawl.")
            return

        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        print(f"[DEBUG] Crawling: {current}")

        try:
            resp = requests.get(current, headers=HEADERS, timeout=10)
            print(f"[DEBUG] Fetched {current} - Status: {resp.status_code}")

            # ALLOWED_SOURCE_PREFIXES にないURLが404だったら broken_links に追加
            if resp.status_code == 404 and current not in ALLOWED_SOURCE_PREFIXES:
                if is_allowed_source(current):
                    broken_links.append((current, current, resp.status_code))
                if len(broken_links) >= ERROR_LIMIT:
                    return
                continue

            # HTML解析
            soup = BeautifulSoup(resp.text, 'html.parser')
            for a_tag in soup.find_all('a', href=True):
                if len(broken_links) >= ERROR_LIMIT:
                    return
                link = urljoin(current, a_tag['href'])
                link = urlparse(link)._replace(fragment="").geturl()
                print(f"[DEBUG] Found link: {link}")

                # 外部リンクの場合は HEAD でチェック
                if not is_internal_link(link):
                    if is_excluded_domain(link):
                        continue
                    check_status(link, current)
                    if len(broken_links) >= ERROR_LIMIT:
                        return
                else:
                    # 内部リンクで ALLOWED_SOURCE_PREFIXES に合致→再帰的にクロール
                    if is_allowed_source(link) and link not in visited:
                        queue.append(link)

        except Exception as e:
            print(f"[DEBUG] Exception while processing {current}: {e}")
            if is_allowed_source(current):
                broken_links.append((current, current, f"Error: {str(e)}"))
            if len(broken_links) >= ERROR_LIMIT:
                return

def check_status(url, source):
    """
    外部リンクなどにHEADを投げ、404なら記録。
    403/405の場合はGETして再度404チェック。
    """
    if is_excluded_domain(url):
        return
    try:
        r = requests.head(url, headers=HEADERS, timeout=5, allow_redirects=True)
        print(f"[DEBUG] Checking URL: {url} - HEAD status: {r.status_code}")
        if r.status_code == 404:
            record_broken_link(source, url, 404)
        elif r.status_code in (403, 405):
            # HEAD禁止の場合はGETで確認
            r = requests.get(url, headers=HEADERS, timeout=10)
            print(f"[DEBUG] GET fallback - {url} - Status: {r.status_code}")
            if r.status_code == 404:
                record_broken_link(source, url, 404)
    except Exception as e:
        print(f"[DEBUG] Exception in check_status for {url}: {e}")
        # エラー時には記録せずスキップ

def update_streamlit_data(broken):
    """
    404リンク一覧をCSVへ書き出し、Streamlit管理アプリで参照。
    """
    df = pd.DataFrame(broken, columns=["source", "url", "status"])
    df.to_csv("broken_links.csv", index=False)
    print("[DEBUG] 'broken_links.csv' written.")

def send_slack_notification(broken):
    """
    Slack通知。Webhook URL がセットされていれば 404件数を通知。
    """
    if not SLACK_WEBHOOK_URL:
        print("SLACK_WEBHOOK_URL is not set.")
        return

    count = len(broken)
    msg = (
        f"【404チェック結果】\n"
        f"404が {count} 件検出されました。\n"
        "詳細は Streamlit 側または 'broken_links.csv' でご確認ください。"
    )

    try:
        r = requests.post(SLACK_WEBHOOK_URL, json={"text": msg}, headers=HEADERS, timeout=10)
        if r.status_code not in [200, 204]:
            print(f"[DEBUG] Slack notification failed: {r.status_code}, {r.text}")
    except Exception as e:
        print(f"[DEBUG] Slack notification failed: {e}")

def main():
    print("Starting crawl from allowed URLs:")
    for url in ALLOWED_SOURCE_PREFIXES:
        print(f" - {url}")

    crawl()
    print("Crawl finished.")
    print(f"Detected {len(broken_links)} broken links.")

    update_streamlit_data(broken_links)
    send_slack_notification(broken_links)

if __name__ == "__main__":
    main()
