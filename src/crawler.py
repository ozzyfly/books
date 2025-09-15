#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import threading
import logging
import platform
from pathlib import Path
from datetime import datetime
from PIL import Image

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.edge.service import Service as EdgeService

logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)


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
        self.iframe_switched = False  # 追蹤是否已切換到 iframe
        self.tutorial_handled = False  # 追蹤是否已處理教學引導
        self.popup_closed_count = 0  # 追蹤關閉的彈出視窗數量
        self.last_page_content = None  # 儲存上一頁的內容用於比較
        self.same_page_count = 0  # 追蹤相同頁面的次數
        self.current_page_number = None  # 追蹤當前頁碼
        self.setup_driver()

    def setup_driver(self):
        """只啟動 Edge WebDriver"""
        logger.info("使用 Edge WebDriver")
        try:
            options = webdriver.EdgeOptions()
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-gpu')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-extensions')
            options.add_argument('--disable-infobars')
            options.add_argument('--disable-notifications')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--disable-animations')
            options.add_argument('--remote-debugging-port=9222')
            
            if self.headless:
                options.add_argument('--headless')
            
            webdriver_path = self.config.get('webdriver_path')
            if webdriver_path and os.path.exists(webdriver_path):
                logger.info(f"使用指定的 WebDriver: {webdriver_path}")
                service = EdgeService(executable_path=webdriver_path)
            else:
                logger.info("未指定或找不到 WebDriver 路徑，將使用 Selenium Manager。")
                service = EdgeService()
            
            self.driver = webdriver.Edge(service=service, options=options)
            self.wait = WebDriverWait(self.driver, 5)
            self.driver.set_page_load_timeout(60)
            logger.info("✅ Edge WebDriver 啟動成功")
            
        except Exception as e:
            logger.error(f"❌ Edge WebDriver 啟動失敗: {e}")
            if "Could not reach host" in str(e):
                logger.error("="*60)
                logger.error("無法下載 WebDriver，這通常是網路連線問題。")
                logger.error("請檢查您的網路連線、DNS 設定或防火牆。")
                logger.error("="*60)
            raise

    def login(self, auto_captcha=False):
        """
        執行一個線性的、無條件的登入流程。
        該流程會自動點擊登入、填寫帳號密碼，然後暫停，等待使用者手動處理 CAPTCHA。
        """
        logger.info("🚀 開始執行線性登入流程...")
        self.driver.get("https://www.books.com.tw/")

        try:
            # 步驟 0：處理彈出式視窗
            self._handle_popups()

            # 步驟一：點擊「會員登入」
            if not self._click_login_link():
                return False

            # 步驟二：填寫帳號
            if not self._fill_username():
                return False

            # 步驟三：填寫密碼
            if not self._fill_password():
                return False

            # 步驟四：點擊「登入」按鈕以觸發 CAPTCHA
            if not self._click_login_button():
                return False

            # 步驟五：人工確認 CAPTCHA 驗證（僅主進程）
            if not auto_captcha:
                print("\n" + "="*60)
                print("🤖 已自動填寫帳密並觸發驗證。")
                print("請在瀏覽器中手動完成 CAPTCHA 驗證，完成後請按 Enter 繼續...")
                print("="*60)
                input()  # 等待使用者按 Enter
                logger.info("🎉 使用者已確認完成手動驗證，繼續執行。")
            
            return True

        except TimeoutException as e:
            logger.error(f"❌ 登入流程中的某個元素等待逾時: {e}", exc_info=True)
            self._save_diagnostic_snapshot("login_timeout_failure")
            return False
        except Exception as e:
            logger.error(f"❌ 登入流程失敗: {e}", exc_info=True)
            self._save_diagnostic_snapshot("login_generic_failure")
            return False

    def _handle_popups(self):
        """處理彈出式視窗"""
        try:
            logger.info("步驟 0/5：檢查彈出式視窗...")
            close_selectors = [
                (By.ID, "close_top_banner"),
                (By.CSS_SELECTOR, "button.close"),
                (By.XPATH, "//button[contains(text(), '關閉')]")
            ]
            for by, value in close_selectors:
                try:
                    close_button = WebDriverWait(self.driver, 2).until(
                        EC.element_to_be_clickable((by, value))
                    )
                    close_button.click()
                    logger.info(f"✅ 步驟 0/5：偵測到並關閉彈窗 ({by}, {value})。")
                    break
                except Exception:
                    continue
        except Exception:
            logger.info("ℹ️ 步驟 0/5：未偵測到彈出式視窗，繼續執行。")

    def _click_login_link(self):
        """點擊會員登入連結"""
        logger.info("步驟 1/5：等待『會員登入』按鈕...")
        login_selectors = [
            (By.CSS_SELECTOR, "span.member_class_name"),
            (By.LINK_TEXT, "會員登入"),
            (By.XPATH, "//span[contains(text(), '會員登入')]")
        ]
        for by, value in login_selectors:
            try:
                login_link = self.driver.find_element(by, value)
                login_link.click()
                return True
            except Exception:
                continue
        
        logger.error("❌ 找不到『會員登入』按鈕。")
        self._save_diagnostic_snapshot("login_no_login_button")
        return False

    def _fill_username(self):
        """填寫使用者名稱"""
        logger.info("步驟 2/5：等待帳號輸入框...")
        username_selectors = [
            (By.ID, "login_id_width01"),
            (By.NAME, "login_id"),
            (By.CSS_SELECTOR, "input[type='text']")
        ]
        
        email_value = self.email or self.config.get("email")
        if not email_value:
            logger.error("❌ 未設定 email，請檢查 config.json。")
            return False
        
        for by, value in username_selectors:
            try:
                username_input = self.driver.find_element(by, value)
                username_input.clear()
                username_input.send_keys(email_value)
                return True
            except Exception:
                continue
        
        logger.error("❌ 找不到帳號輸入框。")
        self._save_diagnostic_snapshot("login_no_username_input")
        return False

    def _fill_password(self):
        """填寫密碼"""
        logger.info("步驟 3/5：等待密碼輸入框...")
        password_selectors = [
            (By.ID, "login_pswd"),
            (By.NAME, "login_pswd"),
            (By.CSS_SELECTOR, "input[type='password']")
        ]
        
        for by, value in password_selectors:
            try:
                password_input = self.driver.find_element(by, value)
                password_input.clear()
                password_input.send_keys(self.config["password"])
                return True
            except Exception:
                continue
        
        logger.error("❌ 找不到密碼輸入框。")
        self._save_diagnostic_snapshot("login_no_password_input")
        return False

    def _click_login_button(self):
        """點擊登入按鈕"""
        logger.info("步驟 4/5：等待『登入』按鈕...")
        login_btn_selectors = [
            (By.ID, "show-captcha"),
            (By.ID, "login_btn"),
            (By.CSS_SELECTOR, "button[type='submit']"),
            (By.XPATH, "//button[contains(text(), '登入')]")
        ]
        
        for by, value in login_btn_selectors:
            try:
                login_button = self.driver.find_element(by, value)
                login_button.click()
                return True
            except Exception:
                continue
        
        logger.error("❌ 找不到『登入』按鈕。")
        self._save_diagnostic_snapshot("login_no_login_btn")
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
        
        # 自動列出所有 button/a 標籤資訊
        self.list_all_buttons_and_links()

    def list_all_buttons_and_links(self):
        """
        診斷方法：列出頁面上所有的按鈕和連結
        用於調試和理解頁面結構
        """
        try:
            logger.info("🔍 開始掃描頁面上的按鈕和連結...")
            
            # 儲存到診斷目錄
            diag_dir = self.output_dir or Path("output/diagnostics")
            diag_dir.mkdir(parents=True, exist_ok=True)
            
            # 掃描所有按鈕
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            logger.info(f"📝 找到 {len(buttons)} 個按鈕:")
            
            button_info = []
            for idx, btn in enumerate(buttons[:20], 1):  # 限制顯示前20個
                try:
                    btn_id = btn.get_attribute('id')
                    btn_class = btn.get_attribute('class')
                    btn_text = btn.text.strip()[:50]  # 限制文字長度
                    btn_visible = btn.is_displayed()
                    btn_enabled = btn.is_enabled()
                    
                    info = f"  [{idx}] ID: {btn_id or 'N/A'}, Class: {btn_class or 'N/A'}, Text: '{btn_text}', Visible: {btn_visible}, Enabled: {btn_enabled}"
                    logger.info(info)
                    button_info.append(info)
                except Exception as e:
                    logger.debug(f"  [{idx}] 無法獲取按鈕資訊: {e}")
            
            # 掃描所有連結
            links = self.driver.find_elements(By.TAG_NAME, "a")
            logger.info(f"📝 找到 {len(links)} 個連結:")
            
            link_info = []
            for idx, link in enumerate(links[:20], 1):  # 限制顯示前20個
                try:
                    link_href = link.get_attribute('href')
                    link_text = link.text.strip()[:50]  # 限制文字長度
                    link_visible = link.is_displayed()
                    
                    info = f"  [{idx}] Href: {link_href or 'N/A'}, Text: '{link_text}', Visible: {link_visible}"
                    logger.info(info)
                    link_info.append(info)
                except Exception as e:
                    logger.debug(f"  [{idx}] 無法獲取連結資訊: {e}")
            
            # 將診斷資訊寫入檔案
            diag_file = diag_dir / "page_elements_diagnostic.txt"
            with open(diag_file, "w", encoding="utf-8") as f:
                f.write(f"頁面元素診斷報告\n")
                f.write(f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"URL: {self.driver.current_url}\n")
                f.write("="*60 + "\n\n")
                
                f.write(f"按鈕 (共 {len(buttons)} 個):\n")
                for info in button_info:
                    f.write(info + "\n")
                
                f.write(f"\n連結 (共 {len(links)} 個):\n")
                for info in link_info:
                    f.write(info + "\n")
            
            logger.info(f"📄 診斷資訊已儲存至: {diag_file}")
            
        except Exception as e:
            logger.warning(f"❌ 列出按鈕和連結時發生錯誤: {e}")

    def handle_tutorial(self):
        """
        自動化處理電子書閱讀器初始可能出現的教學引導畫面。
        """
        # 如果已經處理過教學引導，直接返回
        if self.tutorial_handled:
            logger.info("ℹ️ 教學引導已處理過，跳過此步驟")
            return
        
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
                        if step_count > 1:
                            logger.info(f"✅ 教學引導處理完畢，總共點擊了 {step_count - 1} 次。")
                        else:
                            logger.info("ℹ️ 未找到任何教學引導按鈕，繼續執行。")
                        break
                
                self.tutorial_handled = True  # 標記為已處理
                logger.info(f"✅ 第 {i + 1} 次嘗試成功，結束教學引導處理。")
                return

            except Exception as e:
                logger.warning(f"❌ 處理教學引導時發生錯誤 (第 {i + 1} 次嘗試): {e}")
                if i < max_retries - 1:
                    logger.info("🔄 正在重新整理頁面並重試...")
                    self.driver.refresh()
                    time.sleep(1)
                else:
                    logger.error(f"❌ 在 {max_retries} 次嘗試後，處理教學引導失敗。")
                    self._save_diagnostic_snapshot("tutorial_handling_failed")
                    self.tutorial_handled = True  # 避免重複嘗試
                    logger.info("ℹ️ 將繼續執行後續步驟...")

    def _click_tutorial_next_button(self, selectors, step_count):
        """
        輔助函式：嘗試使用多個選擇器策略來尋找並點擊教學引導的「下一步」按鈕。
        """
        for by, value in selectors:
            try:
                button = WebDriverWait(self.driver, 2).until(
                    EC.element_to_be_clickable((by, value))
                )
                logger.info(f"🖱️ 找到教學按鈕 (策略: {by}='{value}')，正在點擊第 {step_count} 次...")
                button.click()
                time.sleep(0.1)
                return True
            except Exception:
                continue
        return False

    def find_and_switch_to_ebook_iframe(self):
        """精準定位並切換到電子書 iframe，並驗證內部內容"""
        # 如果已經在 iframe 中，直接返回
        if self.iframe_switched:
            try:
                # 驗證是否仍在正確的 iframe 中
                self.driver.find_element(By.CSS_SELECTOR, "body > div, body > *")
                return True
            except:
                # 如果驗證失敗，重置狀態並重新切換
                self.iframe_switched = False
                logger.info("⚠️ iframe 狀態已失效，重新切換...")
        
        self.driver.switch_to.default_content()
        try:
            # 1. 處理教學引導（只在第一次時處理）
            if not self.tutorial_handled:
                self.handle_tutorial()
                self.driver.switch_to.default_content()

            # 2. 先列出所有 iframe 供診斷（只在調試模式下執行）
            if logger.level <= logging.DEBUG:
                all_iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                logger.debug(f"頁面上找到 {len(all_iframes)} 個 iframe")

            # 3. 嘗試多種選擇器
            iframe_selectors = [
                "iframe[id^='epubjs-view-']",
                "iframe[enable-annotation='true']",
                "div.epub-container iframe",
                "iframe[class*='epub']",
                "iframe[class*='book']",
                "iframe",
            ]
            
            for selector in iframe_selectors:
                try:
                    logger.debug(f"嘗試 iframe 選擇器: {selector}")
                    self.wait.until(EC.frame_to_be_available_and_switch_to_it(
                        (By.CSS_SELECTOR, selector)))
                    
                    # 驗證 iframe 內容
                    self.wait.until(EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "body > div, body > *")))
                    
                    self.iframe_switched = True  # 標記為已切換
                    logger.info(f"✅ 已成功切換到電子書 iframe")
                    return True
                    
                except Exception:
                    self.driver.switch_to.default_content()
                    continue
            
            logger.error("❌ 所有 iframe 選擇器都失敗了")
            self.diagnose_page_structure()
            return False
            
        except Exception as e:
            logger.error(f"iframe 處理過程中發生嚴重錯誤: {e}", exc_info=True)
            return False

    def diagnose_page_structure(self):
        """當找不到指定的 iframe 時，執行此函式來診斷頁面結構。"""
        logger.info("🕵️‍♂️ 開始進行頁面結構診斷...")

        self.driver.switch_to.default_content()

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
        """改進的截圖方法，包含重試機制和重複內容檢測"""
        for attempt in range(max_retries):
            try:
                logger.info(
                    f"📸 截圖第 {page_num} 頁 (嘗試 {attempt + 1}/{max_retries}) "
                    f"{'(全頁)' if full_page else ''}")

                # 只在需要時切換到 iframe
                if not self.iframe_switched:
                    if not self.find_and_switch_to_ebook_iframe():
                        self.driver.switch_to.default_content()
                        logger.warning("⚠️ 未能切換到電子書 iframe，將嘗試截取整個頁面。")
                
                # 截圖路徑
                screenshot_path = self.output_dir / f"page_{page_num:04d}.png"

                # 執行截圖
                if full_page:
                    success = self.capture_full_page_screenshot(str(screenshot_path))
                else:
                    self.driver.save_screenshot(str(screenshot_path))
                    success = screenshot_path.exists() and screenshot_path.stat().st_size > 1024

                # 驗證截圖檔案
                if success:
                    # 檢查是否與前一張截圖相同
                    if page_num > 1:
                        prev_screenshot_path = self.output_dir / f"page_{page_num-1:04d}.png"
                        if prev_screenshot_path.exists() and self._compare_screenshots(
                            str(prev_screenshot_path), str(screenshot_path)):
                            logger.warning(f"⚠️ 第 {page_num} 頁截圖與前一頁相同")
                            self.same_page_count += 1
                            # 如果確實相同，刪除重複的截圖
                            if self.same_page_count >= 2:
                                screenshot_path.unlink()  # 刪除重複的檔案
                                logger.info(f"🗑️ 已刪除重複的截圖檔案")
                                return False
                        else:
                            self.same_page_count = 0
                    
                    logger.info(f"✅ 截圖成功: {screenshot_path.name}")
                    return True
                else:
                    logger.warning(f"截圖檔案 {screenshot_path.name} 為空或不存在。")
                    # 重置 iframe 狀態，下次重新切換
                    self.iframe_switched = False

            except Exception as e:
                logger.error(f"截圖失敗 (嘗試 {attempt + 1}): {e}", exc_info=True)
                self.iframe_switched = False  # 重置狀態
                time.sleep(0.5)

        logger.error(f"❌ 第 {page_num} 頁在 {max_retries} 次嘗試後仍截圖失敗。")
        return False
    
    def _compare_screenshots(self, path1, path2):
        """比較兩張截圖是否相同"""
        try:
            img1 = Image.open(path1)
            img2 = Image.open(path2)
            
            # 如果尺寸不同，直接返回 False
            if img1.size != img2.size:
                return False
            
            # 將圖片轉換為相同模式進行比較
            img1 = img1.convert('RGB')
            img2 = img2.convert('RGB')
            
            # 快速比較：取樣比較
            # 只比較部分像素以提高效能
            width, height = img1.size
            sample_points = min(1000, width * height // 100)  # 取樣點數
            
            import random
            random.seed(42)  # 固定隨機種子以確保一致性
            
            differences = 0
            for _ in range(sample_points):
                x = random.randint(0, width - 1)
                y = random.randint(0, height - 1)
                
                pixel1 = img1.getpixel((x, y))
                pixel2 = img2.getpixel((x, y))
                
                # 允許些微差異（壓縮造成的）
                if any(abs(p1 - p2) > 5 for p1, p2 in zip(pixel1, pixel2)):
                    differences += 1
            
            # 如果差異小於 1%，認為圖片相同
            similarity = 1 - (differences / sample_points)
            is_same = similarity > 0.99
            
            if is_same:
                logger.debug(f"截圖相似度: {similarity:.2%}")
            
            img1.close()
            img2.close()
            
            return is_same
            
        except Exception as e:
            logger.debug(f"比較截圖時發生錯誤: {e}")
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
                time.sleep(0.2)  # 等待滾動和渲染

                # 截圖當前可視區域
                temp_screenshot_path = self.output_dir / f"temp_part_{len(screenshots)}.png"
                self.driver.save_screenshot(str(temp_screenshot_path))
                
                # 開啟並儲存圖片
                img = Image.open(temp_screenshot_path)
                screenshots.append(img.copy())
                img.close()
                os.remove(temp_screenshot_path)  # 移除臨時檔案

                current_position += viewport_height

            # 拼接圖片
            if not screenshots:
                logger.error("❌ 未能截取任何部分截圖。")
                return False

            # 創建一個新的空白圖片，用於拼接
            full_image = Image.new('RGB', (viewport_width, total_height))

            y_offset = 0
            for img in screenshots:
                full_image.paste(img, (0, y_offset))
                y_offset += img.height
                img.close()

            full_image.save(filename)
            logger.info(f"✅ 全頁截圖成功: {filename}")
            return True

        except Exception as e:
            logger.error(f"❌ 全頁截圖失敗: {e}", exc_info=True)
            return False

    def smart_next_page(self):
        """智慧翻頁方法"""
        try:
            # 優先切換回主內容
            self.driver.switch_to.default_content()
            
            # 方法1: 嘗試點擊下一頁按鈕
            next_buttons = [
                "//button[@id='UiObj-book-right-btn']",
                "//button[contains(@class, 'viewer__body__pagination') and contains(@class, 'right')]",
                "//button[contains(@class, 'next')]",
                "//button[contains(@class, 'right')]",
                "//div[contains(@class, 'viewer-right')]",
                "//a[contains(@class, 'next')]",
                "//*[@aria-label='Next page']",
                "//*[@id='next-page']"
            ]

            for xpath in next_buttons:
                try:
                    next_btn = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
                    next_btn.click()
                    logger.info(f"✅ 成功點擊翻頁按鈕 (策略: {xpath})")
                    return True
                except Exception:
                    continue

            # 方法2: 使用鍵盤右鍵
            ActionChains(self.driver).send_keys(Keys.ARROW_RIGHT).perform()
            logger.info("✅ 使用鍵盤右鍵翻頁")
            return True

        except Exception as e:
            logger.error(f"翻頁失敗: {e}")
            return False

    def auto_capture_mode(self, total_pages=None, delay=5):
        """自動截圖模式 - 智慧分頁版（改進版）"""
        print("\n" + "="*60)
        print("📸 自動截圖模式 (智慧分頁)")
        print("="*60)
        print(f"⏱️ 每頁間隔 {delay} 秒")
        print("📚 將自動偵測最後一頁並停止")
        print("="*60)
        print("\n✅ 已自動開始截圖流程...")
        
        # 確保已切換到 iframe
        if not self.find_and_switch_to_ebook_iframe():
            logger.error("❌ 無法開始截圖，因為找不到電子書 iframe。")
            return

        page_num = 1
        successful_pages = 0
        failed_pages = []
        consecutive_failures = 0
        max_consecutive_failures = 3
        
        # 重置相同頁面計數器
        self.same_page_count = 0
        self.last_page_content = None

        while True:
            if total_pages is not None and page_num > total_pages:
                logger.info(f"📊 已達到指定的頁數限制 ({total_pages} 頁)")
                break
            
            print(f"\n進度: [第 {page_num} 頁]")
            
            # 截圖當前頁面
            if self.capture_page_with_retry(page_num, full_page=self.full_page_screenshot):
                successful_pages += 1
                consecutive_failures = 0
            else:
                failed_pages.append(page_num)
                consecutive_failures += 1
                logger.error(f"❌ 第 {page_num} 頁截圖失敗")
                
                # 如果連續失敗太多次，停止執行
                if consecutive_failures >= max_consecutive_failures:
                    logger.error(f"❌ 連續 {max_consecutive_failures} 頁截圖失敗，停止執行。")
                    break

            # 嘗試翻頁，如果失敗則結束
            if not self._try_next_page():
                # 再次確認是否真的無法翻頁
                if self.same_page_count >= 2:
                    logger.info(f"📚 確認已到達最後一頁（第 {page_num} 頁）")
                    print(f"\n📚 已到達電子書最後一頁（第 {page_num} 頁）")
                    break
                else:
                    logger.info(f"📊 無法繼續翻頁，可能已到達最後一頁")
                    break
            
            # 檢查是否內容重複（額外保護）
            if self.same_page_count >= 2:
                logger.warning(f"⚠️ 偵測到連續 {self.same_page_count} 次相同內容，停止截圖")
                print(f"\n⚠️ 偵測到重複內容，可能已到達最後一頁（第 {page_num} 頁）")
                break
            
            print(f"等待 {delay} 秒後截取下一頁...")
            time.sleep(delay)
            page_num += 1

        # 顯示結果摘要
        self._show_summary(successful_pages, failed_pages)

    def _try_next_page(self):
        """嘗試翻到下一頁 - 改進版，包含重複頁面檢測"""
        try:
            self.driver.switch_to.default_content()
            
            # 取得翻頁前的頁面內容（用於比較）
            before_content = self._get_page_content_hash()
            
            # 檢查並關閉彈出視窗
            self._close_popups()
            
            # 檢查頁碼顯示（如果有的話）
            current_page_text = self._get_current_page_number()
            
            # 博客來電子書專用翻頁按鈕選擇器
            next_buttons_xpaths = [
                "//button[@id='UiObj-book-right-btn']",
                "//button[contains(@class, 'viewer__body__pagination') and contains(@class, 'right')]",
                "//button[contains(@class, 'next')]",
                "//button[contains(@class, 'right')]",
                "//div[contains(@class, 'viewer-right')]",
                "//a[contains(@class, 'next')]",
                "//*[@aria-label='Next page']",
                "//*[@id='next-page']"
            ]
            
            next_button_clicked = False
            
            for xpath in next_buttons_xpaths:
                try:
                    next_btn = self.driver.find_element(By.XPATH, xpath)
                    if next_btn.is_displayed() and next_btn.is_enabled():
                        # 檢查按鈕是否被禁用（可能有 disabled 屬性或特定 class）
                        btn_classes = next_btn.get_attribute('class') or ''
                        if 'disabled' in btn_classes.lower() or 'inactive' in btn_classes.lower():
                            logger.info(f"⚠️ 翻頁按鈕已禁用，可能已到達最後一頁")
                            return False
                        
                        next_btn.click()
                        next_button_clicked = True
                        logger.info(f"✅ 成功點擊翻頁按鈕: {xpath}")
                        break
                except Exception:
                    continue
            
            if not next_button_clicked:
                # 如果都失敗，嘗試使用鍵盤
                try:
                    ActionChains(self.driver).send_keys(Keys.ARROW_RIGHT).perform()
                    logger.info("✅ 使用鍵盤右鍵翻頁")
                    next_button_clicked = True
                except Exception:
                    pass
            
            if not next_button_clicked:
                logger.warning("❌ 無法找到有效的翻頁按鈕")
                return False
            
            # 等待頁面載入
            time.sleep(1.5)
            
            # 取得翻頁後的頁面內容
            after_content = self._get_page_content_hash()
            
            # 檢查頁碼是否改變
            new_page_text = self._get_current_page_number()
            if current_page_text and new_page_text and current_page_text == new_page_text:
                logger.info(f"⚠️ 頁碼未改變 ({current_page_text})，可能已到達最後一頁")
                self.same_page_count += 1
                if self.same_page_count >= 2:
                    return False
            
            # 比較內容是否改變
            if before_content and after_content and before_content == after_content:
                self.same_page_count += 1
                logger.warning(f"⚠️ 頁面內容未改變 (連續 {self.same_page_count} 次)")
                
                # 如果連續2次內容相同，判定為已到達最後一頁
                if self.same_page_count >= 2:
                    logger.info("📚 偵測到已到達最後一頁（內容未改變）")
                    return False
            else:
                self.same_page_count = 0  # 重置計數器
                logger.info("✅ 頁面內容已更新")
            
            return True
            
        except Exception as e:
            logger.error(f"翻頁過程發生錯誤: {e}")
            return False
    
    def _get_page_content_hash(self):
        """取得當前頁面內容的雜湊值，用於比較頁面是否改變"""
        try:
            # 嘗試切換到 iframe
            if self.iframe_switched:
                # 取得 iframe 內的文字內容
                page_text = self.driver.find_element(By.TAG_NAME, "body").text
            else:
                # 如果不在 iframe 中，取得主頁面的內容
                self.driver.switch_to.default_content()
                page_text = self.driver.find_element(By.TAG_NAME, "body").text
            
            # 如果頁面文字太短，可能是空頁面
            if len(page_text) < 10:
                # 嘗試取得頁面的 HTML 結構
                page_html = self.driver.page_source
                return hash(page_html)
            
            # 返回文字內容的雜湊值
            return hash(page_text)
            
        except Exception as e:
            logger.debug(f"無法取得頁面內容雜湊: {e}")
            return None
    
    def _get_current_page_number(self):
        """嘗試取得當前頁碼顯示"""
        try:
            # 常見的頁碼顯示選擇器
            page_selectors = [
                "//div[contains(@class, 'page-number')]",
                "//span[contains(@class, 'page')]",
                "//div[contains(@class, 'pagination')]//span[@class='current']",
                "//*[contains(text(), '頁') and contains(text(), '/')]",
                "//input[@type='number' and contains(@class, 'page')]",
            ]
            
            for selector in page_selectors:
                try:
                    element = self.driver.find_element(By.XPATH, selector)
                    if element.is_displayed():
                        text = element.text or element.get_attribute('value')
                        if text:
                            logger.debug(f"找到頁碼顯示: {text}")
                            return text
                except:
                    continue
                    
        except Exception:
            pass
        
        return None

    def _close_popups(self):
        """關閉可能的彈出視窗 - 改進版"""
        popup_closed = False
        
        # 定義更精確的彈出視窗選擇器
        popup_selectors = [
            # 博客來特定的彈出視窗
            ("//div[@id='UiObj-model' and contains(@style, 'display: block')]", "UiObj-model (visible)"),
            ("//div[contains(@class, 'popup') and contains(@style, 'display: block')]", "popup (visible)"),
            ("//div[contains(@class, 'modal') and contains(@style, 'display: block')]", "modal (visible)"),
            ("//div[contains(@class, 'overlay') and contains(@style, 'display: block')]", "overlay (visible)"),
            # 試用到期提示
            ("//div[contains(@class, 'trial-expired')]", "trial-expired"),
            ("//div[contains(text(), '試用已到期')]", "試用到期文字"),
        ]
        
        for xpath, description in popup_selectors:
            try:
                popup_elements = self.driver.find_elements(By.XPATH, xpath)
                for popup in popup_elements:
                    if popup.is_displayed():
                        # 只在第一次發現時記錄警告
                        if self.popup_closed_count == 0:
                            logger.warning(f"⚠️ 偵測到遮擋元素: {description}")
                        
                        # 嘗試多種關閉方式
                        close_methods = [
                            # 方法1: 尋找關閉按鈕
                            (".//button[contains(@class, 'close')]", "關閉按鈕"),
                            (".//span[contains(@class, 'close')]", "關閉span"),
                            (".//*[contains(text(), '×')]", "×符號"),
                            (".//*[contains(text(), '關閉')]", "關閉文字"),
                            (".//button[contains(@class, 'btn-close')]", "btn-close"),
                            # 方法2: ESC鍵
                            (None, "ESC鍵"),
                        ]
                        
                        for close_xpath, method in close_methods:
                            try:
                                if close_xpath:
                                    close_btn = popup.find_element(By.XPATH, close_xpath)
                                    close_btn.click()
                                    logger.info(f"✅ 成功關閉遮擋元素 ({method})")
                                    self.popup_closed_count += 1
                                    popup_closed = True
                                    time.sleep(0.3)
                                    break
                                else:
                                    # 嘗試 ESC 鍵
                                    ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                                    time.sleep(0.3)
                                    # 檢查是否成功關閉
                                    if not popup.is_displayed():
                                        logger.info(f"✅ 成功使用 ESC 鍵關閉遮擋元素")
                                        self.popup_closed_count += 1
                                        popup_closed = True
                                        break
                            except Exception:
                                continue
                        
                        # 如果無法關閉，嘗試點擊背景
                        if not popup_closed:
                            try:
                                # 點擊彈出視窗外的區域
                                ActionChains(self.driver).move_by_offset(10, 10).click().perform()
                                time.sleep(0.3)
                                if not popup.is_displayed():
                                    logger.info("✅ 成功透過點擊背景關閉遮擋元素")
                                    self.popup_closed_count += 1
                                    popup_closed = True
                            except:
                                pass
            except Exception:
                continue
        
        # 如果有試用到期的提示，可能需要特殊處理
        if not popup_closed and self.popup_closed_count == 0:
            try:
                # 檢查是否有試用到期的訊息
                trial_messages = self.driver.find_elements(By.XPATH, 
                    "//div[contains(text(), '試用') or contains(text(), 'trial')]")
                if trial_messages:
                    logger.warning("⚠️ 可能遇到試用到期限制，請檢查帳號狀態")
            except:
                pass
        
        return popup_closed

    def _show_summary(self, successful_pages, failed_pages):
        """顯示截圖結果摘要"""
        print("\n" + "="*60)
        print("📊 截圖完成摘要")
        print("="*60)
        print(f"✅ 成功: {successful_pages} 頁")
        print(f"❌ 失敗: {len(failed_pages)} 頁")
        if failed_pages:
            print(f"失敗頁面: {failed_pages}")
        print(f"📁 檔案位置: {self.output_dir}")
        print("="*60)

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
            
            logger.info(f"📸 診斷快照已儲存: {png_path.name}, {html_path.name}")

        except Exception as e:
            logger.error(f"❌ 儲存診斷快照失敗 ({filename_prefix}): {e}")

    def close(self):
        """關閉瀏覽器"""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("瀏覽器已關閉")
            except Exception as e:
                logger.warning(f"關閉瀏覽器時出錯: {e}")