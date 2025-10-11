#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import logging
import hashlib
from pathlib import Path
from datetime import datetime
from PIL import Image
import numpy as np

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.edge.service import Service as EdgeService

logger = logging.getLogger(__name__)


class BooksCrawler:
    def __init__(self, config):
        self.config = config
        self.email = config.get('email')
        self.password = config.get('password')
        self.headless = config.get('headless', False)
        
        # 設定日誌級別
        log_level = logging.INFO if not config.get('debug_mode', False) else logging.DEBUG
        logger.setLevel(log_level)
        
        self.driver = None
        self.wait = None
        self.output_dir = None
        self.iframe_switched = False
        self.tutorial_handled = False
        self.same_page_count = 0
        self.consecutive_empty_pages = 0
        
        self.setup_driver()

    def setup_driver(self):
        """啟動 Edge WebDriver"""
        try:
            options = webdriver.EdgeOptions()
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-gpu')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.page_load_strategy = 'normal'
            
            if self.headless:
                options.add_argument('--headless')
            
            webdriver_path = self.config.get('webdriver_path')
            if webdriver_path and os.path.exists(webdriver_path):
                service = EdgeService(executable_path=webdriver_path)
            else:
                service = EdgeService()
            
            self.driver = webdriver.Edge(service=service, options=options)
            self.wait = WebDriverWait(self.driver, 10)
            self.driver.set_page_load_timeout(60)
            self.driver.implicitly_wait(5)
            logger.info("✅ WebDriver 啟動成功")
            
        except Exception as e:
            logger.error(f"❌ WebDriver 啟動失敗: {e}")
            raise

    def login(self, auto_captcha=False):
        """執行登入流程"""
        logger.info("開始登入流程...")
        self.driver.get("https://www.books.com.tw/")

        try:
            # 處理彈出視窗
            self._handle_popups()

            # 點擊會員登入
            if not self._click_login_link():
                return False

            # 填寫帳號密碼
            if not self._fill_username() or not self._fill_password():
                return False

            # 點擊登入按鈕
            if not self._click_login_button():
                return False

            # 等待手動驗證
            if not auto_captcha:
                print("\n請在瀏覽器中完成 CAPTCHA 驗證，完成後按 Enter 繼續...")
                input()
            
            return True

        except Exception as e:
            logger.error(f"登入失敗: {e}")
            return False

    def _handle_popups(self):
        """處理彈出視窗"""
        try:
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
                    break
                except:
                    continue
        except:
            pass

    def _click_login_link(self):
        """點擊會員登入連結"""
        selectors = [
            (By.CSS_SELECTOR, "span.member_class_name"),
            (By.LINK_TEXT, "會員登入"),
            (By.XPATH, "//span[contains(text(), '會員登入')]")
        ]
        for by, value in selectors:
            try:
                login_link = self.driver.find_element(by, value)
                login_link.click()
                return True
            except:
                continue
        return False

    def _fill_username(self):
        """填寫使用者名稱"""
        selectors = [
            (By.ID, "login_id_width01"),
            (By.NAME, "login_id"),
            (By.CSS_SELECTOR, "input[type='text']")
        ]
        
        for by, value in selectors:
            try:
                username_input = self.driver.find_element(by, value)
                username_input.clear()
                username_input.send_keys(self.email)
                return True
            except:
                continue
        return False

    def _fill_password(self):
        """填寫密碼"""
        selectors = [
            (By.ID, "login_pswd"),
            (By.NAME, "login_pswd"),
            (By.CSS_SELECTOR, "input[type='password']")
        ]
        
        for by, value in selectors:
            try:
                password_input = self.driver.find_element(by, value)
                password_input.clear()
                password_input.send_keys(self.password)
                return True
            except:
                continue
        return False

    def _click_login_button(self):
        """點擊登入按鈕"""
        selectors = [
            (By.ID, "show-captcha"),
            (By.ID, "login_btn"),
            (By.CSS_SELECTOR, "button[type='submit']"),
            (By.XPATH, "//button[contains(text(), '登入')]")
        ]
        
        for by, value in selectors:
            try:
                login_button = self.driver.find_element(by, value)
                login_button.click()
                return True
            except:
                continue
        return False

    def navigate_to_book(self, book_url):
        """導航到電子書頁面"""
        if self.output_dir is not None:
            self.reset_for_next_book()
        
        logger.info(f"前往: {book_url}")
        self.driver.get(book_url)

        # 等待頁面載入
        try:
            self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "iframe[id^='epubjs-view-']"))
            )
        except:
            logger.warning("等待 iframe 超時")

        # 建立輸出目錄
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_dir = Path(f"output/ebook_{timestamp}")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"輸出目錄: {self.output_dir}")

    def reset_for_next_book(self):
        """重置狀態以處理下一本電子書"""
        try:
            self.driver.switch_to.default_content()
            self.iframe_switched = False
            self.tutorial_handled = False
            self.same_page_count = 0
            self.output_dir = None
            self.consecutive_empty_pages = 0
        except Exception as e:
            logger.error(f"重置狀態失敗: {e}")

    def handle_tutorial(self):
        """處理教學引導畫面"""
        if self.tutorial_handled:
            return
        
        try:
            self.driver.switch_to.default_content()
            
            selectors = [
                (By.ID, "UIObj-demo-next-btn"),
                (By.CSS_SELECTOR, ".tutorial-next-button"),
                (By.XPATH, "//button[contains(text(), '下一步')]"),
            ]
            
            for _ in range(10):
                clicked = False
                for by, value in selectors:
                    try:
                        button = WebDriverWait(self.driver, 2).until(
                            EC.element_to_be_clickable((by, value))
                        )
                        button.click()
                        time.sleep(0.1)
                        clicked = True
                        break
                    except:
                        continue
                
                if not clicked:
                    break
            
            self.tutorial_handled = True

        except Exception as e:
            logger.warning(f"處理教學引導失敗: {e}")

    def find_and_switch_to_ebook_iframe(self):
        """切換到電子書 iframe"""
        if self.iframe_switched:
            try:
                # 檢查是否仍在 iframe 中
                self.driver.find_elements(By.CSS_SELECTOR, "body > div, body > *")
                return True
            except:
                self.iframe_switched = False
        
        self.driver.switch_to.default_content()
        
        try:
            # 處理教學引導
            if not self.tutorial_handled:
                self.handle_tutorial()
                self.driver.switch_to.default_content()

            # 嘗試切換 iframe
            iframe_selectors = [
                "iframe[id^='epubjs-view-']",
                "iframe[enable-annotation='true']",
                "div.epub-container iframe",
                "iframe",
            ]
            
            for selector in iframe_selectors:
                try:
                    self.wait.until(EC.frame_to_be_available_and_switch_to_it(
                        (By.CSS_SELECTOR, selector)))
                    
                    # 驗證切換成功
                    self.wait.until(EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "body > div, body > *")))
                    
                    self.iframe_switched = True
                    return True
                    
                except TimeoutException:
                    self.driver.switch_to.default_content()
            
            return False
            
        except Exception as e:
            logger.error(f"切換 iframe 失敗: {e}")
            return False

    def capture_page_with_retry(self, page_num, max_retries=3):
        """截圖當前頁面"""
        for attempt in range(max_retries):
            try:
                # 檢查並切換 iframe
                if not self.iframe_switched:
                    if not self.find_and_switch_to_ebook_iframe():
                        self.driver.switch_to.default_content()
                        continue
                
                # 等待內容載入
                time.sleep(2)
                self._wait_for_images_loaded(timeout=10)
                
                # 執行截圖
                screenshot_path = self.output_dir / f"page_{page_num:04d}.png"
                self.driver.save_screenshot(str(screenshot_path))
                
                # 驗證截圖
                if screenshot_path.exists() and screenshot_path.stat().st_size > 1024:
                    if self._validate_screenshot(screenshot_path):
                        # 檢查是否與前一張相同
                        if page_num > 1:
                            prev_path = self.output_dir / f"page_{page_num-1:04d}.png"
                            if prev_path.exists() and self._compare_screenshots(str(prev_path), str(screenshot_path)):
                                self.same_page_count += 1
                            else:
                                self.same_page_count = 0
                        
                        self.consecutive_empty_pages = 0
                        return True
                    else:
                        screenshot_path.unlink()
                        self.iframe_switched = False
                
            except Exception as e:
                logger.error(f"截圖失敗: {e}")
                self.iframe_switched = False
                time.sleep(1)
        
        self.consecutive_empty_pages += 1
        return False

    def _wait_for_images_loaded(self, timeout=10):
        """等待圖片載入"""
        try:
            def images_loaded(driver):
                images = driver.find_elements(By.TAG_NAME, "img")
                if not images:
                    return False
                    
                for img in images:
                    try:
                        src = img.get_attribute("src")
                        if not src:
                            continue
                            
                        complete = driver.execute_script(
                            "return arguments[0].complete && "
                            "typeof arguments[0].naturalWidth != 'undefined' && "
                            "arguments[0].naturalWidth > 0",
                            img
                        )
                        if not complete:
                            return False
                    except:
                        continue
                        
                return True
                
            WebDriverWait(self.driver, timeout).until(images_loaded)
            return True
            
        except TimeoutException:
            return False

    def _validate_screenshot(self, screenshot_path):
        """驗證截圖是否為有效內容"""
        try:
            img = Image.open(screenshot_path)
            img_array = np.array(img)
            avg_color = img_array.mean(axis=(0, 1))
            
            # 檢查是否為灰色空白頁
            if all(140 < c < 160 for c in avg_color[:3]):
                std_dev = img_array.std()
                if std_dev < 10:
                    return False
                    
            return True
            
        except Exception:
            return True

    def _compare_screenshots(self, path1, path2):
        """比較兩張截圖是否相同"""
        try:
            img1 = Image.open(path1).convert('RGB')
            img2 = Image.open(path2).convert('RGB')
            
            if img1.size != img2.size:
                return False
            
            # 快速抽樣比較
            import random
            random.seed(42)
            
            width, height = img1.size
            sample_points = min(1000, width * height // 100)
            
            differences = 0
            for _ in range(sample_points):
                x = random.randint(0, width - 1)
                y = random.randint(0, height - 1)
                
                pixel1 = img1.getpixel((x, y))
                pixel2 = img2.getpixel((x, y))
                
                if any(abs(p1 - p2) > 5 for p1, p2 in zip(pixel1, pixel2)):
                    differences += 1
            
            similarity = 1 - (differences / sample_points)
            return similarity > 0.99
            
        except Exception:
            return False

    def auto_capture_mode(self, total_pages=None, delay=5):
        """自動截圖模式"""
        print("\n📸 自動截圖模式")
        print(f"⏱️ 每頁間隔 {delay} 秒")
        print("📚 將自動偵測最後一頁並停止\n")
        
        # 確保已切換到 iframe
        if not self.find_and_switch_to_ebook_iframe():
            logger.error("無法開始截圖，找不到 iframe")
            return

        page_num = 1
        successful_pages = 0
        failed_pages = []
        consecutive_failures = 0
        max_consecutive_failures = 5
        
        self.same_page_count = 0
        self.consecutive_empty_pages = 0

        while True:
            if total_pages and page_num > total_pages:
                break
            
            print(f"進度: [第 {page_num} 頁]")
            
            # 截圖當前頁面
            if self.capture_page_with_retry(page_num):
                successful_pages += 1
                consecutive_failures = 0
            else:
                failed_pages.append(page_num)
                consecutive_failures += 1
                
                if consecutive_failures >= max_consecutive_failures:
                    if successful_pages > 100:
                        logger.info("可能已到達最後幾頁")
                        break
                    else:
                        break

            # 嘗試翻頁
            if not self._try_next_page():
                if self.same_page_count >= 2:
                    print(f"\n📚 已到達最後一頁（第 {page_num} 頁）")
                    break
                else:
                    break
            
            # 檢查重複內容
            if self.same_page_count >= 2:
                print(f"\n⚠️ 偵測到重複內容，可能已到達最後一頁")
                break
            
            time.sleep(delay)
            page_num += 1

        # 顯示結果
        print(f"\n📊 截圖完成")
        print(f"✅ 成功: {successful_pages} 頁")
        print(f"❌ 失敗: {len(failed_pages)} 頁")
        if failed_pages:
            print(f"失敗頁面: {failed_pages}")
        print(f"📁 檔案位置: {self.output_dir}")

    def _try_next_page(self):
        """嘗試翻到下一頁"""
        try:
            self.driver.switch_to.default_content()
            
            # 記錄翻頁前的內容
            before_hash = self._get_page_content_hash()
            
            # 關閉彈窗
            self._close_popups()
            
            # 嘗試點擊翻頁按鈕
            next_clicked = False
            next_buttons = [
                "//button[@id='UiObj-book-right-btn']",
                "//button[contains(@class, 'viewer__body__pagination') and contains(@class, 'right')]",
                "//button[contains(@class, 'next')]",
            ]
            
            for xpath in next_buttons:
                try:
                    btn = self.driver.find_element(By.XPATH, xpath)
                    if btn.is_displayed() and btn.is_enabled():
                        classes = btn.get_attribute('class') or ''
                        if 'disabled' not in classes.lower():
                            btn.click()
                            next_clicked = True
                            break
                except:
                    pass
            
            if not next_clicked:
                # 嘗試鍵盤翻頁
                try:
                    ActionChains(self.driver).send_keys(Keys.ARROW_RIGHT).perform()
                    next_clicked = True
                except:
                    pass
            
            if not next_clicked:
                return False
            
            time.sleep(2)
            
            # 檢查內容是否改變
            after_hash = self._get_page_content_hash()
            
            if before_hash and after_hash and before_hash == after_hash:
                self.same_page_count += 1
                if self.same_page_count >= 2:
                    return False
            else:
                self.same_page_count = 0
            
            return True
            
        except Exception as e:
            logger.error(f"翻頁失敗: {e}")
            return False

    def _get_page_content_hash(self):
        """取得當前頁面內容的雜湊值"""
        try:
            if self.iframe_switched:
                page_text = self.driver.find_element(By.TAG_NAME, "body").text
            else:
                self.driver.switch_to.default_content()
                page_text = self.driver.find_element(By.TAG_NAME, "body").text
            
            return hashlib.md5(page_text.encode()).hexdigest()
            
        except Exception:
            return None

    def _close_popups(self):
        """關閉彈出視窗"""
        popup_selectors = [
            ("//div[@id='UiObj-model' and contains(@style, 'display: block')]", ".//button[contains(@class, 'close')]"),
            ("//div[contains(@class, 'popup') and contains(@style, 'display: block')]", ".//button[contains(@class, 'close')]"),
            ("//div[contains(@class, 'modal') and contains(@style, 'display: block')]", ".//button[contains(@class, 'close')]"),
        ]
        
        for popup_xpath, close_xpath in popup_selectors:
            try:
                popup = self.driver.find_element(By.XPATH, popup_xpath)
                if popup.is_displayed():
                    try:
                        close_btn = popup.find_element(By.XPATH, close_xpath)
                        close_btn.click()
                        time.sleep(0.3)
                    except:
                        # 嘗試 ESC 鍵
                        ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                        time.sleep(0.3)
            except:
                continue

    def close(self):
        """關閉瀏覽器"""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("瀏覽器已關閉")
            except Exception as e:
                logger.warning(f"關閉瀏覽器失敗: {e}")