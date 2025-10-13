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
        
        # 設定日誌級別為 INFO（移除 debug_mode 檢查）
        logger.setLevel(logging.INFO)
        
        self.driver = None
        self.wait = None
        self.output_dir = None
        self.iframe_switched = False
        self.tutorial_handled = False
        self.same_page_count = 0
        self.consecutive_empty_pages = 0
        self.last_page_hash = None
        self.page_hashes = set()  # 用於追蹤所有已見過的頁面
        self.book_completed = False  # 新增：標記書籍是否已完成
        
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
            self.last_page_hash = None
            self.page_hashes.clear()
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

    def _wait_for_content_loaded(self, timeout=8):
        """等待頁面內容完全載入（加速版）"""
        try:
            # 快速檢查是否還在載入狀態
            def not_loading(driver):
                try:
                    # 檢查常見的載入指示器
                    loading_indicators = [
                        "div.loading",
                        "div.spinner",
                        "*[class*='loading']"
                    ]
                    for selector in loading_indicators[:2]:  # 只檢查前兩個
                        elements = driver.find_elements(By.CSS_SELECTOR, selector)
                        for elem in elements:
                            if elem.is_displayed():
                                return False
                    return True
                except:
                    return True
            
            # 等待載入指示器消失（縮短時間）
            WebDriverWait(self.driver, 3).until(not_loading)
            
            # 等待文字內容出現
            def has_text_content(driver):
                try:
                    body = driver.find_element(By.TAG_NAME, "body")
                    text = body.text.strip()
                    # 確保有足夠的文字內容
                    return len(text) > 10
                except:
                    return False
            
            # 等待文字內容（縮短時間）
            WebDriverWait(self.driver, timeout).until(has_text_content)
            
            # 快速檢查背景色
            def not_gray_loading(driver):
                try:
                    body_color = driver.execute_script(
                        "return window.getComputedStyle(document.body).backgroundColor"
                    )
                    # 如果是典型的灰色載入背景，返回 False
                    if "rgb(150" in body_color or "rgb(151" in body_color:
                        return False
                    return True
                except:
                    return True
            
            # 等待非灰色載入畫面（縮短時間）
            WebDriverWait(self.driver, 2).until(not_gray_loading)
            
            # 簡化圖片載入檢查（只檢查前3張）
            def images_loaded(driver):
                images = driver.find_elements(By.TAG_NAME, "img")
                if images:
                    for img in images[:3]:  # 只檢查前3張圖片
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
            
            WebDriverWait(self.driver, 3).until(images_loaded)
            
            # 縮短額外等待時間
            time.sleep(0.3)
            return True
            
        except TimeoutException:
            # 如果超時，不再額外等待
            return True

    def capture_page_with_retry(self, page_num, max_retries=2):
        """截圖當前頁面（速度優化版）"""
        # 特定頁面需要刷新處理
        problem_pages = [8, 30, 52, 74, 84, 96]  # 已知的問題頁面
        if page_num in problem_pages:
            logger.info(f"第 {page_num} 頁需要刷新處理...")
            # 先等待一下讓頁面穩定
            time.sleep(1)
            # 刷新頁面兩次以確保載入
            self.driver.refresh()
            time.sleep(2)
            self.driver.refresh()
            time.sleep(2)
            self.iframe_switched = False  # 重置iframe狀態
            max_retries = 3  # 稍微增加重試次數
        
        for attempt in range(max_retries):
            try:
                # 檢查 WebDriver 是否還活著
                try:
                    self.driver.title
                except:
                    logger.error("WebDriver 連線已中斷")
                    return False
                
                # 檢查並切換 iframe
                if not self.iframe_switched:
                    if not self.find_and_switch_to_ebook_iframe():
                        self.driver.switch_to.default_content()
                        time.sleep(0.5)
                        continue
                
                # 等待內容載入（速度優化）
                wait_time = 8 if page_num in problem_pages else 5
                if not self._wait_for_content_loaded(timeout=wait_time):
                    self.iframe_switched = False
                    time.sleep(0.5)
                    continue
                
                # 執行截圖
                screenshot_path = self.output_dir / f"page_{page_num:04d}.png"
                self.driver.save_screenshot(str(screenshot_path))
                
                # 驗證截圖
                if screenshot_path.exists() and screenshot_path.stat().st_size > 1024:
                    # 先驗證是否為有效截圖
                    if not self._validate_screenshot(screenshot_path):
                        # 截圖無效，刪除並重試
                        screenshot_path.unlink()
                        self.iframe_switched = False
                        logger.warning(f"第 {page_num} 頁截圖無效（灰色畫面），重試中...")
                        
                        # 如果是第一次失敗，嘗試刷新
                        if attempt == 0:
                            logger.info(f"刷新第 {page_num} 頁...")
                            self.driver.refresh()
                            time.sleep(2)
                        else:
                            time.sleep(0.5)
                        
                        continue
                    
                    # 取得並儲存當前頁面雜湊
                    current_hash = self._get_page_content_hash()
                    if current_hash:
                        self.page_hashes.add(current_hash)
                        self.last_page_hash = current_hash
                    
                    self.consecutive_empty_pages = 0
                    return True
                
            except Exception as e:
                logger.error(f"截圖失敗: {e}")
                self.iframe_switched = False
                if attempt < max_retries - 1:
                    time.sleep(0.5)
        
        self.consecutive_empty_pages += 1
        return False
    
    def _check_book_completion(self):
        """檢查是否已到達書籍結尾"""
        try:
            self.driver.switch_to.default_content()
            
            # 檢查完成閱讀的彈窗（基於截圖中的實際內容）
            completion_indicators = [
                # 檢查彈窗標題
                "//div[contains(text(), '本書已閱讀完畢')]",
                "//h2[contains(text(), '本書已閱讀完畢')]",
                "//div[contains(@class, 'modal')]//div[contains(text(), '本書已閱讀完畢')]",
                # 檢查按鈕
                "//button[contains(text(), '擁不為完讀')]",
                "//button[text()='分享']",
                # 檢查彈窗內容
                "//div[contains(text(), '從中長跑、馬拉松、越野跑')]",
                # 檢查可見的modal
                "//div[contains(@class, 'modal') and contains(@style, 'display: block')]//div[contains(text(), '本書')]"
            ]
            
            for xpath in completion_indicators:
                try:
                    element = self.driver.find_element(By.XPATH, xpath)
                    if element.is_displayed():
                        logger.info("📚 發現「本書已閱讀完畢」提示，確認已到達最後一頁")
                        self.book_completed = True
                        return True
                except:
                    pass
            
            # 檢查右側翻頁按鈕是否被禁用
            try:
                next_btn = self.driver.find_element(By.ID, "UiObj-book-right-btn")
                if next_btn:
                    is_disabled = next_btn.get_attribute('disabled')
                    aria_disabled = next_btn.get_attribute('aria-disabled')
                    classes = next_btn.get_attribute('class') or ''
                    
                    if is_disabled == 'true' or aria_disabled == 'true' or 'disabled' in classes:
                        logger.info("翻頁按鈕已禁用，可能已到達最後")
                        return True
            except:
                pass
                
        except Exception as e:
            logger.debug(f"檢查完成狀態時發生錯誤: {e}")
        
        return False
    
    def _refresh_current_page(self):
        """重新載入當前頁面內容"""
        try:
            self.driver.switch_to.default_content()
            
            # 嘗試點擊重新載入按鈕（如果有）
            refresh_buttons = [
                "button.refresh",
                "button[title*='refresh']",
                "*[class*='refresh']"
            ]
            
            for selector in refresh_buttons:
                try:
                    btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if btn.is_displayed():
                        btn.click()
                        time.sleep(2)
                        return
                except:
                    pass
            
            # 使用 JavaScript 重新載入 iframe
            try:
                self.driver.execute_script("""
                    var iframe = document.querySelector('iframe[id^="epubjs-view-"]');
                    if (iframe) {
                        iframe.src = iframe.src;
                    }
                """)
                time.sleep(3)
            except:
                pass
                
        except Exception as e:
            logger.error(f"重新載入頁面失敗: {e}")
    
    def _check_duplicate_screenshot(self, screenshot_path, current_page):
        """檢查截圖是否與之前的重複"""
        try:
            current_img = Image.open(screenshot_path)
            
            # 只比較最近5張截圖，避免誤刪
            for i in range(max(1, current_page - 5), current_page):
                prev_path = self.output_dir / f"page_{i:04d}.png"
                if prev_path.exists():
                    prev_img = Image.open(prev_path)
                    
                    # 使用圖片雜湊值比較
                    if self._compare_image_hash(current_img, prev_img):
                        return True
            
            return False
            
        except Exception as e:
            logger.error(f"比較截圖失敗: {e}")
            return False
    
    def _compare_image_hash(self, img1, img2):
        """使用雜湊值比較兩張圖片是否相同"""
        try:
            # 確保圖片大小相同
            if img1.size != img2.size:
                return False
            
            # 轉換為相同模式
            img1 = img1.convert('RGB')
            img2 = img2.convert('RGB')
            
            # 計算圖片的雜湊值
            hash1 = hashlib.md5(img1.tobytes()).hexdigest()
            hash2 = hashlib.md5(img2.tobytes()).hexdigest()
            
            return hash1 == hash2
            
        except Exception:
            return False

    def _validate_screenshot(self, screenshot_path):
        """驗證截圖是否為有效內容"""
        try:
            img = Image.open(screenshot_path)
            img_array = np.array(img)
            
            # 計算平均顏色
            avg_color = img_array.mean(axis=(0, 1))
            
            # 檢查是否為灰色空白頁（RGB 值都在 140-160 之間）
            if all(145 < c < 155 for c in avg_color[:3]):
                # 計算標準差，檢查是否為單一顏色
                std_dev = img_array.std()
                if std_dev < 15:
                    logger.warning("偵測到灰色載入畫面")
                    return False
            
            # 檢查是否為純白頁面
            if all(c > 250 for c in avg_color[:3]):
                std_dev = img_array.std()
                if std_dev < 10:
                    logger.warning("偵測到純白空白頁面")
                    return False
            
            # 檢查是否為純黑頁面
            if all(c < 5 for c in avg_color[:3]):
                std_dev = img_array.std()
                if std_dev < 5:
                    logger.warning("偵測到純黑空白頁面")
                    return False
            
            # 檢查圖片中心區域是否有內容（放寬標準）
            height, width = img_array.shape[:2]
            center_region = img_array[height//4:3*height//4, width//4:3*width//4]
            center_std = center_region.std()
            
            # 放寬標準，只有當變化非常小時才判定為無內容
            if center_std < 5:
                # 再檢查整體圖片的變化
                overall_std = img_array.std()
                if overall_std < 8:
                    logger.warning("偵測到中心區域無內容")
                    return False
                    
            return True
            
        except Exception as e:
            logger.error(f"驗證截圖失敗: {e}")
            return True

    def _get_page_content_hash(self):
        """取得當前頁面內容的雜湊值"""
        try:
            if self.iframe_switched:
                page_text = self.driver.find_element(By.TAG_NAME, "body").text
            else:
                self.driver.switch_to.default_content()
                page_text = self.driver.find_element(By.TAG_NAME, "body").text
            
            if page_text:
                return hashlib.md5(page_text.encode()).hexdigest()
            return None
            
        except Exception:
            return None

    def auto_capture_mode(self, total_pages=None, delay=1):
        """自動截圖模式（極速優化版）"""
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
        
        self.same_page_count = 0
        self.consecutive_empty_pages = 0
        self.last_page_hash = None
        self.page_hashes.clear()
        self.book_completed = False
        
        # 用於追蹤是否到達最後
        no_change_count = 0
        max_no_change = 5  # 降低閾值，加快檢測
        last_successful_hash = None
        repeated_hash_count = 0

        while True:
            if total_pages and page_num > total_pages:
                break
            
            # 檢查是否已完成
            if self.book_completed:
                print(f"\n📚 書籍已完成！共 {page_num - 1} 頁")
                break
            
            print(f"進度: [第 {page_num} 頁]", end=" ")
            
            # 截圖當前頁面
            if self.capture_page_with_retry(page_num):
                successful_pages += 1
                print("✅")
                
                # 檢查是否有完成提示
                if self._check_book_completion():
                    print(f"\n📚 發現「本書已閱讀完畢」，共 {page_num} 頁")
                    break
                
                # 檢查重複內容
                current_hash = self.last_page_hash
                if current_hash == last_successful_hash:
                    repeated_hash_count += 1
                else:
                    repeated_hash_count = 0
                    last_successful_hash = current_hash
                    
            else:
                failed_pages.append(page_num)
                print("❌")

            # 嘗試翻頁
            page_changed = self._try_next_page()
            
            if not page_changed:
                no_change_count += 1
                
                # 檢查是否真的到達最後
                if no_change_count >= max_no_change:
                    # 最後確認
                    if self._check_book_completion():
                        print(f"\n📚 確認已到達最後一頁（第 {page_num} 頁）")
                        break
                    
                    # 嘗試強制翻頁
                    logger.info("嘗試強制翻頁...")
                    self._force_next_page()
                    time.sleep(1)
                    
                    if not self._try_next_page():
                        print(f"\n📚 無法繼續翻頁，已到達最後一頁（第 {page_num} 頁）")
                        break
                    else:
                        no_change_count = 0
                
            else:
                no_change_count = 0
            
            # 檢查重複內容（調整閾值避免過早停止）
            if repeated_hash_count >= 8:
                # 再次確認是否為最後
                if self._check_book_completion():
                    print(f"\n📚 確認已到達最後一頁（第 {page_num} 頁）")
                    break
                
                # 嘗試強制翻頁確認
                self._force_next_page()
                time.sleep(1)
                
                if not self._try_next_page():
                    print(f"\n📚 連續重複內容，確認已到達最後一頁（第 {page_num} 頁）")
                    break
                else:
                    repeated_hash_count = 5  # 降低但不歸零
            
            # 延遲（可以調整為0.5秒以更快）
            time.sleep(delay)
            page_num += 1
            
            # 安全上限
            if page_num > 1000:
                print(f"\n⚠️ 已達到安全上限（1000頁），停止截圖")
                break
        
        # 重試失敗的頁面
        if failed_pages:
            print(f"\n🔄 重試失敗的頁面: {failed_pages}")
            self._retry_failed_pages(failed_pages)

        # 顯示結果
        final_failed = len([p for p in failed_pages if not (self.output_dir / f"page_{p:04d}.png").exists()])
        print(f"\n📊 截圖完成")
        print(f"✅ 成功: {successful_pages} 頁")
        print(f"❌ 最終失敗: {final_failed} 頁")
        if final_failed > 0:
            missing_pages = [p for p in failed_pages if not (self.output_dir / f"page_{p:04d}.png").exists()]
            print(f"缺失頁面: {missing_pages[:20]}")
        print(f"📁 檔案位置: {self.output_dir}")
    
    def _retry_failed_pages(self, failed_pages):
        """重試失敗的頁面"""
        retry_success = []
        
        for page_num in failed_pages[:20]:  # 最多重試前20個失敗頁面
            # 檢查頁面是否已存在（可能在之後的處理中成功了）
            if (self.output_dir / f"page_{page_num:04d}.png").exists():
                retry_success.append(page_num)
                continue
            
            print(f"重試第 {page_num} 頁...", end=" ")
            
            # 給予更長的等待時間
            time.sleep(5)
            
            # 重新切換 iframe
            self.iframe_switched = False
            self.find_and_switch_to_ebook_iframe()
            
            # 重新嘗試截圖（給予更多重試次數）
            if self.capture_page_with_retry(page_num, max_retries=5):
                print("✅")
                retry_success.append(page_num)
            else:
                # 最後嘗試：重新載入並截圖
                print("最後嘗試...", end=" ")
                self._refresh_current_page()
                time.sleep(5)
                if self.capture_page_with_retry(page_num, max_retries=2):
                    print("✅")
                    retry_success.append(page_num)
                else:
                    print("❌")
        
        if retry_success:
            print(f"✅ 重試成功: {len(retry_success)} 頁")

    def _try_next_page(self):
        """嘗試翻到下一頁"""
        try:
            self.driver.switch_to.default_content()
            
            # 記錄翻頁前的雜湊
            before_hash = self.last_page_hash
            
            # 關閉彈窗
            self._close_popups()
            
            # 嘗試點擊翻頁按鈕
            next_clicked = False
            
            # 檢查是否有下一頁按鈕被禁用（表示已到最後）
            try:
                next_btn = self.driver.find_element(By.ID, "UiObj-book-right-btn")
                if next_btn:
                    classes = next_btn.get_attribute('class') or ''
                    is_disabled = next_btn.get_attribute('disabled')
                    
                    if is_disabled or 'disabled' in classes.lower():
                        logger.info("下一頁按鈕已禁用，可能已到達最後一頁")
                        return False
            except:
                pass
            
            next_buttons = [
                "//button[@id='UiObj-book-right-btn']",
                "//button[contains(@class, 'viewer__body__pagination') and contains(@class, 'right')]",
                "//button[contains(@class, 'next')]",
                "//a[contains(@class, 'next')]",
            ]
            
            for xpath in next_buttons:
                try:
                    btn = self.driver.find_element(By.XPATH, xpath)
                    if btn.is_displayed() and btn.is_enabled():
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
                # 嘗試點擊頁面右側區域
                try:
                    self.driver.execute_script("""
                        var event = new MouseEvent('click', {
                            view: window,
                            bubbles: true,
                            cancelable: true,
                            clientX: window.innerWidth - 50,
                            clientY: window.innerHeight / 2
                        });
                        document.body.dispatchEvent(event);
                    """)
                    next_clicked = True
                except:
                    pass
            
            if not next_clicked:
                return False
            
            # 等待新頁面載入
            time.sleep(2)
            
            # 重置 iframe 狀態，確保下一頁重新切換
            self.iframe_switched = False
            
            # 等待並檢查內容是否真的改變
            time.sleep(1)
            after_hash = self._get_page_content_hash()
            
            # 如果雜湊相同，可能還沒載入完成，再等一下
            if before_hash == after_hash:
                time.sleep(2)
                after_hash = self._get_page_content_hash()
            
            return before_hash != after_hash
            
        except Exception as e:
            logger.error(f"翻頁失敗: {e}")
            return False

    def _force_next_page(self):
        """強制翻頁（使用 JavaScript）"""
        try:
            self.driver.switch_to.default_content()
            
            # 嘗試使用 JavaScript 觸發翻頁
            scripts = [
                "document.querySelector('#UiObj-book-right-btn').click()",
                "document.querySelector('.viewer__body__pagination.right').click()",
                "window.dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowRight'}))",
            ]
            
            for script in scripts:
                try:
                    self.driver.execute_script(script)
                    time.sleep(1)
                    break
                except:
                    pass
                    
        except Exception:
            pass

    def _close_popups(self):
        """關閉彈出視窗"""
        # 先檢查是否有"本書已閱讀完畢"的彈窗
        try:
            # 檢查完成閱讀的彈窗（根據截圖內容）
            completion_selectors = [
                "//div[contains(text(), '本書已閱讀完畢')]",
                "//div[contains(text(), '本書已閱讀完單')]",  # 可能的變體
                "//button[contains(text(), '擁不為完讀')]",
                "//button[text()='分享']"
            ]
            
            for selector in completion_selectors:
                try:
                    element = self.driver.find_element(By.XPATH, selector)
                    if element.is_displayed():
                        logger.info("發現「本書已閱讀完畢」提示，書籍已讀完")
                        # 標記為已到達最後
                        self.book_completed = True
                        return
                except:
                    pass
        except:
            pass
        
        # 一般彈窗關閉邏輯
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

    def print_execution_summary(self):
        """輸出執行摘要"""
        if self.output_dir and self.output_dir.exists():
            screenshots = list(self.output_dir.glob("*.png"))
            if screenshots:
                print(f"\n📊 執行摘要：")
                print(f"   總共截取: {len(screenshots)} 張截圖")
                print(f"   儲存位置: {self.output_dir}")
                
                # 計算總檔案大小
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