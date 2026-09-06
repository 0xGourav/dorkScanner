#!/usr/bin/env python3
import argparse
from functools import partial
from multiprocessing import Pool

import requests
from bs4 import BeautifulSoup as bsoup


GREEN, RED, YELLOW = '\033[1;32m', '\033[91m', '\033[93m'

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
    parser.add_argument('-e', '--engine', dest='engine', help='Specify the Search Engine (Google/Bing)')
    parser.add_argument('-p', '--pages', dest='pages', type=int, help='Specify the Number of Pages (Default: 1)')
    parser.add_argument('-P', '--processes', dest='processes', type=int,
                         help='Specify the Number of Processes (Default: 2)')
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
    links = soup.findAll('div', {'class': 'yuRUbf'})
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
    links = soup.findAll('cite')
    result = [link.text for link in links if link.text]
    return result


def search_result(q, engine, pages, processes, result, output=None):
    print('-' * 70)
    print(f'Searching for: {q} in {pages} page(s) of {engine} with {processes} processes')
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


banner = '''

    ██████╗░░█████╗░██████╗░██╗░░██╗  ░██████╗░█████╗░░█████╗░███╗░░██╗███╗░░██╗███████╗██████╗░
    ██╔══██╗██╔══██╗██╔══██╗██║░██╔╝  ██╔════╝██╔══██╗██╔══██╗████╗░██║████╗░██║██╔════╝██╔══██╗
    ██║░░██║██║░░██║██████╔╝█████═╝░  ╚█████╗░██║░░╚═╝███████║██╔██╗██║██╔██╗██║█████╗░░██████╔╝
    ██║░░██║██║░░██║██╔══██╗██╔═██╗░  ░╚═══██╗██║░░██╗██╔══██║██║╚████║██║╚████║██╔══╝░░██╔══██╗
    ██████╔╝╚█████╔╝██║░░██║██║░╚██╗  ██████╔╝╚█████╔╝██║░░██║██║░╚███║██║░╚███║███████╗██║░░██║
    ╚═════╝░░╚════╝░╚═╝░░╚═╝╚═╝░░╚═╝  ╚═════╝░░╚════╝░╚═╝░░╚═╝╚═╝░░╚══╝╚═╝░░╚══╝╚══════╝╚═╝░░╚═╝

    Made By: Madhav Mehndiratta (github.com/madhavmehndiratta)

'''


def run(options):
    print()
    query = options.query or input('[?] Enter the Search Query: ').strip()
    if not query:
        print(RED + '[-] No query entered!...Exiting the Program....')
        return

    engine = (options.engine or input('[?] Choose the Search Engine (Google/Bing): ')).strip().lower()

    if engine == 'google':
        target = partial(google_search, query, timeout=options.timeout or DEFAULT_TIMEOUT)
    elif engine == 'bing':
        target = partial(bing_search, query, timeout=options.timeout or DEFAULT_TIMEOUT)
    else:
        print(RED + '[-] Invalid Option Entered!...Exiting the Program....')
        return

    pages = options.pages or 1
    processes = options.processes or 2

    if pages < 1 or processes < 1:
        print(RED + '[-] Pages and Processes must be positive integers!...Exiting the Program....')
        return

    with Pool(processes) as p:
        result = p.map(target, range(pages))

    search_result(query, engine, pages, processes, result, output=options.output)


def main():
    options = get_arguments()
    print(GREEN + banner)

    try:
        run(options)
        # Keep prompting for another search until both --query and --engine
        # were supplied on the command line, in which case a single run suffices.
        while not (options.query and options.engine):
            run(options)
    except KeyboardInterrupt:
        print('\nThanks For using!')


if __name__ == '__main__':
    main()
