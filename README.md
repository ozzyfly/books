# 博客來電子書截圖工具 v3.0

這是一個使用 Selenium 自動化截取博客來電子書頁面的 Python 腳本。

## 特色

-   **自動登入**：可設定帳號密碼自動登入。
-   **自動截圖**：設定總頁數和延遲，程式將自動翻頁並截圖。
-   **全頁截圖**：支援滾動截取整個頁面（實驗性功能）。
-   **設定檔**：使用 `config.json` 進行所有設定，方便管理。
-   **日誌記錄**：詳細記錄操作過程，方便追蹤和除錯。

## 使用方法

### 1. 環境設定

-   **安裝 Python**：請確保您已安裝 Python 3.8 或更高版本。
-   **安裝 Firefox**：此工具需要 Firefox 瀏覽器。
-   **安裝依賴套件**：
    ```bash
    pip install -r requirements.txt
    ```

### 2. 設定 `config.json`

在 `config` 資料夾中，有一個 `config.json` 檔案。請根據您的需求修改此檔案。

```json
{
    "email": "your_email@example.com",
    "password": "your_password",
    "headless": false,
    "auto_login": true,
    "book_url": "https://www.books.com.tw/products/e/your_book_id",
    "total_pages": 150,
    "delay": 5,
    "full_page_screenshot": false
}
```

**參數說明**：

-   `email` / `password`：您的博客來帳號密碼。
-   `headless`：`true` 為無頭模式（背景執行），`false` 則會顯示瀏覽器畫面。
-   `auto_login`：`true` 啟用自動登入。
-   `book_url`：要截圖的電子書網址。
-   `total_pages`：預計截圖的總頁數。
-   `delay`：每頁之間的延遲秒數。
-   `full_page_screenshot`：是否啟用全頁滾動截圖。

### 3. 執行程式

完成設定後，直接執行主程式：

```bash
python main.py
```

程式將會啟動瀏覽器，自動登入並開始截圖。

## 截圖輸出

截圖檔案會儲存在 `output` 資料夾中，並以時間戳命名。

## 注意事項

-   請遵守博客來的服務條款。此工具僅供個人學習和研究使用。
-   截圖速度和成功率可能受網路狀況和電腦性能影響。