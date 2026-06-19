# 飲料團購系統

這是一個以 Flask + SQLite 建置的內部飲料團購系統。管理員可以建立團購場次、上傳菜單照片、管理部門、查看訂單並匯出 Excel；一般使用者可以在開放時間內填寫飲料訂單。

## 技術棧

- **後端**：Python / Flask
- **資料庫**：SQLite / Flask-SQLAlchemy
- **登入驗證**：Flask-Login + bcrypt
- **表單處理**：WTForms / Flask-WTF
- **Excel 匯出**：openpyxl
- **OCR 辨識**：PaddleOCR / PaddlePaddle
- **AI 校正**：OpenRouter Chat Completions + JSON Schema
- **前端**：Bootstrap 5 CDN + 自訂 CSS
- **測試**：pytest
- **部署**：Zeabur + Gunicorn

## 本機快速啟動

Windows 可直接執行：

```powershell
start.bat
```

第一次執行時，`start.bat` 會檢查並建立 `.env`，要求輸入本機 UAT 的 `ADMIN_ENTRY_PASSWORD`，之後後台入口密碼會從 `.env` 載入。

或手動執行：

```powershell
pip install -r requirements.txt
python setup_db.py
python app.py
```

第一次執行 PaddleOCR 時會下載 OCR 模型，請確認本機可連線並預留啟動時間。預設使用繁體中文 OCR 語言代碼：

```text
PADDLEOCR_LANG=chinese_cht
```

若菜單多為簡體中文或英文混合，可在 `.env` 或部署環境變數改成 PaddleOCR 支援的其他語言代碼。

菜單照片上傳後會先建立團購場次，再把 OCR 排入背景辨識，避免建立場次時卡住。可到後台「菜單品項」頁查看 OCR 狀態、辨識結果並手動修正。高解析圖片會先產生縮小暫存圖再辨識，預設長邊限制為 2000px：

```text
PADDLEOCR_MENU_MAX_SIDE=2000
```

若要使用 AI 修正 OCR 結果，請在 `.env` 或部署環境變數設定 OpenRouter：

```text
OPENROUTER_API_KEY=<OpenRouter API Key>
OPENROUTER_MODEL=openai/gpt-4o-2024-08-06
OPENROUTER_SITE_NAME=drink-pool
OPENROUTER_TIMEOUT_SECONDS=90
OPENROUTER_IMAGE_MAX_SIDE=1200
```

OpenRouter 是選用設定；未設定 `OPENROUTER_API_KEY` 時，系統仍可使用團購、菜單照片、PaddleOCR、手動品項、下單與匯出功能，但後台會停用「AI 修正 OCR」。設定後可在後台「菜單品項」頁點選「AI 修正 OCR」。AI 修正需先等 OCR 完成且已有菜單品項，系統會把 AI 修正排入背景處理並產生草稿，管理員確認並套用勾選品項後才會寫入正式菜單。

啟動後開啟：

```text
http://localhost:5001
```

## 本機 UAT

本機 UAT 建議直接使用 `start.bat` 啟動，流程會自動完成本機環境準備：

```powershell
cd D:\VIbeCoding\drink-pool
.\start.bat
```

`start.bat` 會依序執行：

1. 檢查專案根目錄是否有 `.env`。
2. 若 `.env` 不存在，會自動建立。
3. 若 `.env` 沒有非空的 `ADMIN_ENTRY_PASSWORD`，會要求輸入本機 UAT 後台入口密碼並寫入 `.env`。
4. 安裝 `requirements.txt` 相依套件。
5. 若 `db/drink_pool.db` 不存在，執行 `python setup_db.py` 初始化資料庫。
6. 啟動 Flask 開發伺服器。

啟動後使用瀏覽器開啟：

```text
http://localhost:5001
```

後台入口密碼儲存在 `.env`：

```text
ADMIN_ENTRY_PASSWORD=<本機 UAT 後台入口密碼>
```

`.env` 已被 `.gitignore` 排除，不要提交。若要更換本機 UAT 後台入口密碼，可直接編輯 `.env` 的 `ADMIN_ENTRY_PASSWORD`，再重新啟動 `start.bat`。

本機 UAT 建議驗收流程：

1. 首頁點選「後台登入」，確認會先要求後台入口密碼。
2. 輸入錯誤入口密碼，確認無法進入後台登入頁。
3. 輸入 `.env` 中的 `ADMIN_ENTRY_PASSWORD`，確認可進入後台登入頁。
4. 第一次使用時，進入 `/admin/register` 建立管理員帳號。
5. 登入後台後建立部門。
6. 建立團購場次並上傳菜單圖片。
7. 回到首頁進入下單頁，確認菜單圖片可放大且可下載。
8. 送出一筆訂單。
9. 回後台查看訂單，確認可匯出 Excel。
10. 登出後再次點選「後台登入」，確認需要重新輸入口密碼。

## 第一次使用

1. 進入 `/admin/register` 建立第一個管理員帳號。
2. 從首頁點選「後台登入」，先輸入 `ADMIN_ENTRY_PASSWORD` 設定的入口密碼。
3. 進入 `/admin/login` 登入後台。
4. 到部門管理頁新增部門。
5. 建立團購場次，設定標題、開始時間、結束時間，並可上傳菜單照片。
6. 將首頁網址分享給同事填寫訂單。
7. 團購結束後可在後台查看訂單並匯出 Excel。

## 部署到 Zeabur

本專案已加入 `zbpack.json`，Zeabur 匯入 repo 後會使用其中的啟動命令：

```bash
python setup_db.py && gunicorn wsgi:app --bind 0.0.0.0:$PORT
```

Zeabur 正式環境至少要設定：

```text
SECRET_KEY=<隨機長字串>
ADMIN_ENTRY_PASSWORD=<後台入口密碼>
```

若要保留 SQLite 資料與上傳照片，需掛載 Zeabur Volume：

```text
/app/db
/app/static/uploads/photos
```

OpenRouter 是選用功能；未設定時只會停用「AI 修正 OCR」，不影響一般團購、OCR、手動品項、下單與匯出流程。完整部署步驟、環境變數、Volume 與驗收清單請看 [doc/setup_zeabur.md](doc/setup_zeabur.md)。

## 功能

| 功能 | 說明 |
| --- | --- |
| 首頁場次列表 | 顯示目前開放中的團購場次 |
| 訂單表單 | 填寫姓名、部門、飲料品項、甜度、冰塊、加料與備註 |
| 菜單品項下拉 | 可由後台 OCR/手動維護的品項帶入飲料名稱與單價 |
| 場次管理 | 建立、編輯、刪除、啟用或停用團購場次 |
| 菜單照片上傳 | 建立場次時可上傳菜單圖片，供使用者填單參考，並嘗試以 PaddleOCR 辨識品項與價格 |
| 菜單品項管理 | 後台可查看 OCR 狀態，並新增、編輯、停用、刪除與排序單一場次的菜單品項 |
| AI 修正 OCR 草稿 | OCR 完成後使用 OpenRouter 依菜單圖片與既有品項產生背景修正草稿，管理員確認後套用 |
| 部門管理 | 新增、刪除與排序部門 |
| 系統設定 | 後台可調整網站標題、組織名稱等顯示文字 |
| 訂單管理 | 後台查看單一場次所有訂單 |
| Excel 匯出 | 將團購訂單匯出為 `.xlsx` 檔案 |
| 資料庫還原 | 本機可透過 `restore_db.bat` 還原空白資料庫 |

## 專案結構

```text
drink-pool/
├── app.py                         # Flask 應用程式入口與路由
├── wsgi.py                        # Gunicorn / Zeabur 使用的 WSGI 入口
├── config.py                      # 設定檔
├── models.py                      # SQLAlchemy 資料模型
├── forms.py                       # WTForms 表單定義
├── utils.py                       # Excel 匯出等輔助邏輯
├── ocr.py                         # 菜單 OCR 與品項解析
├── ai_menu.py                     # OpenRouter AI 菜單修正服務
├── setup_db.py                    # 初始化資料庫
├── rebuild_db.py                  # 清除並重建資料庫
├── requirements.txt               # Python 相依套件
├── zbpack.json                    # Zeabur 啟動設定
├── start.bat                      # Windows 本機快速啟動
├── restore_db.bat                 # Windows 本機還原空白資料庫
├── db/
│   ├── drink_pool.db              # 本機資料庫，忽略不提交
│   └── drink_pool_blank.db        # 空白備份資料庫，忽略不提交
├── static/
│   ├── css/style.css              # 主要樣式
│   └── uploads/photos/            # 上傳的菜單照片
├── tests/                         # pytest 測試與菜單圖片 fixtures
└── templates/
    ├── base.html                  # 共用版型
    ├── index.html                 # 首頁
    ├── order_form.html            # 訂單表單
    ├── order_success.html         # 訂單成功頁
    └── admin/
        ├── login.html             # 後台登入
        ├── entry.html             # 後台入口密碼驗證
        ├── register.html          # 管理員註冊
        ├── dashboard.html         # 後台首頁
        ├── session_form.html      # 場次表單
        ├── menu_items.html        # 菜單品項管理
        ├── departments.html       # 部門管理
        ├── orders.html            # 訂單列表
        └── settings.html          # 系統設定
```

## 資料表

| 資料表 | 用途 |
| --- | --- |
| `users` | 管理員帳號 |
| `departments` | 部門清單與排序 |
| `sessions` | 團購場次、時間範圍、菜單照片與 OCR 狀態 |
| `menu_items` | 單一團購場次的菜單品項、價格與 OCR 信心分數 |
| `ai_menu_drafts` | OpenRouter AI 修正 OCR 的待確認草稿 |
| `orders` | 使用者送出的飲料訂單 |
| `order_addons` | 每筆訂單的加料項目 |
| `system_settings` | 網站顯示設定 |

## 開發與檢查指令

安裝相依套件：

```powershell
pip install -r requirements.txt
```

初始化資料庫：

```powershell
python setup_db.py
```

啟動開發伺服器：

```powershell
python app.py
```

## 注意事項

- 不要提交 `.env`、本機資料庫、上傳照片或任何密鑰。
- `db/*.db` 與 `static/uploads/photos/*` 應保持為執行期間資料。
- 測試用圖片位於 `tests/menu/`，屬於測試 fixtures，可納入版本控制；正式上傳圖片仍應保留在 `static/uploads/photos/` 並由 `.gitignore` 排除。
- Zeabur 正式部署時一定要設定 `SECRET_KEY` 與 `ADMIN_ENTRY_PASSWORD`。
- Zeabur 使用 SQLite 時，請保留 `/app/db` 與 `/app/static/uploads/photos` 的 Volume 掛載。
- PaddleOCR/PaddlePaddle 套件與模型較大，首次部署或冷啟動會比原本慢；OCR 會在背景執行，若 Zeabur 資源不足，可先使用後台手動新增菜單品項。
- OCR 辨識結果只會新增同場次內尚不存在的品項，不會覆蓋人工修正過的名稱或價格。
- AI 修正 OCR 需要 OpenRouter API key；未設定時只會停用 AI 修正，不影響一般團購與 OCR 流程。AI 會在背景產生待確認草稿，不會自動覆蓋正式菜單。
- 多價格菜單會拆成單價品項，例如 `紅茶 M`、`紅茶 L`，方便下單與 Excel 結算。
- 若未來需要多人高併發或多副本部署，建議改用 PostgreSQL。
