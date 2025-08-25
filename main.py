#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from src.utils import setup_logging, load_config
from src.crawler import BooksCrawler
import os
import sys
import logging
import platform
from pathlib import Path

# 確保 src 在 Python 路徑中
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# 建立必要的資料夾
for folder in ['src', 'output', 'logs', 'config']:
    Path(folder).mkdir(exist_ok=True)

# Import


def print_banner():
    """顯示程式橫幅"""
    print("\n" + "="*70)
    print("📚 博客來電子書截圖工具 v2.0")
    print("="*70)
    print(f"📌 系統: {platform.system()}")
    print(f"📌 Python: {sys.version.split()[0]}")
    print("="*70 + "\n")


def main():
    # 顯示橫幅
    print_banner()

    # 設定日誌
    setup_logging()
    logger = logging.getLogger(__name__)

    # 載入設定
    config = load_config()

    crawler = None
    try:
        # 建立爬蟲實例
        print("🚀 啟動瀏覽器...")
        crawler = BooksCrawler(config)

        # 登入流程
        print("\n📝 登入流程")
        print("-" * 40)
        if not crawler.ensure_login(auto_login=config.get('auto_login', False)):
            logger.error("登入失敗，程式無法繼續。")
            return

        # 取得書籍網址
        print("\n📖 電子書設定")
        print("-" * 40)
        book_url = config.get('book_url')
        if not book_url:
            book_url = input("請輸入電子書網址: ").strip()

        if not book_url:
            logger.error("未提供電子書網址，程式無法繼續。")
            return

        # 導航到書籍頁面
        crawler.navigate_to_book(book_url)

        # 互動式提示，詢問使用者是否開始截圖
        print("\n📸 截圖準備")
        print("-" * 40)
        user_input = input("已完成前置作業，是否開始截圖？ (y/n): ").lower().strip()
        if user_input != 'y':
            logger.info("使用者取消操作，程式即將結束。")
            print("使用者取消操作，程式即將結束。")
            return

        # 執行自動截圖模式
        total_pages = config.get("total_pages", 100)
        delay = config.get("delay", 5)
        crawler.auto_capture_mode(total_pages, delay)

    except KeyboardInterrupt:
        logger.info("\n⚠️ 使用者中斷程式")
    except Exception as e:
        logger.error(f"❌ 發生錯誤: {e}", exc_info=True)
        print(f"\n❌ 錯誤: {e}")
        print("請檢查錯誤日誌以獲得更多資訊")
    finally:
        if crawler:
            print("\n🔄 正在關閉瀏覽器...")
            crawler.close()
        print("✅ 程式結束")


if __name__ == "__main__":
    main()
