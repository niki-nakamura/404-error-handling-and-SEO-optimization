#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import os
from collections import deque
import pandas as pd

# クロール対象URLリスト
ALLOWED_SOURCE_PREFIXES = [
    "https://good-apps.jp/media/column/",
    "https://good-apps.jp/media/category/",
    "https://good-apps.jp/media/app/"
]

BASE_DOMAIN = "good-apps.jp"  # 内部ドメイン判定用

# 404エラー検知の上限
ERROR_LIMIT = 30

visited = set()
# broken_links: [(発生元記事URL, 壊れたリンクURL, ステータス), ...]
broken_links = []

# ブラウザ的な User-Agent
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/115.0.0.0 Safari/537.36"
    )
}

# Slack 用 webhook
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")

def is_internal_link(url):
    """
    good-apps.jp への内部リンクかどうか判定
    """
    parsed = urlparse(url)
    return (parsed.netloc == "" or parsed.netloc.endswith(BASE_DOMAIN))

def is_excluded_domain(url):
    """
    404チェック対象外ドメイン
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
    発生元URLが指定のプレフィックス一覧に合致するか
    """
    return any(url.startswith(prefix) for prefix in ALLOWED_SOURCE_PREFIXES)

def record_broken_link(source, url, status):
    """
    404 URL を broken_links リストに追加
    """
    if source and is_allowed_source(source):
        broken_links.append((source, url, status))

def crawl():
    """
    クロールメイン処理。ALLOWED_SOURCE_PREFIXES を起点にリンクを辿る
    """
    queue = deque(ALLOWED_SOURCE_PREFIXES)
    while queue:
        if len(broken_links) >= ERROR_LIMIT:
            print(f"[DEBUG] Reached error limit ({ERROR_LIMIT}). Stopping crawl.")
            return

        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)

        print(f"[DEBUG] Crawling: {current}")
        try:
            resp = requests.get(current, headers=HEADERS, timeout=10)
            print(f"[DEBUG] Fetched {current} - Status: {resp.status_code}")

            # もし current が ALLOWED_SOURCE_PREFIXES に含まれていなければ
            # 404の場合にはリストに追加
            if resp.status_code == 404 and current not in ALLOWED_SOURCE_PREFIXES:
                if is_allowed_source(current):
                    broken_links.append((current, current, resp.status_code))
                if len(broken_links) >= ERROR_LIMIT:
                    return
                continue

            # HTMLパース
            soup = BeautifulSoup(resp.text, 'html.parser')
            for a_tag in soup.find_all('a', href=True):
                if len(broken_links) >= ERROR_LIMIT:
                    return
                link = urljoin(current, a_tag['href'])
                # 同じリンクでも fragment (#...) は削除して正規化
                link = urlparse(link)._replace(fragment="").geturl()

                print(f"[DEBUG] Found link: {link}")

                # 外部リンクチェック
                if not is_internal_link(link):
                    if is_excluded_domain(link):
                        continue
                    check_status(link, current)
                    if len(broken_links) >= ERROR_LIMIT:
                        return
                else:
                    # 内部リンクの場合で、
                    # 再帰的にクロール可能かつ未訪問であればキューに追加
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
    HEADリクエストでステータス判定し、404なら broken_links に追加
    """
    if is_excluded_domain(url):
        return
    try:
        r = requests.head(url, headers=HEADERS, timeout=5, allow_redirects=True)
        print(f"[DEBUG] Checking {url} - HEAD status: {r.status_code}")
        if r.status_code == 404:
            record_broken_link(source, url, 404)
        elif r.status_code in (403, 405):
            # HEAD禁止サイトなどは GET で再チェック
            r = requests.get(url, headers=HEADERS, timeout=10)
            print(f"[DEBUG] GET fallback for {url} - Status: {r.status_code}")
            if r.status_code == 404:
                record_broken_link(source, url, 404)
    except Exception as e:
        print(f"[DEBUG] Exception in check_status for {url}: {e}")
        # エラー時は追加登録しない

def update_streamlit_data(broken):
    """
    broken_links.csv に書き出し
    """
    df = pd.DataFrame(broken, columns=["source", "url", "status"])
    df.to_csv("broken_links.csv", index=False)
    print("[DEBUG] Saved 'broken_links.csv'.")

def send_slack_notification(broken):
    """
    Slack 通知（Webhook URL が設定されている場合のみ）
    """
    if not SLACK_WEBHOOK_URL:
        print("SLACK_WEBHOOK_URL is not set.")
        return

    count = len(broken)
    msg = (
        f"【404チェック結果】\n"
        f"404 が {count} 件検出されました。\n"
        "詳細は Streamlit 側または 'broken_links.csv' でご確認ください。"
    )

    try:
        r = requests.post(SLACK_WEBHOOK_URL, json={"text": msg}, headers=HEADERS, timeout=10)
        if r.status_code not in [200, 204]:
            print(f"[DEBUG] Slack notification failed: {r.status_code} - {r.text}")
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
