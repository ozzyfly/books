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
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.firefox.service import Service as FirefoxService

logger = logging.getLogger(__name__)


class BooksCrawler:
    def __init__(self, config):
        self.config = config
        self.email = self.config.get('email')
        self.password = self.config.get('password')
        self.headless = self.config.get('headless', False)
        self.driver = None
        self.wait = None
        self.output_dir = None
        self.main_iframe = None
        self.full_page_screenshot = self.config.get('full_page_screenshot', False)
        self.setup_driver()

    def setup_driver(self):
        """根據設定檔動態設定 WebDriver"""
        browser = self.config.get('browser', 'firefox').lower()
        logger.info(f"使用 {browser.capitalize()} WebDriver")

        try:
            if browser == 'chrome':
                options = webdriver.ChromeOptions()
                options.add_argument('--window-size=1920,1080')
                if self.headless:
                    options.add_argument('--headless')
                service = ChromeService()
                self.driver = webdriver.Chrome(service=service, options=options)

            elif browser == 'edge':
                options = webdriver.EdgeOptions()
                options.add_argument('--window-size=1920,1080')
                if self.headless:
                    options.add_argument('--headless')
                webdriver_path = self.config.get('webdriver_path')
                # 檢查使用者是否在 config.json 中手動指定了 WebDriver 的路徑。
                # 這是為了解決 Selenium Manager 在某些網路環境（例如有特殊 DNS 設定或防火牆）
                # 下自動下載 WebDriver 失敗的問題。
                # 如果提供了有效的路徑，則使用該路徑來初始化 WebDriver 服務。
                if webdriver_path and os.path.exists(webdriver_path):
                    logger.info(f"使用指定的 WebDriver: {webdriver_path}")
                    service = EdgeService(executable_path=webdriver_path)
                else:
                    # 如果未提供路徑或路徑無效，則退回使用 Selenium Manager 的預設行為，
                    # 它會嘗試自動下載並管理 WebDriver。
                    logger.info("未指定或找不到 WebDriver 路徑，將使用 Selenium Manager。")
                    service = EdgeService()
                self.driver = webdriver.Edge(service=service, options=options)

            else:  # Default to firefox
                options = webdriver.FirefoxOptions()
                options.add_argument('--width=1920')
                options.add_argument('--height=1080')
                if self.headless:
                    options.add_argument('--headless')
                
                # Firefox 優化設定
                options.set_preference("dom.webdriver.enabled", False)
                options.set_preference('useAutomationExtension', False)
                
                service = FirefoxService(log_output='geckodriver.log')
                self.driver = webdriver.Firefox(service=service, options=options)

            self.wait = WebDriverWait(self.driver, 30)
            self.driver.set_page_load_timeout(60)

            logger.info(f"✅ {browser.capitalize()} WebDriver 啟動成功")

        except Exception as e:
            logger.error(f"❌ {browser.capitalize()} WebDriver 啟動失敗: {e}")
            if "Could not reach host" in str(e):
                logger.error("="*60)
                logger.error("無法下載 WebDriver，這通常是網路連線問題。")
                logger.error("請檢查您的網路連線、DNS 設定或防火牆。")
                logger.error("="*60)
            raise

    def _perform_login(self):
        """執行實際的登入操作"""
        logger.info("🚀 開始自動登入...")
        try:
            self.driver.get("https://www.books.com.tw/")
            
            # 使用更精確的 XPath 定位登入按鈕
            login_button = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//li[contains(@class, 'li_label_member_login')]/a"))
            )
            login_button.click()
            logger.info("🖱️ 已點擊會員登入按鈕。")

            # 登入表單現在位於新頁面，而非 iframe，因此移除 iframe 切換邏輯
            logger.info("🔄 已導航至登入頁面，不需切換 iframe。")

            email_input = self.wait.until(
                EC.presence_of_element_located((By.ID, "login_id"))
            )
            email_input.send_keys(self.email)
            
            # 根據最終確認的頁面結構，使用最精準的 ID 'login_pswd' 定位密碼欄位
            password_input = self.wait.until(
                EC.presence_of_element_located((By.ID, "login_pswd"))
            )
            password_input.send_keys(self.password)
            logger.info("🔑 已輸入帳號和密碼。")

            # 根據最新頁面結構，使用正確的 ID 'show-captcha' 定位登入按鈕
            submit_button = self.wait.until(
                EC.element_to_be_clickable((By.ID, "show-captcha"))
            )
            submit_button.click()
            logger.info("✅ 登入請求已送出。")

            # 新增：處理滑塊驗證碼
            try:
                # 等待滑塊驗證碼容器出現 (短暫等待)
                slider_captcha_container = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.ID, "slider_captcha_main"))
                )
                if slider_captcha_container:
                    logger.info("🧩 偵測到滑塊驗證碼。")
                    print("\n" + "="*50)
                    print("⚠️ 請手動完成瀏覽器中的滑塊驗證...")
                    print("="*50)
                    
                    # 等待使用者手動完成驗證 (最長等待2分鐘)
                    # 成功登入後頁面會跳轉，驗證碼元素也會因此失效 (stale)
                    WebDriverWait(self.driver, 120).until(
                        EC.staleness_of(slider_captcha_container)
                    )
                    logger.info("✅ 繼續執行...")

            except Exception:
                logger.info("ℹ️ 未偵測到滑塊驗證碼，或已自動通過。")

            # 已不在 iframe 中，不需切換回 default_content
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
            # 使用更長的等待時間和更精確的選擇器來檢查「會員登入」按鈕
            login_element_xpath = "//li[contains(@class, 'li_label_member_login')]"
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.XPATH, login_element_xpath))
            )
            logger.info("使用者尚未登入 (找到 '會員登入' 按鈕)。")
        except Exception:
            # 如果在15秒內找不到「會員登入」按鈕，我們假設使用者已登入
            logger.info("✅ 使用者已登入 (未找到 '會員登入' 按鈕)。")
            return True

        # --- 以下是登入流程 ---
        if auto_login and self.email and self.password:
            if self._perform_login():
                return True
            else:
                logger.error("自動登入失敗，請嘗試手動登入。")

        # 手動登入流程
        logger.info("切換至手動登入流程。")
        print("\n" + "="*50)
        print("⚠️ 自動登入失敗或未設定，請在瀏覽器中手動登入...")
        print("="*50)
        input("登入完成後，請按 Enter 鍵繼續...")
        
        # 再次檢查登入狀態，確認「會員登入」按鈕已消失
        try:
            self.driver.refresh() # 刷新頁面以獲取最新的登入狀態
            logger.info("頁面已刷新，正在重新確認登入狀態...")
            login_element_xpath = "//li[contains(@class, 'li_label_member_login')]"
            WebDriverWait(self.driver, 10).until_not(
                EC.presence_of_element_located((By.XPATH, login_element_xpath))
            )
            logger.info("✅ 手動登入成功！")
            self._save_diagnostic_snapshot("manual_login_success")
            return True
        except Exception:
            logger.error("❌ 手動登入失敗或未完成。")
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

    def _click_tutorial_next_button(self, selectors, step_count):
        """
        輔助函式：嘗試使用多個選擇器策略來尋找並點擊教學引導的「下一步」按鈕。

        Args:
            selectors (list): 一個包含 (By, value) 元組的列表，定義了多種尋找按鈕的策略。
            step_count (int): 目前的步驟計數，主要用於日誌記錄和偵錯截圖。

        Returns:
            bool: 如果成功找到並點擊按鈕，返回 True；否則返回 False。
        """
        for by, value in selectors:
            try:
                # 使用 WebDriverWait 等待按鈕可被點擊，取代固定等待
                button = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((by, value))
                )
                logger.info(f"🖱️ 找到教學按鈕 (策略: {by}='{value}')，正在點擊第 {step_count} 次...")
                button.click()
                
                # 點擊後儲存截圖到正確的輸出目錄
                if self.output_dir:
                    screenshot_path = self.output_dir / f"tutorial_step_{step_count}.png"
                    self.driver.save_screenshot(str(screenshot_path))
                    logger.info(f"📸 已儲存教學步驟截圖: {screenshot_path.name}")
                else:
                    logger.warning("⚠️ output_dir 未設定，跳過教學步驟截圖。")

                # 短暫等待動畫效果
                time.sleep(0.5)
                return True
            except Exception:
                # 如果這個選擇器失敗，繼續嘗試下一個
                continue
        return False

    def handle_tutorial(self):
        """
        自動化處理電子書閱讀器初始可能出現的教學引導畫面。

        此方法會：
        1. 使用多種策略尋找「下一步」按鈕。
        2. 持續點擊直到教學結束 (按鈕消失)。
        3. 包含重試機制，以應對頁面載入延遲等問題。
        """
        max_retries = 3
        for i in range(max_retries):
            try:
                self.driver.switch_to.default_content()
                logger.info(f"🔄 正在檢查教學引導頁面... (第 {i + 1}/{max_retries} 次嘗試)")

                # 定義多個可能的選擇器來尋找「下一步」按鈕
                selectors = [
                    (By.ID, "UIObj-demo-next-btn"),
                    (By.CSS_SELECTOR, ".tutorial-next-button"),
                    (By.XPATH, "//button[contains(text(), '下一步')]"),
                    (By.XPATH, "//a[contains(text(), 'Next')]"),
                    (By.CSS_SELECTOR, "div[class*='-next-btn']"),
                ]
                
                step_count = 0
                # 持續點擊「下一步」，直到找不到按鈕為止
                while step_count < 10:  # 最多點擊10次以防無限迴圈
                    step_count += 1
                    if not self._click_tutorial_next_button(selectors, step_count):
                        # 如果返回 False，表示所有選擇器都試過且找不到按鈕
                        if step_count > 1:  # step_count 從 1 開始，所以 > 1 表示至少點擊過一次
                            logger.info(f"✅ 教學引導處理完畢，總共點擊了 {step_count - 1} 次。")
                        else:
                            logger.info("ℹ️ 未找到任何教學引導按鈕，繼續執行。")
                        break  # 跳出 while 迴圈
                
                logger.info(f"✅ 第 {i + 1} 次嘗試成功，結束教學引導處理。")
                return  # 成功處理後，結束整個函式

            except Exception as e:
                logger.warning(f"❌ 處理教學引導時發生錯誤 (第 {i + 1} 次嘗試): {e}")
                if i < max_retries - 1:
                    logger.info("🔄 正在重新整理頁面並重試...")
                    self.driver.refresh()
                    time.sleep(5)  # 等待頁面重新載入
                else:
                    logger.error(f"❌ 在 {max_retries} 次嘗試後，處理教學引導失敗。")
                    # 使用一致的診斷快照功能
                    self._save_diagnostic_snapshot("tutorial_handling_failed")
                    logger.info("ℹ️ 將繼續執行後續步驟...")

    def find_and_switch_to_ebook_iframe(self):
        """精準定位並切換到電子書 iframe，並驗證內部內容"""
        self.driver.switch_to.default_content()
        try:
            # 1. 處理教學引導
            self.handle_tutorial()
            self.driver.switch_to.default_content()

            # 2. 精準定位 iframe
            logger.info("🔍 開始精準尋找電子書 iframe...")
            iframe_selector = "iframe[id^='epubjs-view-']"
            
            try:
                # 等待 iframe 出現
                # 策略更新：使用 'frame_to_be_available_and_switch_to_it'
                # 這個條件會等待 iframe 存在並且可以被成功切換，一步到位解決時序問題。
                self.wait.until(
                    EC.frame_to_be_available_and_switch_to_it((By.CSS_SELECTOR, iframe_selector))
                )
                logger.info("✅ 已成功切換到電子書 iframe，正在驗證內部內容...")

                # 3. 驗證 iframe 內部內容
                #    此驗證邏輯現在是正確的，因為我們已經在 iframe 內部。
                #    等待 body > div 的出現，確保 epub.js 已渲染內容。
                self.wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "body > div"))
                )
                logger.info("✅ iframe 內部內容驗證成功。")
                return True
                
            except Exception as e:
                logger.error(f"❌ 未找到、無法切換或驗證電子書 iframe: {e}")
                self.diagnose_page_structure() # 失敗時執行診斷
                return False

        except Exception as e:
            logger.error(f"iframe 處理過程中發生嚴重錯誤: {e}", exc_info=True)
            return False

    def diagnose_page_structure(self):
        """當找不到指定的 iframe 時，執行此函式來診斷頁面結構。"""
        logger.info("🕵️‍♂️ 開始進行頁面結構診斷...")

        # 確保切換回主內容
        self.driver.switch_to.default_content()

        # 建立診斷檔案的儲存路徑
        diag_dir = self.output_dir or Path("output/diagnostics")
        diag_dir.mkdir(parents=True, exist_ok=True)
        
        # 儲存頁面原始碼
        source_path = diag_dir / "page_source.html"
        with open(source_path, "w", encoding="utf-8") as f:
            f.write(self.driver.page_source)
        logger.info(f"📄 頁面原始碼已儲存至: {source_path}")

        # 儲存頁面截圖
        screenshot_path = diag_dir / "diagnostic_screenshot.png"
        self.driver.save_screenshot(str(screenshot_path))
        logger.info(f"📸 診斷截圖已儲存至: {screenshot_path}")

        # 尋找所有的 iframe 和 frame
        frames = self.driver.find_elements(By.TAG_NAME, "iframe")
        frames.extend(self.driver.find_elements(By.TAG_NAME, "frame"))

        if frames:
            logger.info(f"🖼️ 找到 {len(frames)} 個框架 (iframe/frame):")
            for i, frame in enumerate(frames):
                try:
                    frame_id = frame.get_attribute('id')
                    frame_name = frame.get_attribute('name')
                    frame_src = frame.get_attribute('src')
                    logger.info(
                        f"  - 框架 {i+1}: "
                        f"ID='{frame_id or 'N/A'}', "
                        f"Name='{frame_name or 'N/A'}', "
                        f"Src='{frame_src or 'N/A'}'"
                    )
                except Exception as e:
                    logger.warning(f"  - 無法獲取框架 {i+1} 的屬性: {e}")
        else:
            logger.warning("⚠️ 在頁面上未找到任何 <iframe> 或 <frame> 元素。")

    def capture_page_with_retry(self, page_num, max_retries=3, full_page=False):
        """改進的截圖方法，包含重試機制，可選擇全頁截圖"""
        for attempt in range(max_retries):
            try:
                logger.info(
                    f"📸 截圖第 {page_num} 頁 (嘗試 {attempt + 1}/{max_retries}) {'(全頁)' if full_page else ''}")

                # 確保在正確的 frame 中 (此函式現在已包含內部驗證)
                if not self.find_and_switch_to_ebook_iframe():
                    # 如果找不到 iframe，切換回主內容並嘗試截取整個頁面
                    self.driver.switch_to.default_content()
                    logger.warning("⚠️ 未能切換到電子書 iframe，將嘗試截取整個頁面。")
                    # 即使 iframe 失敗，仍繼續嘗試截圖主頁面，而不是直接失敗
                
                # 等待內容穩定的邏輯已移至 find_and_switch_to_ebook_iframe，此處不再需要

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

    def _save_diagnostic_snapshot(self, filename_prefix):
        """儲存當前頁面的截圖和 HTML 原始碼以供診斷。"""
        try:
            # 確保輸出資料夾存在
            if not self.output_dir:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                self.output_dir = Path(f"output/ebook_{timestamp}")
                self.output_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"建立診斷輸出目錄: {self.output_dir}")

            # 定義檔案路徑
            png_path = self.output_dir / f"{filename_prefix}.png"
            html_path = self.output_dir / f"{filename_prefix}.html"

            # 儲存截圖
            self.driver.save_screenshot(str(png_path))
            
            # 儲存 HTML
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
            
            # 移除無效的 get_log 方法，改為提示使用者檢查主日誌檔
            logger.info("ℹ️ 瀏覽器控制台日誌已重定向到專案根目錄下的 `geckodriver.log` 檔案。")
            
            logger.info(f"📸 快照已儲存: {png_path.name}, {html_path.name}")

        except Exception as e:
            logger.error(f"❌ 儲存診斷快照失敗 ({filename_prefix}): {e}")

    def auto_capture_mode(self, total_pages=100, delay=5):
        """自動截圖模式 - 重寫版"""
        print("\n" + "="*60)
        print("📸 自動截圖模式")
        print("="*60)
        print(f"📚 將截圖 {total_pages} 頁")
        print(f"⏱️ 每頁間隔 {delay} 秒")
        print("="*60)
        input("\n✅ 準備好後按 Enter 開始...")

        # 確保已切換到 iframe
        if not self.find_and_switch_to_ebook_iframe():
            logger.error("❌ 無法開始截圖，因為找不到電子書 iframe。")
            return

        # 互動式提示：在所有準備工作完成後，給予使用者手動開始的機會
        # 這提供了一個檢查點，讓使用者可以在截圖前確認瀏覽器狀態是否正常
        user_input = input("✅ 已完成登入與教學引導，是否開始截圖？ (y/n): ").lower()
        if user_input != 'y':
            print("使用者取消操作，程式即將結束。")
            self.close()
            return

        self.total_pages = total_pages
        self.current_page = 1
        successful_pages = 0
        failed_pages = []

        while self.current_page <= self.total_pages:
            print(f"\n進度: [{self.current_page}/{self.total_pages}]")

            # 截圖當前頁面
            if self.capture_page_with_retry(self.current_page):
                successful_pages += 1
            else:
                failed_pages.append(self.current_page)
                logger.error(f"❌ 第 {self.current_page} 頁截圖失敗")

            # 如果不是最後一頁，執行翻頁
            if self.current_page < self.total_pages:
                print(f"等待 {delay} 秒後翻頁...")
                time.sleep(delay)

                # 直接在 iframe 的 body 上發送向右鍵事件
                try:
                    body = self.driver.find_element(By.TAG_NAME, "body")
                    ActionChains(self.driver).send_keys_to_element(body, Keys.ARROW_RIGHT).perform()
                    logger.info("✅ 已發送翻頁指令 (ARROW_RIGHT)。")
                    # 短暫等待頁面渲染
                    time.sleep(1)
                except Exception as e:
                    logger.error(f"❌ 發送翻頁指令失敗: {e}")
                    # 即使翻頁失敗，也繼續嘗試下一頁的截圖
            
            self.current_page += 1

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
