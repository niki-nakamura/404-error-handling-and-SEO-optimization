ERROR_LIMIT = 10

def crawl(start_url):
    queue = deque([start_url])
    while queue:
        # 404エラー検出が10件に達した場合はクロールを停止
        if len(broken_links) >= ERROR_LIMIT:
            print(f"[DEBUG] Error limit of {ERROR_LIMIT} reached. Stopping crawl.")
            break

        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        print(f"[DEBUG] Crawling: {current}")

        if is_internal_link(current):
            try:
                resp = requests.get(current, headers=HEADERS, timeout=10)
                print(f"[DEBUG] Fetched {current} - Status: {resp.status_code}")
                if resp.status_code == 404:
                    print(f"[DEBUG] 404 detected at {current}")
                    broken_links.append((current, current, resp.status_code))
                    continue
                soup = BeautifulSoup(resp.text, 'html.parser')
                for a in soup.find_all('a', href=True):
                    link = urljoin(current, a['href'])
                    link = urlparse(link)._replace(fragment="").geturl()
                    print(f"[DEBUG] Found link: {link}")
                    # 外部リンクの場合、参照元を current としてチェック
                    if not is_internal_link(link):
                        check_status(link, current)
                    if link not in visited:
                        queue.append(link)
            except Exception as e:
                print(f"[DEBUG] Exception while processing {current}: {e}")
                broken_links.append((current, current, f"Error: {str(e)}"))
        else:
            check_status(current, None)

def check_status(url, source):
    # 404エラー検出が既に10件に達している場合は何もしない
    if len(broken_links) >= ERROR_LIMIT:
        return
    try:
        r = requests.head(url, headers=HEADERS, timeout=5)
        print(f"[DEBUG] Checking external URL: {url} - Status: {r.status_code}")
        if r.status_code == 404:
            ref = source if source else url
            print(f"[DEBUG] 404 detected at external URL: {url} (ref: {ref})")
            broken_links.append((ref, url, r.status_code))
    except Exception as e:
        ref = source if source else url
        print(f"[DEBUG] Exception while checking {url}: {e}")
        broken_links.append((ref, url, f"Error: {str(e)}"))
