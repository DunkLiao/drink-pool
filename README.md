# 飲料團購系統

這是一個以 Flask + SQLite 建置的內部飲料團購系統。管理員可以建立團購場次、上傳菜單照片、管理部門、查看訂單並匯出 Excel；一般使用者可以在開放時間內填寫飲料訂單。

## 技術棧

- **後端**：Python / Flask
- **資料庫**：SQLite / Flask-SQLAlchemy
- **登入驗證**：Flask-Login + bcrypt
- **表單處理**：WTForms / Flask-WTF
- **Excel 匯出**：openpyxl
- **前端**：Bootstrap 5 CDN + 自訂 CSS
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

本專案已加入 `zbpack.json`，Zeabur 匯入 repo 後會使用其中的啟動命令。

### 1. 推送到 GitHub

先將本專案推送到 GitHub 程式碼倉庫，再到 Zeabur 建立專案，選擇部署此程式碼倉庫。

### 2. 設定環境變數

在 Zeabur 服務設定中加入：

```text
SECRET_KEY=<一串夠長且不可猜的隨機密鑰>
ADMIN_ENTRY_PASSWORD=<後台入口密碼>
```

可用以下指令在本機產生密鑰：

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

`SECRET_KEY` 用於保護 Flask 工作階段、登入狀態與 CSRF 權杖，不應寫死在程式碼或提交到 Git。

`ADMIN_ENTRY_PASSWORD` 是從首頁進入後台登入頁前的入口密碼。本機可放在 `.env`，正式部署請設定在 Zeabur 環境變數。未設定時，系統會拒絕未登入使用者進入後台登入與註冊頁，避免正式環境漏設入口保護。

### 3. 掛載 Volumes

本專案使用 SQLite 與本機上傳目錄，因此 Zeabur 需要掛載持久化 Volume 保存執行期間資料：

```text
/app/db
/app/static/uploads/photos
```

如果沒有掛載 Volume，重新部署或服務重啟後，資料庫與上傳的菜單照片可能會消失。

### 4. 啟動命令

Zeabur 啟動命令定義在 `zbpack.json`：

```bash
python setup_db.py && gunicorn wsgi:app --bind 0.0.0.0:$PORT
```

其中：

- `python setup_db.py`：建立資料庫結構與預設設定。
- `gunicorn wsgi:app`：用 Gunicorn 啟動 Flask app。
- `$PORT`：Zeabur 自動提供的服務連接埠。

部署完成後，開啟 Zeabur domain，從首頁點選「後台登入」並通過入口密碼後，再進入 `/admin/register` 建立第一個管理員帳號。

## 功能

| 功能 | 說明 |
| --- | --- |
| 首頁場次列表 | 顯示目前開放中的團購場次 |
| 訂單表單 | 填寫姓名、部門、飲料品項、甜度、冰塊、加料與備註 |
| 場次管理 | 建立、編輯、刪除、啟用或停用團購場次 |
| 菜單照片上傳 | 建立場次時可上傳菜單圖片，供使用者填單參考 |
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
        ├── departments.html       # 部門管理
        ├── orders.html            # 訂單列表
        └── settings.html          # 系統設定
```

## 資料表

| 資料表 | 用途 |
| --- | --- |
| `users` | 管理員帳號 |
| `departments` | 部門清單與排序 |
| `sessions` | 團購場次、時間範圍與菜單照片 |
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

基本語法檢查：

```powershell
python -m py_compile app.py config.py forms.py models.py utils.py setup_db.py rebuild_db.py wsgi.py
```

## 注意事項

- 不要提交 `.env`、本機資料庫、上傳照片或任何密鑰。
- `db/*.db` 與 `static/uploads/photos/*` 應保持為執行期間資料。
- Zeabur 正式部署時一定要設定 `SECRET_KEY` 與 `ADMIN_ENTRY_PASSWORD`。
- Zeabur 使用 SQLite 時，請保留 `/app/db` 與 `/app/static/uploads/photos` 的 Volume 掛載。
- 若未來需要多人高併發或多副本部署，建議改用 PostgreSQL。
