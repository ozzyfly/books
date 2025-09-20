#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import threading
import logging
import platform
import json
import hashlib
from pathlib import Path
from datetime import datetime
from PIL import Image
import numpy as np

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
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
        self.email = self.config.get('email')
        self.password = self.config.get('password')
        self.headless = self.config.get('headless', False)
        
        # 設定詳細日誌級別
        self.debug_mode = config.get('debug_mode', True)
        if self.debug_mode:
            logging.getLogger().setLevel(logging.DEBUG)
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.WARNING)
        
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
        self.consecutive_empty_pages = 0  # 追蹤連續空白頁數
        
        # 加入執行追蹤
        self.execution_trace = []
        self.page_capture_history = {}  # 記錄每頁的截圖歷史
        self.page_content_hashes = {}  # 記錄每頁的內容雜湊值
        
        logger.info("="*60)
        logger.info("🔍 啟動詳細日誌追蹤模式 v2.2")
        logger.info(f"📅 時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("="*60)
        
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
            
            # 增加圖片載入等待時間
            options.page_load_strategy = 'normal'  # 確保頁面完全載入
            
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
            self.wait = WebDriverWait(self.driver, 10)  # 增加等待時間
            self.driver.set_page_load_timeout(60)
            self.driver.implicitly_wait(5)  # 增加隱式等待
            logger.info("✅ Edge WebDriver 啟動成功")
            
        except Exception as e:
            logger.error(f"❌ Edge WebDriver 啟動失敗: {e}")
            raise

    def wait_for_images_loaded(self, timeout=10):
        """等待圖片載入完成"""
        try:
            def images_loaded(driver):
                # 檢查所有圖片是否載入完成
                images = driver.find_elements(By.TAG_NAME, "img")
                if not images:
                    return False
                    
                for img in images:
                    try:
                        # 檢查圖片是否有 src 屬性
                        src = img.get_attribute("src")
                        if not src:
                            continue
                            
                        # 使用 JavaScript 檢查圖片載入狀態
                        complete = driver.execute_script(
                            "return arguments[0].complete && "
                            "typeof arguments[0].naturalWidth != 'undefined' && "
                            "arguments[0].naturalWidth > 0",
                            img
                        )
                        if not complete:
                            logger.debug(f"圖片尚未載入完成: {src[:50]}...")
                            return False
                    except:
                        continue
                        
                return True
                
            WebDriverWait(self.driver, timeout).until(images_loaded)
            logger.debug("✅ 圖片載入完成")
            return True
            
        except TimeoutException:
            logger.warning("⚠️ 等待圖片載入超時")
            return False
        except Exception as e:
            logger.debug(f"檢查圖片載入狀態時發生錯誤: {e}")
            return False

    def wait_for_content_stable(self, timeout=5):
        """等待內容穩定（不再變化）"""
        try:
            last_hash = None
            stable_count = 0
            
            for _ in range(timeout * 2):  # 每0.5秒檢查一次
                current_hash = self._get_page_content_hash()
                
                if current_hash == last_hash:
                    stable_count += 1
                    if stable_count >= 3:  # 連續3次內容相同，認為穩定
                        logger.debug("✅ 頁面內容已穩定")
                        return True
                else:
                    stable_count = 0
                    
                last_hash = current_hash
                time.sleep(0.5)
                
            return False
            
        except Exception as e:
            logger.debug(f"檢查內容穩定性時發生錯誤: {e}")
            return False

    def login(self, auto_captcha=False):
        """執行登入流程"""
        logger.info("🚀 開始執行登入流程...")
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

            # 步驟五：人工確認 CAPTCHA 驗證
            if not auto_captcha:
                print("\n" + "="*60)
                print("🤖 已自動填寫帳密並觸發驗證。")
                print("請在瀏覽器中手動完成 CAPTCHA 驗證，完成後請按 Enter 繼續...")
                print("="*60)
                input()
                logger.info("🎉 使用者已確認完成手動驗證，繼續執行。")
            
            return True

        except Exception as e:
            logger.error(f"❌ 登入流程失敗: {e}", exc_info=True)
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
                    logger.info(f"✅ 關閉彈窗")
                    break
                except:
                    continue
        except:
            logger.info("ℹ️ 未偵測到彈出式視窗")

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
            except:
                continue
        
        logger.error("❌ 找不到『會員登入』按鈕。")
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
            logger.error("❌ 未設定 email")
            return False
        
        for by, value in username_selectors:
            try:
                username_input = self.driver.find_element(by, value)
                username_input.clear()
                username_input.send_keys(email_value)
                return True
            except:
                continue
        
        logger.error("❌ 找不到帳號輸入框")
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
            except:
                continue
        
        logger.error("❌ 找不到密碼輸入框")
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
            except:
                continue
        
        logger.error("❌ 找不到『登入』按鈕")
        return False

    def reset_for_next_book(self):
        """重置狀態以處理下一本電子書"""
        try:
            self.driver.switch_to.default_content()
            
            # 重置所有狀態變數
            self.iframe_switched = False
            self.tutorial_handled = False
            self.popup_closed_count = 0
            self.same_page_count = 0
            self.last_page_content = None
            self.current_page_number = None
            self.output_dir = None
            self.consecutive_empty_pages = 0
            
            logger.info("✅ 狀態已重置，準備處理下一本電子書")
            
        except Exception as e:
            logger.error(f"重置狀態時發生錯誤: {e}")
    
    def navigate_to_book(self, book_url):
        """導航到電子書頁面"""
        if self.output_dir is not None:
            self.reset_for_next_book()
        
        logger.info(f"前往: {book_url}")
        self.driver.get(book_url)

        # 等待頁面完全載入
        logger.info("等待頁面載入...")
        try:
            self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "iframe[id^='epubjs-view-']"))
            )
            logger.info("✅ 電子書 iframe 已載入")
        except:
            logger.warning("⚠️ 等待電子書 iframe 超時")

        # 建立輸出目錄
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_dir = Path(f"output/ebook_{timestamp}")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"輸出目錄: {self.output_dir}")
        
        # 列出頁面元素資訊
        self.list_all_buttons_and_links()

    def list_all_buttons_and_links(self):
        """診斷方法：列出頁面上所有的按鈕和連結"""
        try:
            logger.info("🔍 開始掃描頁面上的按鈕和連結...")
            
            diag_dir = self.output_dir or Path("output/diagnostics")
            diag_dir.mkdir(parents=True, exist_ok=True)
            
            # 掃描按鈕
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            logger.info(f"📝 找到 {len(buttons)} 個按鈕")
            
            button_info = []
            for idx, btn in enumerate(buttons[:20], 1):
                try:
                    btn_id = btn.get_attribute('id')
                    btn_class = btn.get_attribute('class')
                    btn_text = btn.text.strip()[:50]
                    btn_visible = btn.is_displayed()
                    btn_enabled = btn.is_enabled()
                    
                    info = f"  [{idx}] ID: {btn_id or 'N/A'}, Class: {btn_class or 'N/A'}, Text: '{btn_text}', Visible: {btn_visible}, Enabled: {btn_enabled}"
                    logger.debug(info)
                    button_info.append(info)
                except:
                    pass
            
            # 將診斷資訊寫入檔案
            diag_file = diag_dir / "page_elements_diagnostic.txt"
            with open(diag_file, "w", encoding="utf-8") as f:
                f.write(f"頁面元素診斷報告\n")
                f.write(f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"URL: {self.driver.current_url}\n")
                f.write("="*60 + "\n\n")
                f.write(f"按鈕 (共 {len(buttons)} 個)\n")
                for info in button_info:
                    f.write(info + "\n")
            
            logger.info(f"📄 診斷資訊已儲存至: {diag_file}")
            
        except Exception as e:
            logger.warning(f"列出按鈕和連結時發生錯誤: {e}")

    def handle_tutorial(self):
        """處理教學引導畫面"""
        if self.tutorial_handled:
            logger.info("ℹ️ 教學引導已處理過，跳過此步驟")
            return
        
        max_retries = 3
        for i in range(max_retries):
            try:
                self.driver.switch_to.default_content()
                logger.info(f"🔄 檢查教學引導頁面... (第 {i + 1}/{max_retries} 次)")

                selectors = [
                    (By.ID, "UIObj-demo-next-btn"),
                    (By.CSS_SELECTOR, ".tutorial-next-button"),
                    (By.XPATH, "//button[contains(text(), '下一步')]"),
                ]
                
                step_count = 0
                while step_count < 10:
                    step_count += 1
                    if not self._click_tutorial_next_button(selectors, step_count):
                        if step_count > 1:
                            logger.info(f"✅ 教學引導處理完畢")
                        else:
                            logger.info("ℹ️ 未找到教學引導按鈕")
                        break
                
                self.tutorial_handled = True
                return

            except Exception as e:
                logger.warning(f"處理教學引導時發生錯誤: {e}")
                if i < max_retries - 1:
                    self.driver.refresh()
                    time.sleep(1)

    def _click_tutorial_next_button(self, selectors, step_count):
        """點擊教學引導的下一步按鈕"""
        for by, value in selectors:
            try:
                button = WebDriverWait(self.driver, 2).until(
                    EC.element_to_be_clickable((by, value))
                )
                logger.info(f"🖱️ 點擊教學按鈕第 {step_count} 次")
                button.click()
                time.sleep(0.1)
                return True
            except:
                continue
        return False

    def find_and_switch_to_ebook_iframe(self):
        """切換到電子書 iframe"""
        trace_id = f"iframe_switch_{datetime.now().strftime('%H%M%S%f')}"
        logger.info(f"[{trace_id}] 開始 iframe 切換流程")
        
        # 檢查是否已在 iframe 中
        if self.iframe_switched:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, "body > div, body > *")
                if elements:
                    logger.debug(f"[{trace_id}] 已在 iframe 中")
                    return True
                else:
                    logger.warning(f"[{trace_id}] iframe 狀態失效，重新切換")
                    self.iframe_switched = False
            except:
                self.iframe_switched = False
        
        # 切換到主頁面
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
                    logger.debug(f"[{trace_id}] 嘗試選擇器: {selector}")
                    self.wait.until(EC.frame_to_be_available_and_switch_to_it(
                        (By.CSS_SELECTOR, selector)))
                    
                    # 驗證切換成功
                    elements = self.wait.until(EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "body > div, body > *")))
                    
                    self.iframe_switched = True
                    self.execution_trace.append(f"{trace_id}: iframe切換成功")
                    logger.info(f"[{trace_id}] ✅ 成功切換到 iframe")
                    return True
                    
                except TimeoutException:
                    self.driver.switch_to.default_content()
                except Exception:
                    self.driver.switch_to.default_content()
            
            logger.error(f"[{trace_id}] ❌ 所有 iframe 選擇器都失敗")
            return False
            
        except Exception as e:
            logger.error(f"[{trace_id}] 嚴重錯誤: {e}")
            return False

    def capture_page_with_retry(self, page_num, max_retries=3, full_page=False):
        """改進的截圖方法，包含更好的內容檢測"""
        capture_id = f"capture_p{page_num}_{datetime.now().strftime('%H%M%S')}"
        logger.info(f"[{capture_id}] ========== 開始截圖第 {page_num} 頁 ==========")
        
        # 記錄截圖歷史
        if page_num not in self.page_capture_history:
            self.page_capture_history[page_num] = []
        
        for attempt in range(max_retries):
            attempt_id = f"{capture_id}_a{attempt+1}"
            logger.info(f"[{attempt_id}] 嘗試 {attempt + 1}/{max_retries}")
            
            try:
                # 檢查並切換 iframe
                if not self.iframe_switched:
                    if not self.find_and_switch_to_ebook_iframe():
                        self.driver.switch_to.default_content()
                        continue
                
                # 等待內容載入
                logger.debug(f"[{attempt_id}] 等待內容載入...")
                time.sleep(2)  # 基本等待
                
                # 等待圖片載入
                self.wait_for_images_loaded(timeout=10)
                
                # 等待內容穩定
                self.wait_for_content_stable(timeout=5)
                
                # 檢查頁面內容
                try:
                    body = self.driver.find_element(By.TAG_NAME, "body")
                    body_text = body.text
                    body_html = self.driver.page_source
                    
                    # 檢查是否有圖片
                    images = self.driver.find_elements(By.TAG_NAME, "img")
                    loaded_images = 0
                    for img in images:
                        try:
                            if img.get_attribute("src") and img.size['width'] > 0 and img.size['height'] > 0:
                                loaded_images += 1
                        except:
                            pass
                    
                    logger.debug(f"[{attempt_id}] 頁面統計:")
                    logger.debug(f"  - Body 文字長度: {len(body_text)}")
                    logger.debug(f"  - HTML 長度: {len(body_html)}")
                    logger.debug(f"  - 圖片數量: {len(images)}")
                    logger.debug(f"  - 已載入圖片: {loaded_images}")
                    
                    # 判斷內容是否充足
                    content_sufficient = False
                    
                    # 條件1: 有載入的圖片
                    if loaded_images > 0:
                        content_sufficient = True
                        logger.debug(f"[{attempt_id}] 有 {loaded_images} 張圖片已載入")
                    
                    # 條件2: 文字內容充足
                    elif len(body_text.strip()) > 100:
                        content_sufficient = True
                        logger.debug(f"[{attempt_id}] 文字內容充足")
                    
                    # 條件3: HTML內容豐富（可能是格式化的內容）
                    elif len(body_html) > 5000:
                        content_sufficient = True
                        logger.debug(f"[{attempt_id}] HTML內容豐富")
                    
                    if not content_sufficient:
                        logger.warning(f"[{attempt_id}] ⚠️ 頁面內容不足")
                        
                        # 如果是最後一頁附近，可能確實內容較少
                        if page_num > 150:  # 根據你的情況調整
                            logger.info(f"[{attempt_id}] 接近最後幾頁，可能內容較少，仍然截圖")
                        else:
                            # 再等待一下
                            logger.debug(f"[{attempt_id}] 額外等待 3 秒...")
                            time.sleep(3)
                            
                            # 重新檢查
                            images = self.driver.find_elements(By.TAG_NAME, "img")
                            loaded_images = sum(1 for img in images if self._is_image_loaded(img))
                            
                            if loaded_images == 0 and len(body_text.strip()) < 50:
                                logger.error(f"[{attempt_id}] 頁面內容仍然不足")
                                self.iframe_switched = False
                                continue
                    
                except Exception as e:
                    logger.error(f"[{attempt_id}] 無法檢查頁面內容: {e}")
                
                # 執行截圖
                screenshot_path = self.output_dir / f"page_{page_num:04d}.png"
                logger.debug(f"[{attempt_id}] 準備截圖: {screenshot_path.name}")
                
                self.driver.save_screenshot(str(screenshot_path))
                
                # 驗證截圖檔案
                if screenshot_path.exists() and screenshot_path.stat().st_size > 1024:
                    file_size = screenshot_path.stat().st_size / 1024
                    
                    # 驗證截圖不是灰色空白頁
                    if self._validate_screenshot(screenshot_path):
                        logger.info(f"[{attempt_id}] ✅ 截圖成功: {screenshot_path.name} ({file_size:.1f} KB)")
                        
                        # 記錄成功
                        self.page_capture_history[page_num].append({
                            'attempt': attempt + 1,
                            'success': True,
                            'file_size': file_size,
                            'timestamp': datetime.now().isoformat()
                        })
                        
                        # 檢查是否與前一張相同
                        if page_num > 1:
                            prev_path = self.output_dir / f"page_{page_num-1:04d}.png"
                            if prev_path.exists() and self._compare_screenshots(str(prev_path), str(screenshot_path)):
                                logger.warning(f"[{attempt_id}] ⚠️ 截圖與前一頁相同")
                                self.same_page_count += 1
                            else:
                                self.same_page_count = 0
                        
                        self.consecutive_empty_pages = 0  # 重置連續空白頁計數
                        return True
                    else:
                        logger.warning(f"[{attempt_id}] 截圖可能是灰色空白頁")
                        screenshot_path.unlink()
                        self.iframe_switched = False
                else:
                    logger.error(f"[{attempt_id}] ❌ 截圖失敗或檔案過小")
                    
            except Exception as e:
                logger.error(f"[{attempt_id}] 截圖異常: {type(e).__name__}: {str(e)}")
                self.iframe_switched = False
                time.sleep(1)
        
        # 記錄連續空白頁
        self.consecutive_empty_pages += 1
        logger.error(f"[{capture_id}] ❌❌❌ 所有 {max_retries} 次嘗試都失敗")
        return False
    
    def _is_image_loaded(self, img_element):
        """檢查圖片是否已載入"""
        try:
            return self.driver.execute_script(
                "return arguments[0].complete && "
                "typeof arguments[0].naturalWidth != 'undefined' && "
                "arguments[0].naturalWidth > 0",
                img_element
            )
        except:
            return False
    
    def _validate_screenshot(self, screenshot_path):
        """驗證截圖是否為有效內容（非灰色空白）"""
        try:
            img = Image.open(screenshot_path)
            img_array = np.array(img)
            
            # 計算圖片的平均顏色
            avg_color = img_array.mean(axis=(0, 1))
            
            # 檢查是否為灰色（RGB值相近）
            if all(140 < c < 160 for c in avg_color[:3]):
                std_dev = img_array.std()
                if std_dev < 10:
                    logger.warning(f"截圖可能是空白頁面（標準差: {std_dev:.2f}）")
                    return False
                    
            return True
            
        except Exception as e:
            logger.error(f"截圖驗證失敗: {e}")
            return True
    
    def _compare_screenshots(self, path1, path2):
        """比較兩張截圖是否相同"""
        try:
            img1 = Image.open(path1)
            img2 = Image.open(path2)
            
            if img1.size != img2.size:
                return False
            
            # 轉換為RGB模式
            img1 = img1.convert('RGB')
            img2 = img2.convert('RGB')
            
            # 快速比較
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
            is_same = similarity > 0.99
            
            if is_same:
                logger.debug(f"截圖相似度: {similarity:.2%}")
            
            img1.close()
            img2.close()
            
            return is_same
            
        except Exception as e:
            logger.debug(f"比較截圖時發生錯誤: {e}")
            return False

    def auto_capture_mode(self, total_pages=None, delay=5):
        """自動截圖模式"""
        print("\n" + "="*60)
        print("📸 自動截圖模式 (智慧分頁)")
        print("="*60)
        print(f"⏱️ 每頁間隔 {delay} 秒")
        print("📚 將自動偵測最後一頁並停止")
        print("="*60)
        print("\n✅ 已自動開始截圖流程...")
        
        # 確保已切換到 iframe
        if not self.find_and_switch_to_ebook_iframe():
            logger.error("❌ 無法開始截圖，找不到電子書 iframe")
            return

        page_num = 1
        successful_pages = 0
        failed_pages = []
        consecutive_failures = 0
        max_consecutive_failures = 5  # 增加到5次，因為可能有多頁載入較慢
        
        # 重置計數器
        self.same_page_count = 0
        self.last_page_content = None
        self.consecutive_empty_pages = 0

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
                
                # 調整失敗判斷邏輯
                if consecutive_failures >= max_consecutive_failures:
                    logger.error(f"❌ 連續 {max_consecutive_failures} 頁截圖失敗")
                    
                    # 如果已經成功截取了很多頁，可能是到達最後
                    if successful_pages > 100:
                        logger.info(f"📚 可能已到達最後幾頁（已成功 {successful_pages} 頁）")
                        break
                    else:
                        logger.error("停止執行")
                        break

            # 嘗試翻頁
            if not self._try_next_page():
                if self.same_page_count >= 2:
                    logger.info(f"📚 確認已到達最後一頁（第 {page_num} 頁）")
                    print(f"\n📚 已到達電子書最後一頁（第 {page_num} 頁）")
                    break
                else:
                    logger.info(f"📊 無法繼續翻頁")
                    break
            
            # 檢查是否內容重複
            if self.same_page_count >= 2:
                logger.warning(f"⚠️ 偵測到連續 {self.same_page_count} 次相同內容")
                print(f"\n⚠️ 偵測到重複內容，可能已到達最後一頁（第 {page_num} 頁）")
                break
            
            print(f"等待 {delay} 秒後截取下一頁...")
            time.sleep(delay)
            page_num += 1

        # 顯示結果摘要
        self._show_summary(successful_pages, failed_pages)

    def _try_next_page(self):
        """嘗試翻到下一頁"""
        page_turn_id = f"turn_{datetime.now().strftime('%H%M%S%f')}"
        logger.info(f"[{page_turn_id}] 開始翻頁流程")
        
        try:
            self.driver.switch_to.default_content()
            
            # 記錄翻頁前的狀態
            before_content_hash = self._get_page_content_hash()
            
            # 關閉彈窗
            self._close_popups()
            
            # 嘗試點擊翻頁按鈕
            next_button_clicked = False
            next_buttons_xpaths = [
                "//button[@id='UiObj-book-right-btn']",
                "//button[contains(@class, 'viewer__body__pagination') and contains(@class, 'right')]",
                "//button[contains(@class, 'next')]",
            ]
            
            for xpath in next_buttons_xpaths:
                try:
                    next_btn = self.driver.find_element(By.XPATH, xpath)
                    
                    if next_btn.is_displayed() and next_btn.is_enabled():
                        btn_classes = next_btn.get_attribute('class') or ''
                        if 'disabled' in btn_classes.lower():
                            logger.warning(f"[{page_turn_id}] 按鈕已禁用")
                            return False
                        
                        next_btn.click()
                        logger.info(f"[{page_turn_id}] ✅ 成功點擊翻頁按鈕")
                        next_button_clicked = True
                        break
                        
                except:
                    pass
            
            if not next_button_clicked:
                # 嘗試鍵盤翻頁
                try:
                    ActionChains(self.driver).send_keys(Keys.ARROW_RIGHT).perform()
                    logger.info(f"[{page_turn_id}] 使用鍵盤右鍵翻頁")
                    next_button_clicked = True
                except:
                    pass
            
            if not next_button_clicked:
                logger.warning(f"[{page_turn_id}] ❌ 無法找到翻頁方式")
                return False
            
            # 等待翻頁完成
            time.sleep(2)
            
            # 檢查內容是否改變
            after_content_hash = self._get_page_content_hash()
            
            if before_content_hash and after_content_hash and before_content_hash == after_content_hash:
                self.same_page_count += 1
                logger.warning(f"[{page_turn_id}] ⚠️ 內容未改變 (連續 {self.same_page_count} 次)")
                if self.same_page_count >= 2:
                    return False
            else:
                self.same_page_count = 0
                logger.info(f"[{page_turn_id}] ✅ 翻頁成功")
            
            return True
            
        except Exception as e:
            logger.error(f"[{page_turn_id}] 翻頁異常: {e}")
            return False
    
    def _get_page_content_hash(self):
        """取得當前頁面內容的雜湊值"""
        try:
            if self.iframe_switched:
                page_text = self.driver.find_element(By.TAG_NAME, "body").text
            else:
                self.driver.switch_to.default_content()
                page_text = self.driver.find_element(By.TAG_NAME, "body").text
            
            # 使用 hashlib 來生成雜湊
            return hashlib.md5(page_text.encode()).hexdigest()
            
        except Exception as e:
            logger.debug(f"無法取得頁面內容雜湊: {e}")
            return None
    
    def _get_current_page_number(self):
        """嘗試取得當前頁碼顯示"""
        try:
            page_selectors = [
                "//div[contains(@class, 'page-number')]",
                "//span[contains(@class, 'page')]",
                "//input[@type='number' and contains(@class, 'page')]",
            ]
            
            for selector in page_selectors:
                try:
                    element = self.driver.find_element(By.XPATH, selector)
                    if element.is_displayed():
                        text = element.text or element.get_attribute('value')
                        if text:
                            return text
                except:
                    continue
                    
        except:
            pass
        
        return None

    def _close_popups(self):
        """關閉可能的彈出視窗"""
        popup_closed = False
        
        popup_selectors = [
            ("//div[@id='UiObj-model' and contains(@style, 'display: block')]", "UiObj-model"),
            ("//div[contains(@class, 'popup') and contains(@style, 'display: block')]", "popup"),
            ("//div[contains(@class, 'modal') and contains(@style, 'display: block')]", "modal"),
        ]
        
        for xpath, description in popup_selectors:
            try:
                popup_elements = self.driver.find_elements(By.XPATH, xpath)
                for popup in popup_elements:
                    if popup.is_displayed():
                        # 嘗試關閉
                        close_methods = [
                            (".//button[contains(@class, 'close')]", "關閉按鈕"),
                            (".//span[contains(@class, 'close')]", "關閉span"),
                            (".//*[contains(text(), '×')]", "×符號"),
                        ]
                        
                        for close_xpath, method in close_methods:
                            try:
                                close_btn = popup.find_element(By.XPATH, close_xpath)
                                close_btn.click()
                                logger.info(f"✅ 關閉彈窗 ({method})")
                                popup_closed = True
                                time.sleep(0.3)
                                break
                            except:
                                continue
                        
                        if not popup_closed:
                            # 嘗試ESC鍵
                            try:
                                ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                                time.sleep(0.3)
                                if not popup.is_displayed():
                                    logger.info("✅ 使用 ESC 鍵關閉彈窗")
                                    popup_closed = True
                            except:
                                pass
            except:
                continue
        
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

    def print_execution_summary(self):
        """輸出執行摘要"""
        print("\n" + "="*60)
        print("📊 執行追蹤摘要")
        print("="*60)
        
        if self.execution_trace:
            print("\n執行軌跡:")
            for trace in self.execution_trace[-10:]:
                print(f"  - {trace}")
        
        if self.page_capture_history:
            print("\n頁面截圖統計:")
            for page_num, attempts in self.page_capture_history.items():
                success_count = sum(1 for a in attempts if a['success'])
                print(f"  第 {page_num} 頁: {success_count}/{len(attempts)} 成功")
        
        # 儲存詳細日誌
        if self.output_dir:
            log_file = self.output_dir / "execution_log.json"
            with open(log_file, "w", encoding="utf-8") as f:
                json.dump({
                    'execution_trace': self.execution_trace,
                    'page_capture_history': self.page_capture_history,
                    'timestamp': datetime.now().isoformat()
                }, f, ensure_ascii=False, indent=2)
            
            print(f"\n詳細日誌已儲存至: {log_file}")
        print("="*60)

    def _save_diagnostic_snapshot(self, filename_prefix):
        """儲存診斷快照"""
        try:
            if not self.output_dir:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                self.output_dir = Path(f"output/ebook_{timestamp}")
                self.output_dir.mkdir(parents=True, exist_ok=True)

            png_path = self.output_dir / f"{filename_prefix}.png"
            html_path = self.output_dir / f"{filename_prefix}.html"

            self.driver.save_screenshot(str(png_path))
            
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
            
            logger.info(f"📸 診斷快照已儲存: {png_path.name}, {html_path.name}")

        except Exception as e:
            logger.error(f"❌ 儲存診斷快照失敗: {e}")

    def close(self):
        """關閉瀏覽器"""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("瀏覽器已關閉")
            except Exception as e:
                logger.warning(f"關閉瀏覽器時出錯: {e}")