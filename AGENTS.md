# Repository Guidelines

## Project Structure & Module Organization

本專案是 Flask + SQLite 的飲料團購系統。主要入口是 `app.py`，設定集中在 `config.py`，資料模型在 `models.py`，表單定義在 `forms.py`，Excel 匯出等輔助邏輯在 `utils.py`。

前端模板放在 `templates/`，其中 `templates/admin/` 是後台頁面；靜態資源放在 `static/`，主要樣式為 `static/css/style.css`，上傳菜單照片位於 `static/uploads/photos/`。資料庫由 `setup_db.py` 建立，`rebuild_db.py` 可重建資料庫；`db/*.db` 不納入版本控制。

## Build, Test, and Development Commands

- `pip install -r requirements.txt`：安裝 Flask、SQLAlchemy、WTForms、openpyxl 等相依套件。
- `python setup_db.py`：初始化資料庫與預設資料。
- `python app.py`：啟動本機開發伺服器，預設瀏覽 `http://localhost:5001`。
- `start.bat`：Windows 一鍵安裝相依套件並啟動應用。
- `python rebuild_db.py`：清除並重建資料庫，僅在需要重置本機資料時使用。
- `python -m py_compile app.py config.py forms.py models.py utils.py setup_db.py rebuild_db.py`：基本語法檢查。

## Coding Style & Naming Conventions

Python 程式遵循 PEP 8，使用 4 空格縮排。函式與變數使用 `snake_case`，類別與 SQLAlchemy model 使用 `PascalCase`。Flask route handler 名稱應描述頁面或動作，例如 `admin_dashboard`、`order_submit`。

模板檔案使用小寫加底線命名，例如 `order_form.html`。表單、模型與 route 變更應保持欄位名稱一致，避免模板中出現難以追蹤的臨時命名。

## Testing Guidelines

目前專案沒有正式測試框架或 coverage 要求。提交前至少執行 Python 語法檢查，並手動驗證主要流程：管理員註冊與登入、建立部門、建立團購 session、送出訂單、匯出 Excel。

若新增測試，建議使用 `pytest`，測試放在 `tests/`，檔名採 `test_*.py`，並優先覆蓋資料驗證、session 開關時間、訂單送出與 Excel 匯出。

## Commit & Pull Request Guidelines

目前 git 歷史只有初始提交，格式為英文祈使句並附範圍摘要，例如 `Initial commit: drink order pool system (Flask + SQLite)`。後續 commit 建議維持簡短、明確，例如 `Add order export validation`。

PR 應包含變更摘要、測試或手動驗證結果、資料庫 schema 影響，以及 UI 變更截圖。涉及 `.db`、上傳照片或 `.env` 的內容不得提交。

## Security & Configuration Tips

不要提交本機上傳檔案或密鑰。敏感設定請放在 `.env` 或部署環境變數。處理上傳檔案時保留 `secure_filename` 與副檔名限制，避免放寬未驗證的檔案類型。
