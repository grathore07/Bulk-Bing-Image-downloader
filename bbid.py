#!/usr/bin/env python3

import argparse
import hashlib
import imghdr
import os
import pickle
import posixpath
import re
import signal
import socket
import threading
import time
import urllib.parse
import urllib.request
import random


# Default directory to save dowloaded images.
OUTPUT_DIR = './bing'
# Adult filter is on by default.
ADULT_FILTER = True
ADLT = 'on' if ADULT_FILTER else 'off'


socket.setdefaulttimeout(2)



IN_PROGRESS = TRIED_URLs = []
IMAGE_MD5s = {}
URLOPENHEADER = {'User-Agent': 'Mozilla/5.0 (X11; Fedora; Linux x86_64; rv:60.0) Gecko/20100101 Firefox/60.0'}

class Error(Exception):
    pass

class DuplicateError(Error):
    pass

class InvalidError(Error):
    pass


def download(pool_sema: threading.Semaphore, url: str, output_dir: str):
    if url in TRIED_URLs:
        return
    pool_sema.acquire()
    path = urllib.parse.urlsplit(url).path
    filename = posixpath.basename(path).split('?')[0]  # Strip GET parameters from filename
    name, ext = os.path.splitext(filename)
    name = name[:36]
    filename = name + ext

    i = 0
    while os.path.exists(os.path.join(output_dir, filename)) or filename in IN_PROGRESS:
        i += 1
        filename = "%s-%d%s" % (name, i, ext)
    IN_PROGRESS.append(filename)
    image_file_path = ''
    try:
        request = urllib.request.Request(url, None, URLOPENHEADER)
        image = urllib.request.urlopen(request).read()
        if not imghdr.what(None, image):
            print('FAIL: Invalid image, not saving ' + filename)
            return -1, 0

        md5_key = hashlib.md5(image).hexdigest()
        if md5_key in IMAGE_MD5s:
            print('FAIL: Image is a duplicate of ' + IMAGE_MD5s[md5_key] + ', not saving ' + filename)
            return -1, ''

        IMAGE_MD5s[md5_key] = filename

        image_file_path = os.path.join(output_dir, filename)
        imagefile = open(image_file_path, 'wb')
        imagefile.write(image)
        imagefile.close()
        print("OK: " + filename)
        TRIED_URLs.append(url)
    except Exception as e:
        print("FAIL: " + filename)
    finally:
        IN_PROGRESS.remove(filename)
        pool_sema.release()
    return 0, image_file_path


def fetch_images_from_keyword(pool_sema: threading.Semaphore, keyword: str, output_dir: str, filters: str, limit: int):
    current = 0
    last = ''
    while True:
        request_url = 'https://www.bing.com/images/async?q=' + urllib.parse.quote_plus(keyword) + '&first=' + str(
            current) + '&count=35&adlt=' + ADLT + '&qft=' + ('' if filters is None else filters)
        request = urllib.request.Request(request_url, None, headers=URLOPENHEADER)
        response = urllib.request.urlopen(request)
        html = response.read().decode('utf8')
        links = re.findall('murl&quot;:&quot;(.*?)&quot;', html)
        try:
            if links[-1] == last:
                return
            for index, link in enumerate(links):
                if limit is not None and current + index >= limit:
                    return
                t = threading.Thread(target=download, args=(pool_sema, link, output_dir))
                t.start()
                current += 1
            last = links[-1]
        except IndexError:
            print('No search results for "{0}"'.format(keyword))
            return
        time.sleep(0.1)


def fetch_random_image_from_keyword(keyword, output_dir=OUTPUT_DIR, filters=''):
    pool_sema = threading.BoundedSemaphore(1)
    current = 0
    request_url = 'https://www.bing.com/images/async?q=' + urllib.parse.quote_plus(keyword) + '&first=' + str(
        current) + '&count=35&adlt=' + ADLT + '&qft=' + ('' if filters is None else filters)
    request = urllib.request.Request(request_url, None, headers=URLOPENHEADER)
    response = urllib.request.urlopen(request)
    html = response.read().decode('utf8')
    links = re.findall('murl&quot;:&quot;(.*?)&quot;', html)
    # Randomize the links
    random.shuffle(links)

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    for link in links:
        error, path = download(pool_sema, link, output_dir)
        if error == 0:
            return path


def backup_history(*args):
    download_history = open(os.path.join(OUTPUT_DIR, 'download_history.pickle'), 'wb')
    pickle.dump(TRIED_URLs, download_history)
    copied_image_md5s = dict(
        IMAGE_MD5s)  # We are working with the copy, because length of input variable for pickle must not be changed during dumping
    pickle.dump(copied_image_md5s, download_history)
    download_history.close()
    print('history_dumped')
    if args:
        exit(0)


# print(fetch_random_image_from_keyword('black cat', output_dir='../item_catalog/bing/'))
# print(fetch_random_image_from_keyword('macbook', output_dir='../item_catalog/bing/'))
# print(fetch_random_image_from_keyword('blue jay', output_dir='../item_catalog/bing/'))
# print(fetch_random_image_from_keyword('skateboard', output_dir='../item_catalog/bing/'))
# print(fetch_random_image_from_keyword('The Godfather', output_dir='../item_catalog/bing/'))

#
# if __name__ == "__main__":
#     parser = argparse.ArgumentParser(description='Bing image bulk downloader')
#     parser.add_argument('-s', '--search-string', help='Keyword to search', required=False)
#     parser.add_argument('-f', '--search-file', help='Path to a file containing search strings line by line',
#                         required=False)
#     parser.add_argument('-o', '--output', help='Output directory', required=False)
#     parser.add_argument('--adult-filter-on', help='Enable adult filter', action='store_true', required=False)
#     parser.add_argument('--adult-filter-off', help='Disable adult filter', action='store_true', required=False)
#     parser.add_argument('--filters',
#                         help='Any query based filters you want to append when searching for images, e.g. +filterui:license-L1',
#                         required=False)
#     parser.add_argument('--limit', help='Make sure not to search for more than specified amount of images.',
#                         required=False, type=int)
#     parser.add_argument('--threads', help='Number of threads', type=int, default=20)
#     args = parser.parse_args()
#     if (not args.search_string) and (not args.search_file):
#         parser.error('Provide Either search string or path to file containing search strings')
#     if args.output:
#         OUTPUT_DIR = args.output
#     if not os.path.exists(OUTPUT_DIR):
#         os.makedirs(OUTPUT_DIR)
#     output_dir_origin = OUTPUT_DIR
#     signal.signal(signal.SIGINT, backup_history)
#     try:
#         download_history = open(os.path.join(OUTPUT_DIR, 'download_history.pickle'), 'rb')
#         TRIED_URLs = pickle.load(download_history)
#         IMAGE_MD5s = pickle.load(download_history)
#         download_history.close()
#     except (OSError, IOError):
#         TRIED_URLs = []
#     if ADULT_FILTER:
#         ADLT = ''
#     else:
#         ADLT = 'off'
#     if args.adult_filter_off:
#         ADLT = 'off'
#     elif args.adult_filter_on:
#         ADLT = ''
#     pool_sema = threading.BoundedSemaphore(args.threads)
#     if args.search_string:
#         fetch_images_from_keyword(pool_sema, args.search_string, OUTPUT_DIR, args.filters, args.limit)
#     elif args.search_file:
#         try:
#             input_file = open(args.search_file)
#         except (OSError, IOError):
#             print("Couldn't open file {}".format(args.search_file))
#             exit(1)
#         finally:
#             for keyword in input_file.readlines():
#                 output_sub_dir = os.path.join(output_dir_origin, keyword.strip().replace(' ', '_'))
#                 if not os.path.exists(output_sub_dir):
#                     os.makedirs(output_sub_dir)
#                 fetch_images_from_keyword(pool_sema, keyword, output_sub_dir, args.filters, args.limit)
#                 backup_history()
#             input_file.close()
