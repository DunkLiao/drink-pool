# Zeabur 部署設定

本文說明如何將 `drink-pool` 部署到 Zeabur。此專案是 Flask + SQLite 應用，使用 `zbpack.json` 啟動。PaddleOCR 與 OpenRouter AI 修正菜單都是選用功能，預設部署會先確保團購主流程穩定啟動。

## 1. 部署前檢查

先確認以下檔案已在 GitHub repo 中：

- `zbpack.json`
- `wsgi.py`
- `requirements.txt`
- `setup_db.py`
- `app.py`
- `config.py`

`zbpack.json` 應維持以下啟動命令：

```json
{
  "start_command": "python setup_db.py && gunicorn wsgi:app --bind 0.0.0.0:$PORT"
}
```

不要提交以下本機執行期間資料：

- `.env`
- `db/*.db`
- `static/uploads/photos/*`
- 任何 OpenRouter API key 或密鑰

## 2. 建立 Zeabur 服務

1. 將專案推送到 GitHub。
2. 到 Zeabur 建立 Project。
3. 新增 Service，選擇 GitHub Repository。
4. 選取 `drink-pool` repo。
5. 確認 Zeabur 會使用 repo 內的 `zbpack.json`。
6. 部署後，Zeabur 會執行：

```bash
python setup_db.py && gunicorn wsgi:app --bind 0.0.0.0:$PORT
```

其中 `setup_db.py` 會建立 SQLite 資料表與預設設定；`gunicorn wsgi:app` 會啟動 Flask app；`PORT` 由 Zeabur 自動注入。

## 3. 環境變數

### 必填

Zeabur 正式環境至少要設定：

```text
SECRET_KEY=<隨機長字串>
ADMIN_ENTRY_PASSWORD=<後台入口密碼>
```

`SECRET_KEY` 用於 Flask session 與 CSRF。可在本機產生：

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

`ADMIN_ENTRY_PASSWORD` 是從首頁進入後台登入頁之前的入口密碼。未設定時，正式環境會無法正常進入後台入口流程。

### 選填：OpenRouter AI 修正 OCR

若要啟用「AI 修正 OCR」，再設定：

```text
OPENROUTER_API_KEY=<OpenRouter API Key>
OPENROUTER_MODEL=openai/gpt-4o-2024-08-06
OPENROUTER_SITE_NAME=drink-pool
OPENROUTER_TIMEOUT_SECONDS=90
OPENROUTER_IMAGE_MAX_SIDE=1200
```

OpenRouter 是選用功能。未設定 `OPENROUTER_API_KEY` 時，系統仍可使用團購、菜單照片、PaddleOCR、手動品項、下單與匯出功能；後台只會停用「AI 修正 OCR」。

### 選填：OCR 設定

Zeabur 預設只安裝 `requirements.txt`，不安裝 PaddleOCR / PaddlePaddle。這可避免大型 OCR 套件造成建置時間過長、映像過大或資源不足。未啟用 OCR 時，菜單照片仍可上傳，品項可在後台手動新增。

若部署環境資源足夠，且要啟用 OCR，需先讓建置流程額外安裝 `requirements-ocr.txt`，再設定：

```text
PADDLEOCR_ENABLED=true
PADDLEOCR_LANG=chinese_cht
PADDLEOCR_MENU_MAX_SIDE=2000
```

`PADDLEOCR_ENABLED` 預設為 `false`。

`PADDLEOCR_LANG` 預設為 `chinese_cht`。若菜單多為簡體中文或英文混合，可改成 PaddleOCR 支援的其他語言代碼。

`PADDLEOCR_MENU_MAX_SIDE` 會在 OCR 前縮小高解析菜單圖片，降低辨識時間與記憶體壓力。

## 4. Volume 掛載

此專案使用 SQLite 與本機上傳目錄。Zeabur 上要掛載 Volume，否則重新部署或服務重啟後，資料庫與上傳照片可能消失。

建議掛載：

```text
/app/db
/app/static/uploads/photos
```

用途：

- `/app/db`：保存 `drink_pool.db` 與空白備份資料庫。
- `/app/static/uploads/photos`：保存上傳的菜單照片。

不要用提交 `.db` 檔取代 Volume。正式資料持久化應靠 Zeabur Volume。

## 5. 首次啟用流程

部署完成後：

1. 開啟 Zeabur 提供的網站網址。
2. 點選「後台登入」。
3. 輸入 `ADMIN_ENTRY_PASSWORD`。
4. 進入 `/admin/register` 建立第一個管理員帳號。
5. 登入後台。
6. 建立部門。
7. 建立團購場次並上傳菜單照片。
8. 到「菜單品項」頁手動新增或修正品項。
9. 若已啟用 PaddleOCR，可確認 OCR 狀態，完成後再手動修正品項。
10. 若已啟用 PaddleOCR 並設定 OpenRouter，可點選「AI 修正 OCR」排入背景處理，完成後確認草稿並套用。
11. 回首頁測試送出一筆訂單。
12. 回後台確認訂單並測試 Excel 匯出。

## 6. 驗收清單

部署後至少檢查：

- 首頁可正常開啟。
- 後台入口密碼可擋住未授權使用者。
- `/admin/register` 可建立第一個管理員。
- 部門可新增。
- 場次可建立。
- 菜單照片可上傳並在下單頁顯示。
- 未啟用 OCR 時，可手動新增菜單品項；啟用 OCR 時，可在背景完成或失敗時顯示狀態。
- 手動菜單品項可新增、編輯、停用、刪除。
- 使用者可送出訂單。
- 後台可匯出 Excel。
- 重新部署或重啟後，若已掛 Volume，資料庫與照片仍存在。

## 7. 常見問題

### 啟動後資料消失

通常是沒有掛載 `/app/db` Volume。SQLite 檔案必須放在持久化磁碟上。

### 菜單照片消失

通常是沒有掛載 `/app/static/uploads/photos` Volume。

### PaddleOCR 套件安裝失敗或 OCR 顯示未安裝

這通常不會影響網站主流程。Zeabur 上建議先維持預設部署，不安裝 OCR 套件；管理員可上傳菜單照片並手動新增品項。

若確定要在 Zeabur 啟用 OCR，請確認：

- 建置流程有額外安裝 `requirements-ocr.txt`。
- 環境變數有設定 `PADDLEOCR_ENABLED=true`。
- 服務規格足以承受 PaddleOCR / PaddlePaddle 的套件大小、記憶體需求與首次模型下載。

### AI 修正 OCR 不可用

確認是否已設定 `OPENROUTER_API_KEY`。另外，AI 修正需等該場次 OCR 完成且已有菜單品項後才能執行。

### OCR 第一次很慢

PaddleOCR 會在第一次執行時下載與載入模型，冷啟動時間較長。若 Zeabur 資源不足，請維持 `PADDLEOCR_ENABLED=false` 並使用後台手動新增菜單品項。

### OpenRouter 呼叫偶發失敗

可先確認 `OPENROUTER_MODEL`、`OPENROUTER_TIMEOUT_SECONDS` 與 `OPENROUTER_IMAGE_MAX_SIDE`。目前預設會在送出前將圖片長邊縮到 1200，並將 AI 修正排入背景處理。

### 服務啟動失敗

先確認：

- `requirements.txt` 安裝成功。OCR 選用套件不應阻塞主流程部署。
- `gunicorn` 有在相依套件中。
- Zeabur 有注入 `PORT`。
- `setup_db.py` 能建立資料庫。
- `SECRET_KEY` 與 `ADMIN_ENTRY_PASSWORD` 已設定。

## 8. 參考

- Zeabur Flask 部署：<https://zeabur.com/docs/en-US/guides/python/flask>
- Zeabur 環境變數：<https://zeabur.com/docs/en-US/deploy/config/environment-variables>
- Zeabur Volumes：<https://zeabur.com/docs/en-US/data-management/volumes>
