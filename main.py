#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import logging
import platform
import time
from pathlib import Path
from src.utils import setup_logging, load_config
from src.crawler import BooksCrawler

def print_banner():
    """顯示程式橫幅"""
    print("\n" + "="*70)
    print("📚 博客來電子書截圖工具 v2.0")
    print("="*70)
    print(f"📌 系統: {platform.system()}")
    print(f"📌 Python: {sys.version.split()[0]}")
    print("="*70 + "\n")

def process_single_book(crawler, book_url, book_index, total_books, total_pages, delay):
    """處理單本電子書"""
    print("\n" + "="*70)
    print(f"📖 正在處理第 {book_index}/{total_books} 本電子書")
    print(f"🔗 網址: {book_url}")
    print("="*70)
    
    try:
        # 導航到電子書頁面
        crawler.navigate_to_book(book_url)
        
        # 等待頁面載入穩定
        time.sleep(3)
        
        # 執行自動截圖
        crawler.auto_capture_mode(total_pages, delay)
        
        print(f"\n✅ 第 {book_index}/{total_books} 本電子書處理完成")
        return True
        
    except Exception as e:
        print(f"\n❌ 第 {book_index}/{total_books} 本電子書處理失敗: {e}")
        logging.error(f"處理電子書失敗 {book_url}: {e}", exc_info=True)
        return False

def reset_crawler_state(crawler):
    """重置 crawler 狀態，準備處理下一本書"""
    try:
        # 切換回主頁面
        crawler.driver.switch_to.default_content()
        
        # 重置狀態變數
        crawler.iframe_switched = False
        crawler.tutorial_handled = False
        crawler.popup_closed_count = 0
        crawler.same_page_count = 0
        crawler.last_page_content = None
        crawler.current_page_number = None
        
        # 清理可能的彈出視窗
        try:
            crawler._close_popups()
        except:
            pass
        
        logging.info("✅ Crawler 狀態已重置")
        
    except Exception as e:
        logging.error(f"重置 crawler 狀態時發生錯誤: {e}")

def main():
    """主程式"""
    # 設定日誌
    setup_logging()
    
    # 載入設定
    config = load_config()
    
    # 顯示橫幅
    print_banner()
    
    # 建立 crawler 實例
    print("🔧 初始化瀏覽器...")
    crawler = BooksCrawler(config)
    
    try:
        # 執行登入（只需要登入一次）
        print("🔐 執行登入流程...")
        if not crawler.login(auto_captcha=False):
            print("❌ 登入失敗，程式結束。")
            return
        
        print("\n✅ 登入成功！")
        
        # 讓使用者輸入多本電子書網址
        print("\n" + "="*70)
        print("📚 請輸入電子書網址")
        print("💡 提示：")
        print("   - 可輸入多個網址，以逗號分隔")
        print("   - 或按 Enter 一次輸入一個網址")
        print("   - 輸入 'done' 或空白行結束輸入")
        print("="*70)
        
        book_urls = []
        
        # 方式一：一次輸入多個網址
        urls_input = input("\n請輸入所有電子書網址（以逗號分隔）或按 Enter 逐個輸入: ").strip()
        
        if urls_input and urls_input.lower() != 'done':
            # 如果有輸入，嘗試分割
            book_urls = [u.strip() for u in urls_input.split(",") if u.strip()]
        
        # 方式二：逐個輸入網址
        if not book_urls:
            print("\n請逐個輸入電子書網址（輸入 'done' 或空白行結束）：")
            while True:
                url = input(f"第 {len(book_urls) + 1} 本: ").strip()
                if not url or url.lower() == 'done':
                    break
                book_urls.append(url)
        
        # 檢查是否有輸入網址
        if not book_urls:
            print("\n❌ 未輸入任何網址，程式結束。")
            return
        
        print(f"\n📚 共有 {len(book_urls)} 本電子書待處理")
        
        # 取得設定參數
        total_pages = config.get("total_pages", None)  # None 表示自動偵測
        delay = config.get("delay", 2)
        
        if total_pages:
            print(f"📄 每本書最多截取: {total_pages} 頁")
        else:
            print(f"📄 將自動偵測每本書的總頁數")
        print(f"⏱️ 翻頁延遲: {delay} 秒")
        
        # 確認開始
        input("\n按 Enter 開始處理所有電子書...")
        
        # 記錄處理結果
        successful_books = []
        failed_books = []
        
        # 循序處理每本電子書
        for index, book_url in enumerate(book_urls, 1):
            # 處理單本書
            success = process_single_book(
                crawler, 
                book_url, 
                index, 
                len(book_urls), 
                total_pages, 
                delay
            )
            
            if success:
                successful_books.append(book_url)
            else:
                failed_books.append(book_url)
            
            # 如果不是最後一本，準備處理下一本
            if index < len(book_urls):
                print(f"\n⏳ 準備處理下一本電子書...")
                
                # 重置 crawler 狀態
                reset_crawler_state(crawler)
                
                # 等待一下，避免太快切換
                time.sleep(3)
        
        # 顯示總結果
        print("\n" + "="*70)
        print("📊 所有電子書處理完成！")
        print("="*70)
        print(f"✅ 成功: {len(successful_books)} 本")
        print(f"❌ 失敗: {len(failed_books)} 本")
        
        if failed_books:
            print("\n失敗的電子書網址：")
            for i, url in enumerate(failed_books, 1):
                print(f"  {i}. {url}")
        
        print("\n📁 所有截圖已儲存在 output 目錄下")
        print("="*70)
        
    except KeyboardInterrupt:
        print("\n\n⚠️ 使用者中斷程式執行")
    except Exception as e:
        print(f"\n❌ 程式發生錯誤: {e}")
        logging.error(f"主程式錯誤: {e}", exc_info=True)
    finally:
        # 關閉瀏覽器
        try:
            print("\n🔧 正在關閉瀏覽器...")
            crawler.close()
            print("✅ 瀏覽器已關閉")
        except Exception as e:
            print(f"❌ 關閉瀏覽器時發生錯誤: {e}")
        
        print("\n👋 程式結束，感謝使用！")

if __name__ == "__main__":
    main()