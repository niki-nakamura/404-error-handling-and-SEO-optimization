#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import os
from collections import deque
import pandas as pd
from datetime import datetime

ALLOWED_SOURCE_PREFIXES = [
    "https://good-apps.jp/media/column/",
    "https://good-apps.jp/media/category/",
    "https://good-apps.jp/media/app/"
]

BASE_DOMAIN = "good-apps.jp"
ERROR_LIMIT = 30

visited = set()
broken_links = []  # (source, url, status)を格納

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/115.0.0.0 Safari/537.36"
    )
}

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")


def is_internal_link(url):
    parsed = urlparse(url)
    return (parsed.netloc == "" or parsed.netloc.endswith(BASE_DOMAIN))


def is_excluded_domain(url):
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
    return any(url.startswith(prefix) for prefix in ALLOWED_SOURCE_PREFIXES)


def record_broken_link(source, url, status):
    if source and is_allowed_source(source):
        broken_links.append((source, url, status))


def crawl():
    queue = deque(ALLOWED_SOURCE_PREFIXES)
    while queue:
        if len(broken_links) >= ERROR_LIMIT:
            print(f"[DEBUG] Reached {ERROR_LIMIT} broken links. Stopping.")
            return

        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        print(f"[DEBUG] Crawling: {current}")

        try:
            resp = requests.get(current, headers=HEADERS, timeout=10)
            if resp.status_code == 404 and current not in ALLOWED_SOURCE_PREFIXES:
                if is_allowed_source(current):
                    broken_links.append((current, current, 404))
                if len(broken_links) >= ERROR_LIMIT:
                    return
                continue

            soup = BeautifulSoup(resp.text, 'html.parser')
            for a_tag in soup.find_all('a', href=True):
                if len(broken_links) >= ERROR_LIMIT:
                    return
                link = urljoin(current, a_tag['href'])
                link = urlparse(link)._replace(fragment="").geturl()

                if not is_internal_link(link):
                    if is_excluded_domain(link):
                        continue
                    check_status(link, current)
                else:
                    if is_allowed_source(link) and link not in visited:
                        queue.append(link)

        except Exception as e:
            if is_allowed_source(current):
                broken_links.append((current, current, f"Error: {str(e)}"))
            if len(broken_links) >= ERROR_LIMIT:
                return


def check_status(url, source):
    if is_excluded_domain(url):
        return
    try:
        r = requests.head(url, headers=HEADERS, timeout=5, allow_redirects=True)
        if r.status_code == 404:
            record_broken_link(source, url, 404)
        elif r.status_code in (403, 405):
            r2 = requests.get(url, headers=HEADERS, timeout=10)
            if r2.status_code == 404:
                record_broken_link(source, url, 404)
    except Exception as e:
        # エラー時にはスキップ
        pass


def update_csv(broken):
    """
    404リンク一覧をCSVへ書き出す。
    - 既存CSVがあれば、'resolved' や 'detected_date' を引き継ぎ
    - 新規リンクは 'detected_date' に現在日時を設定、resolved=False で追加
    - 今回未検出のリンクは削除 (常に最新の404だけを保持)
    """
    new_dict = {}
    for s, u, st_code in broken:
        new_dict[(s, u)] = st_code

    old_df = pd.DataFrame(columns=["source", "url", "status", "detected_date", "resolved"])

    if os.path.exists("broken_links.csv"):
        old_df = pd.read_csv("broken_links.csv")
        if 'detected_date' not in old_df.columns:
            old_df['detected_date'] = ""
        if 'resolved' not in old_df.columns:
            old_df['resolved'] = False

    old_map = {}
    for _, row in old_df.iterrows():
        key = (row["source"], row["url"])
        old_map[key] = {
            "status": row["status"],
            "detected_date": row.get("detected_date", ""),
            "resolved": row.get("resolved", False)
        }

    updated_rows = []

    # 今回検出された404だけを保持
    for (src, link), st_code in new_dict.items():
        if (src, link) in old_map:
            # 既存分を継承
            rowdata = old_map[(src, link)]
            row = {
                "source": src,
                "url": link,
                "status": st_code,
                "detected_date": rowdata["detected_date"],
                "resolved": rowdata["resolved"]
            }
        else:
            # 新規
            row = {
                "source": src,
                "url": link,
                "status": st_code,
                "detected_date": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "resolved": False
            }
        updated_rows.append(row)

    new_df = pd.DataFrame(updated_rows)

    # 万が一 detected_date が空なら現在日時を入れる
    mask = (new_df["detected_date"].isnull()) | (new_df["detected_date"] == "")
    new_df.loc[mask, "detected_date"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    new_df.to_csv("broken_links.csv", index=False)
    print("[DEBUG] 'broken_links.csv' updated with crawler results.")


def send_slack_notification(broken):
    if not SLACK_WEBHOOK_URL:
        return
    count = len(broken)
    msg = f"【404チェック】\n404が {count} 件検出されました。詳細は 'broken_links.csv' にて。"
    try:
        r = requests.post(SLACK_WEBHOOK_URL, json={"text": msg}, headers=HEADERS, timeout=10)
        if r.status_code not in [200, 204]:
            print("[DEBUG] Slack notification failed:", r.status_code, r.text)
    except Exception as e:
        print("[DEBUG] Slack notification exception:", e)


def main():
    crawl()
    update_csv(broken_links)
    send_slack_notification(broken_links)


if __name__ == "__main__":
    main()
