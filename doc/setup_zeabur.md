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
DATABASE_URL=sqlite:////app/db/drink_pool.db
```

`SECRET_KEY` 用於 Flask session 與 CSRF。可在本機產生：

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

`ADMIN_ENTRY_PASSWORD` 是從首頁進入後台登入頁之前的入口密碼。未設定時，正式環境會無法正常進入後台入口流程。

`DATABASE_URL` 建議使用：

```text
DATABASE_URL=sqlite:////app/db/drink_pool.db
```

這裡需要四個 `/`。`sqlite:////app/db/drink_pool.db` 代表 SQLite 使用容器內的絕對路徑 `/app/db/drink_pool.db`。DB 檔案必須位於 Zeabur Volume 掛載的 `/app/db` 底下，否則服務重啟或重新部署後資料可能消失。

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

## 5. 圖片 Housekeeping

專案提供清理上傳菜單照片的 CLI：

```bash
python cleanup_uploads.py --dry-run
python cleanup_uploads.py --yes
python cleanup_uploads.py --yes --retention-days 90
```

預設清理規則：

- 刪除 `static/uploads/photos/` 中 DB 未引用、且檔案修改時間超過 24 小時的孤兒圖片。
- 刪除已結束超過 90 天的場次照片，並將該場次 `photo_path` 清空。
- 保留 `.gitkeep`、子目錄、未知副檔名與仍被未過期場次引用的圖片。
- 若 DB 引用的圖片檔案不存在，只在輸出中列為 missing，不自動清空 DB。

### Zeabur worker service

建議做法是新增 cleanup worker service，讓它定期執行清檔。這個做法的前提是 Zeabur 方案可讓 worker 存取與 web service 同一份 `/app/db` 與 `/app/static/uploads/photos` Volume。

1. 在同一個 Zeabur Project 新增 GitHub service。
2. 選擇同一個 `drink-pool` repo 與 branch。
3. 將 service 命名為 `drink-pool-cleanup-worker`。
4. Start Command 設為：

```bash
python setup_db.py && python cleanup_worker.py
```

5. Environment Variables 設定：

```text
DATABASE_URL=sqlite:////app/db/drink_pool.db
UPLOAD_CLEANUP_ENABLED=true
UPLOAD_CLEANUP_RETENTION_DAYS=90
UPLOAD_CLEANUP_ORPHAN_GRACE_HOURS=24
UPLOAD_CLEANUP_INTERVAL_HOURS=24
UPLOAD_CLEANUP_RUN_AT=03:30
```

`UPLOAD_CLEANUP_RUN_AT=03:30` 代表 worker 啟動後會先等待到下一個 03:30，再執行第一次清檔；之後每天約同一時間執行一次。若不設定 `UPLOAD_CLEANUP_RUN_AT`，worker 會依 `UPLOAD_CLEANUP_INTERVAL_HOURS` 的間隔等待後執行。

6. cleanup worker 必須能存取與 web service 相同的 Volume：

```text
/app/db
/app/static/uploads/photos
```

7. 到 worker logs 先確認排程等待時間與每日清檔摘要，例如：

```text
next_cleanup_in_seconds=...
mode=apply
scanned_files=...
orphan_files=...
expired_referenced_files=...
cleared_photo_references=...
```

### 無法共享 Volume 時的備援

如果 Zeabur 當前方案不能讓兩個 service 共享同一份 `/app/db` 與 `/app/static/uploads/photos` Volume，不要啟用獨立 cleanup worker，否則 worker 可能看到另一份空 DB 或空圖片目錄。

此時請改在 web service 的 Command Execution 內手動執行。這不是完全自動，但最安全，因為命令會在持有正確 `/app/db` 與 `/app/static/uploads/photos` 的 web service 內執行：

```bash
python cleanup_uploads.py --dry-run
python cleanup_uploads.py --yes
```

也可以日後改成 web service 內部排程，讓清檔邏輯直接在持有正確 Volume 的服務中執行。

## 6. 首次啟用流程

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

## 7. 驗收清單

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
- 圖片清檔先用 `python cleanup_uploads.py --dry-run` 檢查摘要，再用 `--yes` 或 cleanup worker 實際執行。
- 清檔後未過期場次圖片仍可顯示，過期場次不再顯示圖片但訂單與 Excel 匯出仍正常。

## 8. 常見問題

### 啟動後資料消失

通常是沒有掛載 `/app/db` Volume。SQLite 檔案必須放在持久化磁碟上。

### 菜單照片消失

通常是沒有掛載 `/app/static/uploads/photos` Volume。

### cleanup worker 沒有刪到預期圖片

先確認 worker 與 web service 是否真的使用同一份 Volume。`DATABASE_URL` 應為：

```text
DATABASE_URL=sqlite:////app/db/drink_pool.db
```

如果 worker 不能共享 web service 的 `/app/db` 與 `/app/static/uploads/photos`，請改用 web service 的 Command Execution 執行 `python cleanup_uploads.py --dry-run` 與 `python cleanup_uploads.py --yes`。

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

## 9. 參考

- Zeabur Flask 部署：<https://zeabur.com/docs/en-US/guides/python/flask>
- Zeabur 環境變數：<https://zeabur.com/docs/en-US/deploy/config/environment-variables>
- Zeabur Volumes：<https://zeabur.com/docs/en-US/data-management/volumes>
