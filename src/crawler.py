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
        
        logger.setLevel(logging.INFO)
        
        self.driver = None
        self.wait = None
        self.output_dir = None
        self.iframe_switched = False
        self.tutorial_handled = False
        
        # 優化的狀態追蹤
        self.page_hashes = set()
        self.last_page_hash = None
        self.no_change_count = 0
        self.max_no_change = 5  # 減少等待次數
        
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
            options.page_load_strategy = 'eager'  # 改為 eager 加快載入
            
            if self.headless:
                options.add_argument('--headless')
            
            webdriver_path = self.config.get('webdriver_path')
            if webdriver_path and os.path.exists(webdriver_path):
                service = EdgeService(executable_path=webdriver_path)
            else:
                service = EdgeService()
            
            self.driver = webdriver.Edge(service=service, options=options)
            self.wait = WebDriverWait(self.driver, 10)
            self.driver.set_page_load_timeout(30)  # 縮短超時時間
            self.driver.implicitly_wait(3)  # 縮短隱式等待
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
            self.output_dir = None
            self.page_hashes.clear()
            self.last_page_hash = None
            self.no_change_count = 0
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
                        button = WebDriverWait(self.driver, 1).until(
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
                self.driver.find_elements(By.CSS_SELECTOR, "body > div, body > *")
                return True
            except:
                self.iframe_switched = False
        
        self.driver.switch_to.default_content()
        
        try:
            if not self.tutorial_handled:
                self.handle_tutorial()
                self.driver.switch_to.default_content()

            iframe_selectors = [
                "iframe[id^='epubjs-view-']",
                "iframe[enable-annotation='true']",
                "div.epub-container iframe",
            ]
            
            for selector in iframe_selectors:
                try:
                    self.wait.until(EC.frame_to_be_available_and_switch_to_it(
                        (By.CSS_SELECTOR, selector)))
                    
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

    def _wait_for_content_loaded(self, timeout=3):
        """快速等待頁面載入"""
        try:
            # 簡化載入檢查
            def has_content(driver):
                try:
                    body = driver.find_element(By.TAG_NAME, "body")
                    return len(body.text.strip()) > 10
                except:
                    return False
            
            WebDriverWait(self.driver, timeout).until(has_content)
            
            # 簡短延遲確保渲染完成
            time.sleep(0.2)
            return True
            
        except TimeoutException:
            return True

    def capture_page_with_retry(self, page_num, max_retries=2):
        """簡化的截圖函數"""
        for attempt in range(max_retries):
            try:
                # 確保在 iframe 中
                if not self.iframe_switched:
                    if not self.find_and_switch_to_ebook_iframe():
                        time.sleep(0.5)
                        continue
                
                # 快速等待載入
                self._wait_for_content_loaded()
                
                # 截圖
                screenshot_path = self.output_dir / f"page_{page_num:04d}.png"
                self.driver.save_screenshot(str(screenshot_path))
                
                # 簡單驗證
                if screenshot_path.exists() and screenshot_path.stat().st_size > 1024:
                    if self._is_valid_screenshot(screenshot_path):
                        # 更新頁面雜湊
                        current_hash = self._get_page_content_hash()
                        if current_hash:
                            self.page_hashes.add(current_hash)
                            self.last_page_hash = current_hash
                        return True
                    
                    screenshot_path.unlink()
                    self.iframe_switched = False
                    
                    if attempt == 0:
                        self.driver.refresh()
                        time.sleep(1)
                
            except Exception as e:
                logger.error(f"截圖失敗: {e}")
                self.iframe_switched = False
        
        return False

    def _is_valid_screenshot(self, screenshot_path):
        """快速驗證截圖"""
        try:
            img = Image.open(screenshot_path)
            img_array = np.array(img)
            avg_color = img_array.mean(axis=(0, 1))
            
            # 檢查灰色載入畫面
            if all(145 < c < 155 for c in avg_color[:3]):
                if img_array.std() < 15:
                    return False
            
            # 檢查純白或純黑
            if all(c > 250 for c in avg_color[:3]) or all(c < 5 for c in avg_color[:3]):
                if img_array.std() < 10:
                    return False
            
            return True
            
        except:
            return True

    def _get_page_content_hash(self):
        """取得頁面內容雜湊"""
        try:
            if self.iframe_switched:
                text = self.driver.find_element(By.TAG_NAME, "body").text
            else:
                self.driver.switch_to.default_content()
                text = self.driver.find_element(By.TAG_NAME, "body").text
            
            if text:
                return hashlib.md5(text.encode()).hexdigest()
        except:
            pass
        return None

    def _get_screenshot_hash_preview(self):
        """在截圖前預覽當前頁面內容的雜湊"""
        try:
            if self.iframe_switched:
                # 使用 JavaScript 取得頁面的視覺內容特徵
                visual_hash = self.driver.execute_script("""
                    var body = document.body;
                    var text = body.innerText || body.textContent || '';
                    var images = document.getElementsByTagName('img');
                    var imgData = '';
                    for(var i = 0; i < Math.min(images.length, 5); i++) {
                        imgData += images[i].src || '';
                    }
                    return text + imgData;
                """)
                if visual_hash:
                    return hashlib.md5(visual_hash.encode()).hexdigest()
        except:
            pass
        return None
    
    def _get_last_screenshot_hash(self, page_num):
        """取得最後一張截圖的雜湊值"""
        try:
            screenshot_path = self.output_dir / f"page_{page_num:04d}.png"
            if screenshot_path.exists():
                img = Image.open(screenshot_path)
                img_array = np.array(img)
                # 簡化圖片以減少細微差異的影響
                simplified = img_array[::10, ::10]  # 降採樣
                return hashlib.md5(simplified.tobytes()).hexdigest()
        except Exception as e:
            logger.error(f"無法取得截圖雜湊: {e}")
        return None

    def _get_screenshot_hash_preview(self):
        """在截圖前預覽當前頁面內容的雜湊"""
        try:
            if self.iframe_switched:
                # 使用 JavaScript 取得頁面的視覺內容特徵
                visual_hash = self.driver.execute_script("""
                    var body = document.body;
                    var text = body.innerText || body.textContent || '';
                    var images = document.getElementsByTagName('img');
                    var imgData = '';
                    for(var i = 0; i < Math.min(images.length, 5); i++) {
                        imgData += images[i].src || '';
                    }
                    return text + imgData;
                """)
                if visual_hash:
                    return hashlib.md5(visual_hash.encode()).hexdigest()
        except:
            pass
        return None
    
    def _get_last_screenshot_hash(self, page_num):
        """取得最後一張截圖的雜湊值"""
        try:
            screenshot_path = self.output_dir / f"page_{page_num:04d}.png"
            if screenshot_path.exists():
                img = Image.open(screenshot_path)
                img_array = np.array(img)
                # 簡化圖片以減少細微差異的影響
                simplified = img_array[::10, ::10]  # 降採樣
                return hashlib.md5(simplified.tobytes()).hexdigest()
        except Exception as e:
            logger.error(f"無法取得截圖雜湊: {e}")
        return None
        """檢查是否到達書籍結尾"""
        try:
            self.driver.switch_to.default_content()
            
            # 完成提示
            completion_indicators = [
                "//div[contains(text(), '本書已閱讀完畢')]",
                "//h2[contains(text(), '本書已閱讀完畢')]",
                "//button[contains(text(), '擁不為完讀')]",
            ]
            
            for xpath in completion_indicators:
                try:
                    element = self.driver.find_element(By.XPATH, xpath)
                    if element.is_displayed():
                        logger.info("📚 發現完成提示")
                        return True
                except:
                    pass
            
            # 檢查按鈕狀態
            try:
                next_btn = self.driver.find_element(By.ID, "UiObj-book-right-btn")
                if next_btn.get_attribute('disabled') == 'true':
                    return True
            except:
                pass
                
        except:
            pass
        
        return False

    def _check_book_completion(self):
        """檢查是否到達書籍結尾"""
        try:
            self.driver.switch_to.default_content()
            
            # 完成提示
            completion_indicators = [
                "//div[contains(text(), '本書已閱讀完畢')]",
                "//h2[contains(text(), '本書已閱讀完畢')]",
                "//button[contains(text(), '擁不為完讀')]",
            ]
            
            for xpath in completion_indicators:
                try:
                    element = self.driver.find_element(By.XPATH, xpath)
                    if element.is_displayed():
                        logger.info("📚 發現完成提示")
                        return True
                except:
                    pass
            
            # 檢查按鈕狀態
            try:
                next_btn = self.driver.find_element(By.ID, "UiObj-book-right-btn")
                if next_btn.get_attribute('disabled') == 'true':
                    return True
            except:
                pass
                
        except:
            pass
        
        return False

    def _try_next_page(self):
        """簡化的翻頁函數"""
        try:
            self.driver.switch_to.default_content()
            
            # 嘗試點擊翻頁按鈕
            try:
                next_btn = self.driver.find_element(By.ID, "UiObj-book-right-btn")
                if next_btn.is_displayed() and next_btn.is_enabled():
                    next_btn.click()
                    time.sleep(1)
                    self.iframe_switched = False
                    return True
            except:
                pass
            
            # 備用：鍵盤翻頁
            ActionChains(self.driver).send_keys(Keys.ARROW_RIGHT).perform()
            time.sleep(1)
            self.iframe_switched = False
            return True
            
        except Exception:
            return False

    def auto_capture_mode(self, total_pages=None, delay=1):
        """優化的自動截圖模式"""
        print("\n📸 自動截圖模式")
        print(f"⏱️ 每頁間隔 {delay} 秒\n")
        
        # 初始化
        if not self.find_and_switch_to_ebook_iframe():
            logger.error("無法開始截圖")
            return

        page_num = 1
        successful_pages = 0
        failed_pages = []
        
        self.page_hashes.clear()
        self.last_page_hash = None
        self.no_change_count = 0
        
        # 加強的重複頁面偵測
        last_screenshot_hash = None
        same_screenshot_count = 0
        max_same_screenshots = 3  # 連續3張相同截圖就停止
        
        while True:
            # 檢查頁數上限
            if total_pages and page_num > total_pages:
                print(f"\n📚 達到設定頁數上限 {total_pages}")
                break
            
            print(f"第 {page_num} 頁: ", end="")
            
            # 截圖前先取得當前頁面內容
            before_screenshot_hash = self._get_screenshot_hash_preview()
            
            # 截圖
            if self.capture_page_with_retry(page_num):
                successful_pages += 1
                print("✅")
                
                # 檢查截圖是否與上一張相同
                current_screenshot_hash = self._get_last_screenshot_hash(page_num)
                if current_screenshot_hash and current_screenshot_hash == last_screenshot_hash:
                    same_screenshot_count += 1
                    logger.warning(f"⚠️ 偵測到重複截圖 ({same_screenshot_count}/{max_same_screenshots})")
                    
                    if same_screenshot_count >= max_same_screenshots:
                        print(f"\n📚 連續{max_same_screenshots}張相同截圖，書籍可能已結束於第 {page_num - same_screenshot_count + 1} 頁")
                        # 刪除重複的截圖
                        for i in range(1, same_screenshot_count):
                            dup_path = self.output_dir / f"page_{page_num - i + 1:04d}.png"
                            if dup_path.exists():
                                dup_path.unlink()
                                logger.info(f"已刪除重複截圖: {dup_path.name}")
                        break
                else:
                    same_screenshot_count = 0
                    last_screenshot_hash = current_screenshot_hash
            else:
                failed_pages.append(page_num)
                print("❌")
            
            # 檢查完成狀態
            if self._check_book_completion():
                print(f"\n📚 書籍完成，共 {page_num} 頁")
                break
            
            # 記錄當前頁面雜湊
            before_hash = self.last_page_hash
            
            # 翻頁
            if not self._try_next_page():
                self.no_change_count += 1
                logger.info(f"翻頁失敗 ({self.no_change_count}/{self.max_no_change})")
                
                if self.no_change_count >= self.max_no_change:
                    print(f"\n📚 無法繼續翻頁，結束於第 {page_num} 頁")
                    break
                    
                # 重試翻頁
                time.sleep(1)
                ActionChains(self.driver).send_keys(Keys.PAGE_DOWN).perform()
                time.sleep(1)
            else:
                # 檢查頁面是否真的改變
                time.sleep(0.5)
                after_hash = self._get_page_content_hash()
                
                if after_hash and after_hash == before_hash:
                    self.no_change_count += 1
                    logger.info(f"頁面未變化 ({self.no_change_count}/{self.max_no_change})")
                    
                    if self.no_change_count >= self.max_no_change:
                        print(f"\n📚 連續{self.max_no_change}次頁面未變化，結束於第 {page_num} 頁")
                        break
                else:
                    self.no_change_count = 0
            
            # 延遲
            time.sleep(delay)
            page_num += 1
            
            # 安全上限
            if page_num > 500:
                print(f"\n⚠️ 達到安全上限 500 頁")
                break
        
        
        # 顯示結果
        actual_pages = len(list(self.output_dir.glob("*.png")))
        print(f"\n📊 截圖完成")
        print(f"✅ 成功: {actual_pages} 頁")
        if failed_pages:
            print(f"❌ 失敗: {len(failed_pages)} 頁")
            print(f"失敗頁面: {failed_pages[:20]}")
        print(f"📁 儲存位置: {self.output_dir}")

    def print_execution_summary(self):
        """輸出執行摘要"""
        if self.output_dir and self.output_dir.exists():
            screenshots = list(self.output_dir.glob("*.png"))
            if screenshots:
                print(f"\n📊 執行摘要：")
                print(f"   總共截取: {len(screenshots)} 張截圖")
                print(f"   儲存位置: {self.output_dir}")
                
                total_size = sum(f.stat().st_size for f in screenshots)
                print(f"   總檔案大小: {total_size / (1024*1024):.2f} MB")

    def close(self):
        """關閉瀏覽器"""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("瀏覽器已關閉")
            except Exception as e:
                logger.warning(f"關閉瀏覽器失敗: {e}")