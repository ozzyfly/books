# 博客來電子書截圖工具 v3.0

這是一個使用 Selenium 自動化截取博客來電子書頁面的 Python 腳本。

## 特色

-   **多瀏覽器支援**：可透過設定檔選擇使用 Firefox, Chrome 或 Edge。
-   **穩定的 WebDriver 管理**：支援手動指定 WebDriver 路徑，解決自動下載在特定網路環境下的失敗問題。
-   **自動登入**：可設定帳號密碼自動登入，並包含處理滑塊驗證碼的提示。
-   **自動截圖**：設定總頁數和延遲，程式將自動翻頁並截圖。
-   **設定檔**：使用 `config.json` 進行所有設定，方便管理。
-   **日誌記錄**：詳細記錄操作過程，方便追蹤和除錯。
-   **自動跳過教學引導**：自動處理電子書閱讀器的初始教學畫面。
-   **互動式開始截圖**：登入並跳過教學後，會提示使用者確認是否開始截圖。

## 安裝與設定

### 1. 環境準備

-   **安裝 Python**：請確保您已安裝 Python 3.8 或更高版本。
-   **安裝瀏覽器**：根據您的偏好，安裝 [Firefox](https://www.mozilla.org/zh-TW/firefox/new/)、[Google Chrome](https://www.google.com/intl/zh-TW/chrome/) 或 [Microsoft Edge](https://www.microsoft.com/zh-tw/edge)。
-   **安裝依賴套件**：
    ```bash
    pip install -r requirements.txt
    ```

### 2. 設定 `config.json`

1.  **複製設定檔**：將 `config/config.example.json` 複製一份，並重新命名為 `config/config.json`。
2.  **編輯設定檔**：打開 `config/config.json` 並根據您的需求修改。

    ```json
    {
        "browser": "edge",
        "webdriver_path": "./msedgedriver",
        "email": "your_email@example.com",
        "password": "your_password",
        "headless": false,
        "auto_login": true,
        "book_url": "https://www.books.com.tw/products/e/your_book_id",
        "total_pages": 150,
        "delay": 5
    }
    ```

**參數說明**：

-   `browser`：指定要使用的瀏覽器，可選值為 `"firefox"`, `"chrome"`, `"edge"`。
-   `webdriver_path`：**（重要）** 手動指定 WebDriver 執行檔的路徑。預設為 `"./msedgedriver"`，指向專案根目錄下的檔案。
-   `email` / `password`：您的博客來帳號密碼。
-   `headless`：`true` 為無頭模式（背景執行），`false` 則會顯示瀏覽器畫面。
-   `auto_login`：`true` 啟用自動登入。
-   `book_url`：要截圖的電子書網址。
-   `total_pages`：預計截圖的總頁數。
-   `delay`：每頁之間的延遲秒數。

### 3. 手動下載 WebDriver（重要）

**為什麼需要手動下載？**

Selenium 的自動下載工具 (Selenium Manager) 在某些網路環境下（例如公司網路、特殊的 DNS 設定）可能會因為無法連線到下載伺服器而失敗。手動下載可以完全繞過這個問題，確保程式能穩定啟動。

**下載步驟**：

1.  **前往官方下載頁面**：
    *   **Microsoft Edge**: [https://developer.microsoft.com/en-us/microsoft-edge/tools/webdriver/](https://developer.microsoft.com/en-us/microsoft-edge/tools/webdriver/)

2.  **選擇正確版本**：請務必下載與您**目前瀏覽器版本完全對應**的 WebDriver。

3.  **放置檔案**：下載完成後，解壓縮檔案，將 `msedgedriver` (Windows 上可能是 `msedgedriver.exe`) 執行檔放置在**專案的根目錄**下。

    > **macOS 使用者特別提示**：
    > 如果您在 macOS 上遇到 `“msedgedriver” is damaged and can’t be opened.` 的錯誤訊息，這是因為系統的安全隔離屬性。請在終端機中，於專案根目錄下執行以下指令來移除該屬性：
    > ```bash
    > xattr -d com.apple.quarantine ./msedgedriver
    > ```

### 4. 執行程式

完成以上所有設定後，執行主程式：

```bash
python main.py
```

程式將會啟動您指定的瀏覽器，自動登入並開始截圖。

## 截圖輸出

截圖檔案會儲存在 `output` 資料夾中，並以時間戳命名。

## 注意事項

-   請遵守博客來的服務條款。此工具僅供個人學習和研究使用。
-   截圖速度和成功率可能受網路狀況和電腦性能影響。