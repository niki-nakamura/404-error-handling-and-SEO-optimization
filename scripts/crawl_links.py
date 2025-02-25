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

# テスト用: 404を5件見つけたら打ち切り
MAX_404 = 5

visited = set()
# broken_links のタプル形式は (発生元記事, 壊れているリンク, ステータス)
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
    Google系ドメインなど、404チェック不要のものはここで除外
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
    発生元記事が許可されている場合のみ broken_links に追加
    """
    if source and is_allowed_source(source):
        broken_links.append((source, url, status))

def crawl():
    # 初期キューは許可対象の3つのURL
    queue = deque(ALLOWED_SOURCE_PREFIXES)
    while queue:
        # 404検知数が5に達したら打ち切り
        if len(broken_links) >= MAX_404:
            print(f"[DEBUG] 404が {MAX_404}件に達したためクロールを終了します。")
            return

        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)

        print(f"[DEBUG] Crawling: {current}")
        try:
            resp = requests.get(current, headers=HEADERS, timeout=10)
            print(f"[DEBUG] Fetched {current} - Status: {resp.status_code}")

            # current が ALLOWED_SOURCE_PREFIXES に含まれていない場合のみ
            # 404を broken_links に登録
            if resp.status_code == 404 and current not in ALLOWED_SOURCE_PREFIXES:
                if is_allowed_source(current):
                    broken_links.append((current, current, resp.status_code))
                if len(broken_links) >= MAX_404:
                    return
                continue

            # HTMLの解析
            soup = BeautifulSoup(resp.text, 'html.parser')
            for a in soup.find_all('a', href=True):
                # 既に5件検出済みなら打ち切り
                if len(broken_links) >= MAX_404:
                    return

                link = urljoin(current, a['href'])
                link = urlparse(link)._replace(fragment="").geturl()
                print(f"[DEBUG] Found link: {link}")

                # 外部リンクかどうかで処理を分ける
                if not is_internal_link(link):
                    # 404チェック不要ドメインならスキップ
                    if is_excluded_domain(link):
                        continue
                    check_status(link, current)
                    if len(broken_links) >= MAX_404:
                        return
                else:
                    # 内部リンク: 対象プレフィックスなら追跡
                    if is_allowed_source(link) and link not in visited:
                        queue.append(link)

        except Exception as e:
            print(f"[DEBUG] Exception while processing {current}: {e}")
            if is_allowed_source(current):
                broken_links.append((current, current, f"Error: {str(e)}"))
            if len(broken_links) >= MAX_404:
                return

def check_status(url, source):
    """
    HEADリクエストで404チェック。403/405ならGETで再チェック
    """
    if is_excluded_domain(url):
        return
    try:
        r = requests.head(url, headers=HEADERS, timeout=5, allow_redirects=True)
        print(f"[DEBUG] Checking URL: {url} - Status: {r.status_code}")
        if r.status_code == 404:
            record_broken_link(source, url, 404)
        elif r.status_code in (403, 405):
            r = requests.get(url, headers=HEADERS, timeout=10)
            print(f"[DEBUG] GET fallback for URL: {url} - Status: {r.status_code}")
            if r.status_code == 404:
                record_broken_link(source, url, 404)
    except Exception as e:
        print(f"[DEBUG] Exception in check_status for URL: {url} - {e}")
        pass

def update_streamlit_data(broken):
    """
    Streamlit 用に CSV を出力し、管理アプリから読み込めるようにする
    """
    df = pd.DataFrame(broken, columns=["source", "url", "status"])
    df.to_csv("broken_links.csv", index=False)
    print("[DEBUG] 'broken_links.csv' written.")

def send_slack_notification(broken):
    """
    Slack通知。SLACK_WEBHOOK_URL が無い場合はスキップ。
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
            print(f"[DEBUG] Slack notification failed with status {r.status_code}: {r.text}")
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
