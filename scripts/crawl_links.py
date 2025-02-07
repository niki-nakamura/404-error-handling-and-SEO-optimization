#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import os
from collections import deque

START_URL = "https://good-apps.jp/"  # 開始URL
BASE_DOMAIN = "good-apps.jp"        # ドメインチェックに使用
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")

visited = set()
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

        if not is_internal_link(current):
            # 外部リンクの場合はステータスだけ確認
            check_status(current)
            continue

        # 内部リンク: HTML取得 -> リンク解析
        try:
            resp = requests.get(current, timeout=10)
            if resp.status_code >= 400:
                broken_links.append((current, resp.status_code))
                continue

            soup = BeautifulSoup(resp.text, 'html.parser')
            for a in soup.find_all('a', href=True):
                link = urljoin(current, a['href'])
                link = urlparse(link)._replace(fragment="").geturl()
                if link not in visited:
                    queue.append(link)
        except Exception as e:
            broken_links.append((current, f"Error: {str(e)}"))

def check_status(url):
    # 外部リンクの簡易チェック
    try:
        r = requests.head(url, timeout=5)
        if r.status_code >= 400:
            broken_links.append((url, r.status_code))
    except Exception as e:
        broken_links.append((url, f"Error: {str(e)}"))

def send_slack_notification(broken):
    if not SLACK_WEBHOOK_URL:
        print("SLACK_WEBHOOK_URL is not set.")
        return

    if not broken:
        msg = "[Link Checker]\nNo broken links found!"
    else:
        msg = "[Link Checker]\nBroken links found:\n"
        for url, status in broken:
            msg += f"- {url} [Status: {status}]\n"

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
