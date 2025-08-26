#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from src.utils import setup_logging, load_config
from src.crawler import BooksCrawler
import os
import sys
import logging
import platform
from pathlib import Path
from multiprocessing import Process
from src.utils import setup_logging, load_config
from src.crawler import BooksCrawler

def run_crawler(config, book_url, total_pages, delay):
    crawler = BooksCrawler(config)
    # 子進程不做人工 CAPTCHA 驗證
    crawler.login(auto_captcha=True)
    crawler.navigate_to_book(book_url)
    crawler.auto_capture_mode(total_pages, delay)

def print_banner():
    print("\n" + "="*70)
    print("📚 博客來電子書截圖工具 v2.0")
    print("="*70)
    print(f"📌 系統: {platform.system()}")
    print(f"📌 Python: {sys.version.split()[0]}")
    print("="*70 + "\n")
    # ...existing code...

def main():
    setup_logging()
    config = load_config()
    print_banner()
    # 先登入
    crawler = BooksCrawler(config)
    crawler.login(auto_captcha=False)

    # 讓使用者輸入多本電子書網址
    urls_input = input("請輸入所有電子書網址（以逗號分隔）: ").strip()
    book_urls = [u.strip() for u in urls_input.split(",") if u.strip()]
    if not book_urls:
        print("未輸入任何網址，程式結束。")
        return
    total_pages = config.get("total_pages", 100)
    delay = config.get("delay", 1)
    processes = []
    # 主進程執行第一本書
    crawler.navigate_to_book(book_urls[0])
    crawler.auto_capture_mode(total_pages, delay)
    # 其餘書籍平行處理
    for url in book_urls[1:]:
        p = Process(target=run_crawler, args=(config, url, total_pages, delay))
        p.start()
        processes.append(p)
    for p in processes:
        p.join()

if __name__ == "__main__":
    main()
