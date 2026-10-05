#!/usr/bin/env python3
"""
Download all attachments from a Confluence Data Center / Server space,
saving them into folders that mirror the page tree of the space.

    <out>/<SPACE>/<Root page>/<Child page>/<Grandchild page>/file.pdf

Uses only the public REST API (/rest/api/content), so Confluence enforces
permissions: the account sees only what it is allowed to view in the space.

Authentication (pick one):
  * Personal Access Token (recommended, Confluence DC 7.9+):
        export CONFLUENCE_TOKEN=...
  * Username + password:
        export CONFLUENCE_USER=jdoe CONFLUENCE_PASSWORD=...

Example:
    python3 confluence-space-attachments-download.py \
        --url https://confluence.example.com --space DOCS --out ./export

Requires: requests (pip install requests)
"""
import argparse
import csv
import os
import re
import sys
import time

import requests

PAGE_LIMIT = 100
INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED_NAMES = {'CON', 'PRN', 'AUX', 'NUL'} | {'COM%d' % i for i in range(1, 10)} | {'LPT%d' % i for i in range(1, 10)}


def safe_name(name, max_len=120):
    """Make a title usable as a file/folder name on Windows, macOS and Linux."""
    name = INVALID_CHARS.sub('_', name).strip().rstrip('.')
    if not name:
        name = '_'
    if name.split('.')[0].upper() in RESERVED_NAMES:
        name = '_' + name
    if len(name) > max_len:
        root, ext = os.path.splitext(name)
        name = root[:max_len - len(ext)] + ext
    return name


class Confluence:
    def __init__(self, url, token=None, user=None, password=None, verify=True, timeout=120):
        self.url = url.rstrip('/')
        self.session = requests.Session()
        self.session.verify = verify
        self.timeout = timeout
        self.session.headers['Accept'] = 'application/json'
        if token:
            self.session.headers['Authorization'] = 'Bearer ' + token
        elif user and password:
            self.session.auth = (user, password)
        else:
            raise SystemExit('Missing credentials: set CONFLUENCE_TOKEN or CONFLUENCE_USER + CONFLUENCE_PASSWORD')

    def get(self, path_or_url, params=None, stream=False, retries=4):
        url = path_or_url if path_or_url.startswith('http') else self.url + path_or_url
        for attempt in range(retries + 1):
            wait = 2 ** (attempt + 1)
            try:
                response = self.session.get(url, params=params, stream=stream, timeout=self.timeout)
            except requests.RequestException:
                if attempt == retries:
                    raise
            else:
                # 429 = rate limiting (DC 7.7+), 5xx = transient server errors
                if response.status_code != 429 and response.status_code < 500:
                    response.raise_for_status()
                    return response
                if attempt == retries:
                    response.raise_for_status()
                retry_after = response.headers.get('Retry-After', '')
                wait = int(retry_after) if retry_after.isdigit() else wait
            time.sleep(wait)

    def paged(self, path, params):
        """Iterate over all results of a paged /rest/api endpoint."""
        start = 0
        while True:
            data = self.get(path, params=dict(params, start=start, limit=PAGE_LIMIT)).json()
            results = data.get('results', [])
            for item in results:
                yield item
            # Confluence may cap 'limit' server-side, so rely on the 'next' link, not on the page size
            if not results or 'next' not in data.get('_links', {}):
                return
            start += len(results)

    def check_space(self, space_key):
        try:
            return self.get('/rest/api/space/' + space_key).json()
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code in (401, 403, 404):
                raise SystemExit('Space "%s" does not exist or you have no access to it (HTTP %s)'
                                 % (space_key, e.response.status_code))
            raise

    def space_content(self, space_key, content_type):
        return self.paged('/rest/api/content', {
            'spaceKey': space_key,
            'type': content_type,
            'status': 'current',
            'expand': 'ancestors',
        })

    def attachments(self, content_id):
        return self.paged('/rest/api/content/%s/child/attachment' % content_id, {'expand': 'version'})


def page_folder(page, folder_cache, base_dir):
    """Folder path built from the page's ancestors + its own title."""
    parts = [safe_name(a['title']) for a in page.get('ancestors', [])] + [safe_name(page['title'])]
    folder = os.path.join(base_dir, *parts)
    # Titles are unique per space, but sanitising may produce collisions (e.g. "a/b" and "a_b").
    owner = folder_cache.setdefault(folder, page['id'])
    if owner != page['id']:
        folder = '%s (%s)' % (folder, page['id'])
    return folder


def unique_path(path, used):
    if path not in used and not os.path.exists(path):
        used.add(path)
        return path
    root, ext = os.path.splitext(path)
    i = 1
    while '%s (%d)%s' % (root, i, ext) in used:
        i += 1
    path = '%s (%d)%s' % (root, i, ext)
    used.add(path)
    return path


def download(confluence, url, target):
    tmp = target + '.part'
    with confluence.get(url, stream=True) as response, open(tmp, 'wb') as f:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            f.write(chunk)
    os.replace(tmp, target)


def main():
    parser = argparse.ArgumentParser(description='Download all attachments of a Confluence space into a page-tree folder structure.')
    parser.add_argument('--url', required=True, help='Confluence base URL incl. context path, e.g. https://wiki.example.com/confluence')
    parser.add_argument('--space', required=True, help='Space key, e.g. DOCS')
    parser.add_argument('--out', default='.', help='Output directory (default: current directory)')
    parser.add_argument('--blogposts', action='store_true', help='Also download attachments of blog posts (into _Blog posts/)')
    parser.add_argument('--skip-existing', action='store_true', help='Skip files that already exist with the same size (resume an interrupted run)')
    parser.add_argument('--ca-bundle', help='Path to a CA bundle for an internal TLS certificate')
    parser.add_argument('--insecure', action='store_true', help='Disable TLS verification (not recommended)')
    args = parser.parse_args()

    verify = False if args.insecure else (args.ca_bundle or True)
    confluence = Confluence(
        args.url,
        token=os.environ.get('CONFLUENCE_TOKEN'),
        user=os.environ.get('CONFLUENCE_USER'),
        password=os.environ.get('CONFLUENCE_PASSWORD'),
        verify=verify,
    )

    space = confluence.check_space(args.space)
    base_dir = os.path.join(args.out, safe_name(space['key']))
    os.makedirs(base_dir, exist_ok=True)
    print('Space: %s (%s) -> %s' % (space['name'], space['key'], base_dir))

    sources = [('page', base_dir)]
    if args.blogposts:
        sources.append(('blogpost', os.path.join(base_dir, '_Blog posts')))

    folder_cache, used_paths = {}, set()
    stats = {'pages': 0, 'files': 0, 'skipped': 0, 'errors': 0, 'bytes': 0}
    manifest_path = os.path.join(base_dir, '_attachments_manifest.csv')

    with open(manifest_path, 'w', newline='', encoding='utf-8') as manifest_file:
        manifest = csv.writer(manifest_file)
        manifest.writerow(['page_id', 'page_title', 'attachment_id', 'file_name', 'version', 'size', 'local_path', 'status'])

        for content_type, root in sources:
            for page in confluence.space_content(args.space, content_type):
                stats['pages'] += 1
                folder = None
                for att in confluence.attachments(page['id']):
                    if folder is None:
                        folder = page_folder(page, folder_cache, root)
                        os.makedirs(folder, exist_ok=True)

                    size = att.get('extensions', {}).get('fileSize')
                    target = os.path.join(folder, safe_name(att['title'], max_len=200))
                    status = 'ok'
                    if args.skip_existing and os.path.exists(target) and size is not None and os.path.getsize(target) == size:
                        used_paths.add(target)
                        status = 'skipped'
                        stats['skipped'] += 1
                    else:
                        target = unique_path(target, used_paths)
                        link = att['_links']['download']
                        url = link if link.startswith('http') else att['_links'].get('base', confluence.url) + link
                        try:
                            download(confluence, url, target)
                            stats['files'] += 1
                            stats['bytes'] += os.path.getsize(target)
                        except Exception as e:  # keep going, report at the end
                            status = 'error: %s' % e
                            stats['errors'] += 1
                            print('  ! %s / %s: %s' % (page['title'], att['title'], e), file=sys.stderr)

                    manifest.writerow([page['id'], page['title'], att['id'], att['title'],
                                       att.get('version', {}).get('number'), size,
                                       os.path.relpath(target, base_dir), status])
                    print('  %s %s' % ('=' if status == 'skipped' else '+', os.path.relpath(target, base_dir)))

    print('\nPages scanned: %(pages)d, downloaded: %(files)d files (%(bytes)d bytes), '
          'skipped: %(skipped)d, errors: %(errors)d' % stats)
    print('Manifest: %s' % manifest_path)
    return 1 if stats['errors'] else 0


if __name__ == '__main__':
    sys.exit(main())
