#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import os
from collections import deque

START_URL = "https://good-apps.jp/"  # 開始URL
BASE_DOMAIN = "good-apps.jp"         # ドメインチェックに使用
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")

visited = set()
# broken_links のタプル形式は (参照元, 壊れているリンク, ステータス) とする
broken_links = []

def is_internal_link(url):
    parsed = urlparse(url)
    return (parsed.netloc == "" or parsed.netloc.endswith(BASE_DOMAIN))

def crawl(start_url):
    queue = deque([start_url])
    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)

        # 内部リンクの場合はHTMLを取得して解析
        if is_internal_link(current):
            try:
                resp = requests.get(current, timeout=10)
                if resp.status_code >= 400:
                    # ページ自体の取得が失敗している場合は、source も current として記録
                    broken_links.append((current, current, resp.status_code))
                    continue
                soup = BeautifulSoup(resp.text, 'html.parser')
                for a in soup.find_all('a', href=True):
                    link = urljoin(current, a['href'])
                    link = urlparse(link)._replace(fragment="").geturl()
                    # 外部リンクの場合は、そのリンクのステータスをチェック（参照元を current として渡す）
                    if not is_internal_link(link):
                        check_status(link, current)
                    if link not in visited:
                        queue.append(link)
            except Exception as e:
                broken_links.append((current, current, f"Error: {str(e)}"))
        else:
            # 内部経由でない外部URLの場合は、source は不明なので None もしくは URL 自体で記録
            check_status(current, None)

def check_status(url, source):
    # 外部リンクの簡易チェック
    try:
        r = requests.head(url, timeout=5)
        if r.status_code >= 400:
            ref = source if source else url
            broken_links.append((ref, url, r.status_code))
    except Exception as e:
        ref = source if source else url
        broken_links.append((ref, url, f"Error: {str(e)}"))

def send_slack_notification(broken):
    if not SLACK_WEBHOOK_URL:
        print("SLACK_WEBHOOK_URL is not set.")
        return

    if not broken:
        msg = "[Link Checker]\nNo broken links found!"
    else:
        msg = "[Link Checker]\nBroken links found:\n"
        for source, url, status in broken:
            msg += f"- {url} [Status: {status}] (発見元: {source})\n"

    try:
        requests.post(SLACK_WEBHOOK_URL, json={"text": msg}, timeout=10)
    except Exception as e:
        print(f"Slack notification failed: {e}")

def main():
    print(f"Starting crawl from {START_URL}")
    crawl(START_URL)
    print("Crawl finished.")
    print(f"Detected {len(broken_links)} broken links.")

    send_slack_notification(broken_links)

if __name__ == "__main__":
    main()
