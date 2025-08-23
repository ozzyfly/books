#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import logging
import platform
from pathlib import Path
from datetime import datetime
from PIL import Image # 新增 Image 模組

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.firefox.service import Service
from webdriver_manager.firefox import GeckoDriverManager

logger = logging.getLogger(__name__)


class BooksCrawler:
    def __init__(self, email=None, password=None, headless=False, full_page_screenshot=False):
        self.email = email
        self.password = password
        self.driver = None
        self.wait = None
        self.output_dir = None
        self.main_iframe = None
        self.full_page_screenshot = full_page_screenshot # 新增全頁截圖設定
        self.setup_driver(headless)

    def setup_driver(self, headless=False):
        """Firefox WebDriver 設定 - 優化版"""
        logger.info("使用 Firefox WebDriver - 優化版")

        options = webdriver.FirefoxOptions()
        options.add_argument('--width=1920')
        options.add_argument('--height=1080')

        if platform.system() == "Darwin":
            options.set_preference("browser.privatebrowsing.autostart", False)
            options.set_preference("browser.download.folderList", 2)
            options.set_preference(
                "browser.download.manager.showWhenStarting", False)

        if headless:
            options.add_argument('--headless')
            logger.info("啟用無頭模式")

        # 優化設定
        options.set_preference("dom.webdriver.enabled", False)
        options.set_preference('useAutomationExtension', False)
        options.set_preference("browser.tabs.remote.autostart", False)
        options.set_preference("browser.tabs.remote.autostart.2", False)

        # 禁用圖片載入加速（可選）
        # options.set_preference('permissions.default.image', 2)

        try:
            service = Service(GeckoDriverManager().install())
            self.driver = webdriver.Firefox(service=service, options=options)
            self.wait = WebDriverWait(self.driver, 30)  # 增加等待時間
            self.driver.set_window_size(1920, 1080)

            # 設定頁面載入策略
            self.driver.set_page_load_timeout(60)

            logger.info("✅ Firefox WebDriver 啟動成功")

        except Exception as e:
            logger.error(f"❌ Firefox WebDriver 啟動失敗: {e}")
            raise

    def _perform_login(self):
        """執行實際的登入操作"""
        logger.info("🚀 開始自動登入...")
        try:
            self.driver.get("https://www.books.com.tw/")
            
            login_button = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), '會員登入')]"))
            )
            login_button.click()
            logger.info("🖱️ 已點擊會員登入按鈕。")

            login_iframe = self.wait.until(
                EC.presence_of_element_located((By.ID, "login_iframe"))
            )
            self.driver.switch_to.frame(login_iframe)
            logger.info("🔄 已切換到登入 iframe。")

            email_input = self.wait.until(
                EC.presence_of_element_located((By.ID, "login_id"))
            )
            email_input.send_keys(self.email)
            
            password_input = self.driver.find_element(By.ID, "login_pwd")
            password_input.send_keys(self.password)
            logger.info("🔑 已輸入帳號和密碼。")

            submit_button = self.driver.find_element(By.ID, "login_btn")
            submit_button.click()
            logger.info("✅ 登入請求已送出。")

            self.driver.switch_to.default_content()
            self.wait.until(
                EC.presence_of_element_located((By.XPATH, "//a[contains(text(), '會員專區')]"))
            )
            logger.info("🎉 登入成功！")
            return True
        except Exception as e:
            logger.error(f"❌ 自動登入失敗: {e}", exc_info=True)
            return False

    def ensure_login(self, auto_login=False):
        """確保使用者已登入"""
        logger.info("正在檢查登入狀態...")
        self.driver.get("https://www.books.com.tw/")
        try:
            # 檢查是否已經登入
            self.wait.until(
                EC.presence_of_element_located((By.XPATH, "//a[contains(text(), '會員專區')]"))
            )
            logger.info("✅ 使用者已登入。")
            return True
        except Exception:
            logger.info("使用者尚未登入。")

        if auto_login and self.email and self.password:
            if self._perform_login():
                return True
            else:
                logger.error("自動登入失敗，請嘗試手動登入。")

        # 手動登入流程
        login_choice = input("是否需要登入博客來？(y/n): ").strip().lower()
        if login_choice == 'y':
            self.driver.get("https://www.books.com.tw")
            print("請在瀏覽器中手動登入...")
            input("登入完成後按 Enter 繼續...")
            # 再次檢查登入狀態
            try:
                self.wait.until(
                    EC.presence_of_element_located((By.XPATH, "//a[contains(text(), '會員專區')]"))
                )
                logger.info("✅ 手動登入成功！")
                return True
            except Exception:
                logger.error("❌ 手動登入失敗或未完成。")
                return False
        return False

    def navigate_to_book(self, book_url):
        """導航到電子書頁面 - 改進版"""
        logger.info(f"前往: {book_url}")
        self.driver.get(book_url)

        # 等待頁面完全載入 (等待 iframe 出現)
        logger.info("等待頁面載入...")
        try:
            self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "iframe[id^='epubjs-view-']"))
            )
            logger.info("✅ 電子書 iframe 已載入。")
        except Exception:
            logger.warning("⚠️ 等待電子書 iframe 超時，繼續執行...")

        # 建立輸出目錄
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_dir = Path(f"output/ebook_{timestamp}")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"輸出目錄: {self.output_dir}")

    def handle_tutorial(self):
        """處理教學引導頁面"""
        try:
            self.driver.switch_to.default_content()
            logger.info("🔄 正在檢查教學引導頁面...")
            # 根據截圖，教學按鈕的 class 包含 "tutorial_button"
            next_button_xpath = "//button[contains(@class, 'tutorial_button') or contains(text(), '下一步') or contains(@class, 'next-btn')]"
            
            # 增加等待時間，確保按鈕出現
            self.wait.until(EC.presence_of_element_located((By.XPATH, next_button_xpath)))
            
            # 可能有多個教學步驟
            for i in range(5): # 最多點擊5次
                try:
                    next_button = self.driver.find_element(By.XPATH, next_button_xpath)
                    if next_button.is_displayed() and next_button.is_enabled():
                        logger.info(f"🖱️ 點擊教學引導按鈕 (第 {i+1} 次)...")
                        next_button.click()
                        time.sleep(0.5) # 短暫等待動畫效果
                    else:
                        break # 按鈕不可見或不可用，跳出循環
                except Exception:
                    logger.info("✅ 教學引導頁面處理完畢或不存在。")
                    break
        except Exception:
            logger.info("ℹ️ 未找到教學引導頁面，繼續執行。")

    def find_and_switch_to_ebook_iframe(self):
        """精準定位並切換到電子書 iframe"""
        try:
            # 1. 處理教學引導
            self.handle_tutorial()
            self.driver.switch_to.default_content()

            # 2. 精準定位 iframe
            logger.info("🔍 開始精準尋找電子書 iframe...")
            iframe_selector = "iframe[id^='epubjs-view-']"
            
            try:
                # 等待 iframe 出現
                iframe_element = self.wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, iframe_selector))
                )
                
                # 切換到 iframe
                self.driver.switch_to.frame(iframe_element)
                
                # 3. 驗證 iframe 內部內容
                # 等待一個比 <body> 更具體的元素，表示書籍已渲染
                # 等待一個比 <body> 更具體的元素，表示書籍已渲染
                self.wait.until(
                    EC.visibility_of_element_located((By.CSS_SELECTOR, "div.epub-view"))
                )
                # time.sleep(2) # 已由 visibility_of_element_located 取代
                logger.info("✅ 成功切換到電子書 iframe 並確認內容已載入。")
                return True
                
            except Exception as e:
                logger.error(f"❌ 未找到或無法切換到指定的電子書 iframe: {e}")
                self.diagnose_page_structure() # 失敗時執行診斷
                return False

        except Exception as e:
            logger.error(f"iframe 處理過程中發生嚴重錯誤: {e}", exc_info=True)
            return False

    def capture_page_with_retry(self, page_num, max_retries=3, full_page=False):
        """改進的截圖方法，包含重試機制，可選擇全頁截圖"""
        for attempt in range(max_retries):
            try:
                logger.info(
                    f"📸 截圖第 {page_num} 頁 (嘗試 {attempt + 1}/{max_retries}) {'(全頁)' if full_page else ''}")

                # 確保在正確的 frame 中
                if not self.find_and_switch_to_ebook_iframe():
                    # 如果找不到 iframe，嘗試截取整個頁面
                    self.driver.switch_to.default_content()
                    logger.warning("⚠️ 未能切換到電子書 iframe，將嘗試截取整個頁面。")

                # 等待內容穩定
                # 等待內容穩定
                self.wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "div.epub-view")))
                # time.sleep(2) # 已由 visibility_of_element_located 取代

                # 截圖路徑
                screenshot_path = self.output_dir / f"page_{page_num:04d}.png"

                # 執行截圖
                if full_page:
                    success = self.capture_full_page_screenshot(str(screenshot_path))
                else:
                    self.driver.save_screenshot(str(screenshot_path))
                    success = screenshot_path.exists() and screenshot_path.stat().st_size > 1024 # 確保檔案大小至少 > 1KB

                # 驗證截圖檔案
                if success:
                    logger.info(f"✅ 截圖成功: {screenshot_path.name}")
                    return True
                else:
                    logger.warning(f"截圖檔案 {screenshot_path.name} 為空或不存在。")

            except Exception as e:
                logger.error(f"截圖失敗 (嘗試 {attempt + 1}): {e}", exc_info=True)
                time.sleep(2)

        logger.error(f"❌ 第 {page_num} 頁在 {max_retries} 次嘗試後仍截圖失敗。")
        return False

    def capture_full_page_screenshot(self, filename):
        """
        截取整個頁面的截圖，包括可滾動區域。
        此方法會滾動頁面並拼接多張截圖。
        """
        logger.info(f"📸 嘗試截取全頁截圖: {filename}")
        try:
            # 獲取頁面總高度和視窗高度
            total_height = self.driver.execute_script("return document.body.scrollHeight")
            viewport_height = self.driver.execute_script("return window.innerHeight")
            viewport_width = self.driver.execute_script("return window.innerWidth")

            # 儲存所有截圖的列表
            screenshots = []
            current_position = 0

            while current_position < total_height:
                # 滾動到當前位置
                self.driver.execute_script(f"window.scrollTo(0, {current_position});")
                time.sleep(0.5) # 等待滾動和渲染

                # 截圖當前可視區域
                temp_screenshot_path = self.output_dir / "temp_part.png"
                self.driver.save_screenshot(str(temp_screenshot_path))
                screenshots.append(Image.open(temp_screenshot_path))
                os.remove(temp_screenshot_path) # 移除臨時檔案

                current_position += viewport_height

            # 拼接圖片
            if not screenshots:
                logger.error("❌ 未能截取任何部分截圖。")
                return False

            # 計算最終圖片的高度
            # 這裡需要考慮到最後一張截圖可能不是完整視窗高度
            final_height = sum(img.height for img in screenshots)
            
            # 創建一個新的空白圖片，用於拼接
            full_image = Image.new('RGB', (viewport_width, final_height))

            y_offset = 0
            for img in screenshots:
                full_image.paste(img, (0, y_offset))
                y_offset += img.height
                img.close() # 關閉圖片檔案

            full_image.save(filename)
            logger.info(f"✅ 全頁截圖成功: {filename}")
            return True

        except Exception as e:
            logger.error(f"❌ 全頁截圖失敗: {e}", exc_info=True)
            return False

    def smart_next_page(self):
        """智慧翻頁方法"""
        try:
            # 方法1: 嘗試點擊下一頁按鈕
            next_buttons = [
                "//button[contains(@class, 'next')]",
                "//button[contains(@class, 'right')]",
                "//div[contains(@class, 'viewer-right')]",
                "//a[contains(@class, 'next')]",
                "//*[@aria-label='Next page']",
                "//*[@id='next-page']"
            ]

            # 優先切換回主內容
            self.driver.switch_to.default_content()
            for xpath in next_buttons:
                try:
                    # 使用 WebDriverWait 提高穩定性
                    next_btn = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
                    next_btn.click()
                    logger.info(f"✅ 成功點擊翻頁按鈕 (策略: {xpath})")
                    return True
                except Exception:
                    continue # 嘗試下一個策略

            # 方法2: 使用鍵盤右鍵
            ActionChains(self.driver).send_keys(Keys.ARROW_RIGHT).perform()
            logger.info("✅ 使用鍵盤右鍵翻頁")
            return True

        except Exception as e:
            logger.error(f"翻頁失敗: {e}")
            return False


    def auto_capture_mode(self, total_pages=100, delay=5):
        """自動截圖模式"""
        print("\n" + "="*60)
        print("📸 自動截圖模式")
        print("="*60)
        print(f"📚 將截圖 {total_pages} 頁")
        print(f"⏱️ 每頁間隔 {delay} 秒")
        print("="*60)
        input("\n✅ 準備好後按 Enter 開始...")

        successful_pages = 0
        failed_pages = []

        for page_num in range(1, total_pages + 1):
            print(f"\n進度: [{page_num}/{total_pages}]")

            # 截圖當前頁面
            if self.capture_page_with_retry(page_num):
                successful_pages += 1
            else:
                failed_pages.append(page_num)
                logger.error(f"❌ 第 {page_num} 頁截圖失敗")

            # 如果不是最後一頁，執行翻頁
            if page_num < total_pages:
                print(f"等待 {delay} 秒後翻頁...")
                time.sleep(delay)

                if not self.smart_next_page():
                    logger.warning("翻頁可能失敗，繼續嘗試...")
                
                # 等待新頁面載入完成
                try:
                    self.wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "div.epub-view")))
                    logger.info("✅ 新頁面已載入。")
                except Exception:
                    logger.warning("⚠️ 等待新頁面載入超時。")

        # 顯示結果摘要
        print("\n" + "="*60)
        print("📊 截圖完成摘要")
        print("="*60)
        print(f"✅ 成功: {successful_pages} 頁")
        print(f"❌ 失敗: {len(failed_pages)} 頁")
        if failed_pages:
            print(f"失敗頁面: {failed_pages}")
        print(f"📁 檔案位置: {self.output_dir}")

    def close(self):
        """關閉瀏覽器"""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("瀏覽器已關閉")
            except Exception as e:
                logger.warning(f"關閉瀏覽器時出錯: {e}")
