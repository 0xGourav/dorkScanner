#!/usr/bin/env python3
import argparse
import re
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from urllib.parse import parse_qs, unquote, urlparse

import requests
from bs4 import BeautifulSoup as bsoup


RED, YELLOW = '\033[91m', '\033[93m'

USER_AGENT = (
    'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:109.0) '
    'Gecko/20100101 Firefox/117.0'
)

DEFAULT_TIMEOUT = 10


def get_arguments():
    parser = argparse.ArgumentParser(
        description='Scrape search engines with dork queries to find exposed URLs.'
    )
    parser.add_argument('-q', '--query', dest='query', help="Specify the Search Query within ''")
    parser.add_argument('-p', '--pages', dest='pages', type=int, help='Specify the Number of Pages (Default: 1)')
    parser.add_argument('-P', '--processes', dest='processes', type=int,
                         help='Specify the Number of Worker Threads (Default: 2)')
    parser.add_argument('-t', '--timeout', dest='timeout', type=int,
                         help=f'Specify the Request Timeout in Seconds (Default: {DEFAULT_TIMEOUT})')
    parser.add_argument('-o', '--output', dest='output', help='Save the found URLs to a file')
    options = parser.parse_args()
    return options


def fetch(url, params, timeout):
    """Perform a GET request, returning the response or None on failure."""
    headers = {'User-Agent': USER_AGENT}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=timeout)
    except requests.exceptions.RequestException as exc:
        print(RED + f'[-] Request failed: {exc}')
        return None

    if resp.status_code != 200:
        print(RED + f'[-] Received HTTP {resp.status_code} for {resp.url} '
                     '(you may be rate-limited or blocked)')
        return None

    return resp


def google_search(query, page, timeout=DEFAULT_TIMEOUT):
    base_url = 'https://www.google.com/search'
    params = {'q': query, 'start': page * 10}
    resp = fetch(base_url, params, timeout)
    if resp is None:
        return []

    soup = bsoup(resp.text, 'html.parser')
    links = soup.find_all('div', {'class': 'yuRUbf'})
    result = []
    for link in links:
        anchor = link.find('a')
        href = anchor.get('href') if anchor else None
        if href:
            result.append(href)
    return result


def bing_search(query, page, timeout=DEFAULT_TIMEOUT):
    base_url = 'https://www.bing.com/search'
    params = {'q': query, 'first': page * 10 + 1}
    resp = fetch(base_url, params, timeout)
    if resp is None:
        return []

    soup = bsoup(resp.text, 'html.parser')
    links = soup.find_all('cite')
    result = [link.text for link in links if link.text]
    return result


def _unwrap_duckduckgo(href):
    """DuckDuckGo's HTML results link through /l/?uddg=<encoded target>."""
    parsed = urlparse(href)
    if parsed.path == '/l/':
        target = parse_qs(parsed.query).get('uddg')
        if target:
            return unquote(target[0])
    return href


def duckduckgo_search(query, page, timeout=DEFAULT_TIMEOUT):
    base_url = 'https://html.duckduckgo.com/html/'
    params = {'q': query, 's': page * 30}
    resp = fetch(base_url, params, timeout)
    if resp is None:
        return []

    soup = bsoup(resp.text, 'html.parser')
    links = soup.find_all('a', {'class': 'result__a'})
    result = [_unwrap_duckduckgo(link.get('href')) for link in links if link.get('href')]
    return result


def _unwrap_yahoo(href):
    """Yahoo's HTML results link through r.search.yahoo.com/.../RU=<encoded target>/..."""
    match = re.search(r'/RU=([^/]+)/', href)
    if match:
        return unquote(match.group(1))
    return href


def yahoo_search(query, page, timeout=DEFAULT_TIMEOUT):
    base_url = 'https://search.yahoo.com/search'
    params = {'p': query, 'b': page * 10 + 1}
    resp = fetch(base_url, params, timeout)
    if resp is None:
        return []

    soup = bsoup(resp.text, 'html.parser')
    links = soup.find_all('a', {'class': 'ac-algo'})
    result = [_unwrap_yahoo(link.get('href')) for link in links if link.get('href')]
    return result


# Every engine that a search will be run against. Results from all of them
# are combined into a single, deduplicated list.
ENGINES = {
    'google': google_search,
    'bing': bing_search,
    'duckduckgo': duckduckgo_search,
    'yahoo': yahoo_search,
}


def run_job(job):
    """Unwrap and execute one (engine, page) job."""
    return job()


def search_result(q, pages, processes, result, output=None):
    print('-' * 70)
    engines = ', '.join(ENGINES)
    print(f'Searching for: {q} in {pages} page(s) across [{engines}] with {processes} threads')
    print('-' * 70)
    print()

    urls = []
    for page_results in result:
        for url in page_results:
            urls.append(url)

    # Preserve order while removing duplicates (e.g. same result across pages).
    seen = set()
    unique_urls = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)

    if not unique_urls:
        print(YELLOW + '[!] No URLs found for this query.')
    for url in unique_urls:
        print('[+] ' + url)

    print()
    print('-' * 70)
    print(f'Number of urls: {len(unique_urls)}')
    print('-' * 70)

    if output:
        try:
            with open(output, 'w') as f:
                f.write('\n'.join(unique_urls) + ('\n' if unique_urls else ''))
            print(f'[+] Results saved to {output}')
        except OSError as exc:
            print(RED + f'[-] Could not write to {output}: {exc}')


def run(options):
    print()
    query = options.query or input('[?] Enter the Search Query: ').strip()
    if not query:
        print(RED + '[-] No query entered!...Exiting the Program....')
        return

    pages = options.pages or 1
    processes = options.processes or 2

    if pages < 1 or processes < 1:
        print(RED + '[-] Pages and Processes must be positive integers!...Exiting the Program....')
        return

    timeout = options.timeout or DEFAULT_TIMEOUT
    jobs = [
        partial(engine_fn, query, page, timeout=timeout)
        for engine_fn in ENGINES.values()
        for page in range(pages)
    ]

    with ThreadPoolExecutor(max_workers=processes) as pool:
        result = list(pool.map(run_job, jobs))

    search_result(query, pages, processes, result, output=options.output)


def main():
    options = get_arguments()

    try:
        run(options)
        # Keep prompting for another search until --query was supplied on
        # the command line, in which case a single run suffices.
        while not options.query:
            run(options)
    except KeyboardInterrupt:
        print('\nThanks For using!')


if __name__ == '__main__':
    main()
