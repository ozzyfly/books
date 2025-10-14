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
        
        # 設定日誌級別為 INFO
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
        self.book_completed = False  # 標記書籍是否已完成
        self.last_screenshot_hash = None  # 追蹤最後一張截圖的雜湊值
        
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
            self.last_screenshot_hash = None
            self.page_hashes.clear()
            self.book_completed = False
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
                    loading_indicators = [
                        "div.loading",
                        "div.spinner",
                        "*[class*='loading']"
                    ]
                    for selector in loading_indicators[:2]:
                        elements = driver.find_elements(By.CSS_SELECTOR, selector)
                        for elem in elements:
                            if elem.is_displayed():
                                return False
                    return True
                except:
                    return True
            
            WebDriverWait(self.driver, 3).until(not_loading)
            
            # 等待文字內容出現
            def has_text_content(driver):
                try:
                    body = driver.find_element(By.TAG_NAME, "body")
                    text = body.text.strip()
                    return len(text) > 10
                except:
                    return False
            
            WebDriverWait(self.driver, timeout).until(has_text_content)
            
            # 快速檢查背景色
            def not_gray_loading(driver):
                try:
                    body_color = driver.execute_script(
                        "return window.getComputedStyle(document.body).backgroundColor"
                    )
                    if "rgb(150" in body_color or "rgb(151" in body_color:
                        return False
                    return True
                except:
                    return True
            
            WebDriverWait(self.driver, 2).until(not_gray_loading)
            
            # 簡化圖片載入檢查
            def images_loaded(driver):
                images = driver.find_elements(By.TAG_NAME, "img")
                if images:
                    for img in images[:3]:
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
            
            time.sleep(0.3)
            return True
            
        except TimeoutException:
            return True

    def capture_page_with_retry(self, page_num, max_retries=2):
        """截圖當前頁面（速度優化版）"""
        problem_pages = [8, 30, 52, 74, 84, 96]
        if page_num in problem_pages:
            logger.info(f"第 {page_num} 頁需要刷新處理...")
            time.sleep(1)
            self.driver.refresh()
            time.sleep(2)
            self.driver.refresh()
            time.sleep(2)
            self.iframe_switched = False
            max_retries = 3
        
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
                
                # 等待內容載入
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
                    if not self._validate_screenshot(screenshot_path):
                        screenshot_path.unlink()
                        self.iframe_switched = False
                        logger.warning(f"第 {page_num} 頁截圖無效（灰色畫面），重試中...")
                        
                        if attempt == 0:
                            logger.info(f"刷新第 {page_num} 頁...")
                            self.driver.refresh()
                            time.sleep(2)
                        else:
                            time.sleep(0.5)
                        
                        continue
                    
                    # 儲存截圖雜湊值
                    img = Image.open(screenshot_path)
                    img_hash = hashlib.md5(img.tobytes()).hexdigest()
                    self.last_screenshot_hash = img_hash
                    
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
            
            # 檢查完成閱讀的彈窗
            completion_indicators = [
                "//div[contains(text(), '本書已閱讀完畢')]",
                "//h2[contains(text(), '本書已閱讀完畢')]",
                "//div[contains(@class, 'modal')]//div[contains(text(), '本書已閱讀完畢')]",
                "//button[contains(text(), '擁不為完讀')]",
                "//button[text()='分享']",
                "//div[contains(text(), '從中長跑、馬拉松、越野跑')]",
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

    def _validate_screenshot(self, screenshot_path):
        """驗證截圖是否為有效內容"""
        try:
            img = Image.open(screenshot_path)
            img_array = np.array(img)
            
            # 計算平均顏色
            avg_color = img_array.mean(axis=(0, 1))
            
            # 檢查是否為灰色空白頁
            if all(145 < c < 155 for c in avg_color[:3]):
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
            
            # 檢查圖片中心區域是否有內容
            height, width = img_array.shape[:2]
            center_region = img_array[height//4:3*height//4, width//4:3*width//4]
            center_std = center_region.std()
            
            if center_std < 5:
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
        """自動截圖模式（改良版）"""
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
        self.last_screenshot_hash = None
        self.page_hashes.clear()
        self.book_completed = False
        
        # 用於追蹤翻頁失敗
        consecutive_no_change = 0
        max_consecutive_no_change = 10  # 提高閾值，避免過早停止
        
        # 用於追蹤重複截圖
        same_screenshot_count = 0
        last_successful_screenshot_hash = None

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
                
                # 檢查截圖是否重複
                if self.last_screenshot_hash == last_successful_screenshot_hash:
                    same_screenshot_count += 1
                    logger.debug(f"偵測到重複截圖（第 {same_screenshot_count} 次）")
                else:
                    same_screenshot_count = 0
                    last_successful_screenshot_hash = self.last_screenshot_hash
                
                # 檢查是否有完成提示
                if self._check_book_completion():
                    print(f"\n📚 發現「本書已閱讀完畢」，共 {page_num} 頁")
                    break
                    
            else:
                failed_pages.append(page_num)
                print("❌")

            # 嘗試翻頁
            before_hash = self.last_page_hash
            page_changed = self._try_next_page()
            
            if not page_changed:
                consecutive_no_change += 1
                logger.info(f"翻頁無變化（第 {consecutive_no_change} 次）")
                
                # 多次嘗試翻頁
                if consecutive_no_change == 3:
                    logger.info("嘗試使用鍵盤翻頁...")
                    self._keyboard_next_page()
                    time.sleep(2)
                elif consecutive_no_change == 5:
                    logger.info("嘗試強制翻頁...")
                    self._force_next_page()
                    time.sleep(2)
                elif consecutive_no_change == 7:
                    logger.info("嘗試點擊頁面右側...")
                    self._click_page_right()
                    time.sleep(2)
                
                # 檢查翻頁後是否有變化
                after_hash = self._get_page_content_hash()
                if after_hash and after_hash != before_hash:
                    consecutive_no_change = 0
                    logger.info("翻頁成功！")
                elif consecutive_no_change >= max_consecutive_no_change:
                    # 最後確認是否真的到達最後
                    if self._check_book_completion():
                        print(f"\n📚 確認已到達最後一頁（第 {page_num} 頁）")
                        break
                    
                    # 再次強力嘗試
                    logger.info("最後嘗試翻頁...")
                    self._aggressive_next_page()
                    time.sleep(3)
                    
                    final_hash = self._get_page_content_hash()
                    if final_hash == after_hash:
                        print(f"\n📚 無法繼續翻頁，已到達最後一頁（第 {page_num} 頁）")
                        break
                    else:
                        consecutive_no_change = 0
            else:
                consecutive_no_change = 0
            
            # 檢查重複截圖（提高閾值）
            if same_screenshot_count >= 15:
                logger.warning(f"連續 {same_screenshot_count} 張相同截圖")
                
                # 嘗試強制翻頁
                self._aggressive_next_page()
                time.sleep(3)
                
                if not self._try_next_page():
                    if self._check_book_completion():
                        print(f"\n📚 確認已到達最後一頁（第 {page_num} 頁）")
                        break
                    
                    print(f"\n📚 連續重複內容，可能已到達最後一頁（第 {page_num} 頁）")
                    break
                else:
                    same_screenshot_count = 10  # 降低但不歸零
            
            # 延遲
            time.sleep(delay)
            page_num += 1
            
            # 安全上限
            if page_num > 500:
                print(f"\n⚠️ 已達到安全上限（1000頁），停止截圖")
                break
        
        # 重試失敗的頁面
        if failed_pages:
            print(f"\n🔄 重試失敗的頁面: {failed_pages[:10]}...")
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

    def _try_next_page(self):
        """嘗試翻到下一頁"""
        try:
            self.driver.switch_to.default_content()
            
            # 關閉彈窗
            self._close_popups()
            
            # 檢查是否有下一頁按鈕被禁用
            try:
                next_btn = self.driver.find_element(By.ID, "UiObj-book-right-btn")
                if next_btn:
                    is_disabled = next_btn.get_attribute('disabled')
                    
                    # 不要因為按鈕狀態就直接返回 False
                    # 因為有時候按鈕狀態不準確
                    if is_disabled == 'true':
                        logger.debug("下一頁按鈕顯示為禁用狀態")
            except:
                pass
            
            # 嘗試點擊翻頁按鈕
            next_clicked = False
            
            next_buttons = [
                "//button[@id='UiObj-book-right-btn']",
                "//button[contains(@class, 'viewer__body__pagination') and contains(@class, 'right')]",
                "//button[contains(@class, 'next')]",
                "//a[contains(@class, 'next')]",
            ]
            
            for xpath in next_buttons:
                try:
                    btn = self.driver.find_element(By.XPATH, xpath)
                    if btn.is_displayed():
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
            
            # 等待新頁面載入
            time.sleep(2)
            
            # 重置 iframe 狀態，這很重要！
            self.iframe_switched = False
            
            # 翻頁動作已執行，假設成功
            # 不再檢查內容是否改變，因為這個檢查不可靠
            return True
            
        except Exception as e:
            logger.error(f"翻頁失敗: {e}")
            return False

    def _keyboard_next_page(self):
        """使用鍵盤翻頁"""
        try:
            self.driver.switch_to.default_content()
            ActionChains(self.driver).send_keys(Keys.ARROW_RIGHT).perform()
            time.sleep(1)
            ActionChains(self.driver).send_keys(Keys.PAGE_DOWN).perform()
        except:
            pass

    def _click_page_right(self):
        """點擊頁面右側區域"""
        try:
            self.driver.switch_to.default_content()
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
        except:
            pass

    def _force_next_page(self):
        """強制翻頁（使用 JavaScript）"""
        try:
            self.driver.switch_to.default_content()
            
            scripts = [
                "document.querySelector('#UiObj-book-right-btn').click()",
                "document.querySelector('.viewer__body__pagination.right').click()",
                "window.dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowRight'}))",
                "document.querySelector('[aria-label=\"next\"]').click()",
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

    def _aggressive_next_page(self):
        """積極嘗試翻頁（組合多種方法）"""
        try:
            self.driver.switch_to.default_content()
            
            # 1. 先嘗試按 ESC 關閉任何可能的彈窗
            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            time.sleep(0.5)
            
            # 2. 嘗試多種鍵盤組合
            key_combinations = [
                Keys.ARROW_RIGHT,
                Keys.PAGE_DOWN,
                Keys.SPACE,
                'd',  # 有些閱讀器用 d 鍵
                'n',  # 有些用 n 表示 next
            ]
            
            for key in key_combinations:
                ActionChains(self.driver).send_keys(key).perform()
                time.sleep(0.3)
            
            # 3. 嘗試點擊多個位置
            click_positions = [
                (0.9, 0.5),  # 右側中間
                (0.95, 0.5), # 更右側
                (0.8, 0.8),  # 右下角
                (0.5, 0.9),  # 底部中間
            ]
            
            for x_ratio, y_ratio in click_positions:
                try:
                    self.driver.execute_script(f"""
                        var event = new MouseEvent('click', {{
                            view: window,
                            bubbles: true,
                            cancelable: true,
                            clientX: window.innerWidth * {x_ratio},
                            clientY: window.innerHeight * {y_ratio}
                        }});
                        document.body.dispatchEvent(event);
                    """)
                    time.sleep(0.3)
                except:
                    pass
            
        except Exception:
            pass

    def _retry_failed_pages(self, failed_pages):
        """重試失敗的頁面"""
        retry_success = []
        
        for page_num in failed_pages[:20]:
            if (self.output_dir / f"page_{page_num:04d}.png").exists():
                retry_success.append(page_num)
                continue
            
            print(f"重試第 {page_num} 頁...", end=" ")
            
            time.sleep(5)
            
            self.iframe_switched = False
            self.find_and_switch_to_ebook_iframe()
            
            if self.capture_page_with_retry(page_num, max_retries=5):
                print("✅")
                retry_success.append(page_num)
            else:
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

    def _refresh_current_page(self):
        """重新載入當前頁面內容"""
        try:
            self.driver.switch_to.default_content()
            
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

    def _close_popups(self):
        """關閉彈出視窗"""
        try:
            # 檢查完成閱讀的彈窗
            completion_selectors = [
                "//div[contains(text(), '本書已閱讀完畢')]",
                "//button[contains(text(), '擁不為完讀')]",
                "//button[text()='分享']"
            ]
            
            for selector in completion_selectors:
                try:
                    element = self.driver.find_element(By.XPATH, selector)
                    if element.is_displayed():
                        logger.info("發現「本書已閱讀完畢」提示，書籍已讀完")
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