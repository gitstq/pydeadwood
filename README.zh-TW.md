# 🪵 PyDeadwood — Python 死碼掃描器

> 不需要執行你的程式碼，也能找出沒人用的那一部分。

[English](README.en.md) · 繁體中文 · [简体中文](README.md)

PyDeadwood 是一個零依賴的 Python 死碼掃描工具：它只用標準函式庫的 `ast` 解析程式碼、**絕不匯入或執行目標程式碼**，即使掃描不可信的程式碼也很安全。它能找出未使用的匯入、函式、類別與方法，以及 `return` 之後的不可達程式碼和 `if False:` 這類常數死分支，並以文字或 JSON 輸出，方便接進 CI。

## ✨ 核心特性

- 🔍 **未用匯入檢測**：`import` / `from … import`（含別名），星號匯入永不誤報
- 🧩 **未用定義檢測**：頂層函式、類別、方法，跨檔案引用也會被算作「已使用」
- 🚫 **不可達程式碼檢測**：`return` / `raise` / `break` / `continue` 之後的陳述式
- 🌿 **常數死分支檢測**：`if False:`、`if True:` 的 `else`、`while False:`
- 🛡️ **只報告、不刪除**：預設不修改任何檔案，刪除程式碼的決定永遠留給人
- 🧪 **低誤報豁免**：`__all__` 公開匯出、雙底線方法、`main`、測試函式與 `setUp/tearDown` 等生命週期方法預設不報
- 📄 **兩種輸出**：人類可讀文字 + 機器可讀 JSON，結束碼可直接用於 CI 門禁
- 🪶 **零依賴**：僅 Python 標準函式庫，Python ≥ 3.9 即可執行

## 🚀 快速開始

```bash
# 不需要安裝任何第三方依賴
git clone https://github.com/gitstq/pydeadwood.git
cd pydeadwood

# 掃描目前目錄
python -m pydeadwood .

# 掃描指定目錄，並以 JSON 輸出
python -m pydeadwood path/to/your/project --format json

# 試試內附範例（應報出 6 條，六種類型各 1 條）
python -m pydeadwood examples/sample_project
```

安裝為命令列工具（可選）：

```bash
pip install .
pydeadwood --help
```

## 📖 詳細使用指南

### 基本用法

```bash
pydeadwood [路徑 ...] [選項]
```

不傳路徑時預設掃描目前目錄。可以同時傳多個檔案或目錄，目錄會遞迴掃描，`.git`、`__pycache__`、`venv`、`.venv`、`build`、`dist` 等目錄會自動跳過。

### 選項一覽

| 選項 | 說明 |
| --- | --- |
| `--format text\|json` | 輸出格式，預設 `text` |
| `--exclude PATTERN` | 跳過符合該 glob 的檔案或目錄（可重複使用） |
| `--ignore-names PATTERN` | 永不報告符合該 glob 的名稱（可重複使用） |
| `--include-tests` | 同時報告測試函式／測試類別（預設排除，因為測試執行器不靠文字引用呼叫它們） |
| `--fail-on any\|unused\|unreachable\|none` | 哪些發現會使結束碼為 1，預設 `any` |
| `--version` | 顯示版本 |

### 結束碼

| 結束碼 | 含義 |
| --- | --- |
| `0` | 沒有達到 `--fail-on` 門檻的發現 |
| `1` | 發現了死碼 |
| `2` | 用法錯誤，例如掃描路徑不存在 |

### CI 接入範例

```bash
# 僅把不可達程式碼和死分支當作失敗條件，未用匯入只做提醒
pydeadwood src --fail-on unreachable

# 嚴格模式：任何發現都失敗
pydeadwood src --fail-on any
```

### JSON 輸出結構

```bash
pydeadwood src --format json
```

```json
{
  "summary": {
    "total": 2,
    "by_kind": {"unused-import": 1, "unused-function": 1},
    "by_severity": {"warning": 2}
  },
  "findings": [
    {
      "kind": "unused-import",
      "file": "src/a.py",
      "line": 1,
      "name": "os",
      "message": "unused import: import os",
      "severity": "warning"
    }
  ]
}
```

### 發現類型與嚴重級別

| 類型 | 嚴重級別 | 說明 |
| --- | --- | --- |
| `unused-import` | warning | 檔案內從未使用的匯入 |
| `unused-function` | warning | 專案內從未被引用的頂層函式 |
| `unused-class` | warning | 專案內從未被引用的類別（其方法不再重複報告） |
| `unused-method` | warning | 從未以屬性形式使用的類別方法 |
| `unreachable-code` | error | 終止陳述式之後的同區塊陳述式 |
| `dead-branch` | error | 恆為假／恆為真的常數分支 |
| `parse-error` | error | 無法解析的檔案（不會悄悄跳過） |

### 判斷規則（刻意保守）

- 一個名稱只要在專案任何位置出現過引用，就不算未用。寧可漏報，也不誤報。
- 方法只要其名稱曾以屬性形式出現（如 `obj.run()`、`self.run`），就算已用。
- 未用類別的方法不再單獨報告，避免同一處死碼重複刷屏。
- `from … import *` 和 `from __future__ import …` 永不報告：前者名字無法從匯入檔案推斷，後者是編譯期指令。
- 動態呼叫（`getattr`、反射、外掛註冊、字串拼接出的名字）無法被靜態分析看到——這類名稱請用 `--ignore-names` 豁免，或在 `__all__` 中宣告。

## 🧠 設計思路與迭代規劃

### 為什麼只做靜態分析

執行目標程式碼才能確認「是否被呼叫」，但那既慢又危險。PyDeadwood 選擇純 AST 靜態分析：速度快、可離線、可掃描不可信程式碼，代價是接受保守的漏報——這是有意為之的取捨。

### 架構

| 模組 | 職責 |
| --- | --- |
| 🧠 `pydeadwood/core.py` | AST 收集、跨檔案引用統計、七種發現的判定與排序 |
| 💻 `pydeadwood/cli.py` | 參數解析、文字／JSON 渲染、結束碼 |
| 🧪 `tests/` | 28 個單元測試，全部用暫存目錄建構獨立小專案 |

### 迭代規劃

- [ ] v1.1：支援未用模組級變數與未用參數的報告（預設關閉，避免噪音）
- [ ] v1.2：`--fix` 僅刪除未用匯入（仍不碰函式與類別），並先輸出 diff 供確認
- [ ] v1.3：設定檔 `pyproject.toml` 中的 `[tool.pydeadwood]` 小節
- [ ] v1.4：按檔案／目錄維度的統計摘要與基線檔案（只報告新增死碼）

## 📦 打包與部署指南

PyDeadwood 是工具庫類專案，**不發 Release**，按以下方式安裝使用：

```bash
# 方式一：從原始碼安裝
pip install .

# 方式二：直接用原始碼執行（無需安裝）
python -m pydeadwood <路徑>

# 方式三：作為函式庫呼叫
python - <<'PY'
from pydeadwood import analyze
for finding in analyze(["src"]):
    print(finding.file, finding.line, finding.kind, finding.name)
PY
```

### 環境要求

- Python ≥ 3.9
- 無第三方依賴
- 支援 macOS、Linux、Windows

### 本地開發與自測

```bash
python -m unittest discover -s tests -v
python -m pydeadwood pydeadwood   # 自檢，應輸出 No dead code found.
```

## 🤝 貢獻指南

歡迎提交 Issue 與 Pull Request：

1. Fork 本倉庫，建立特性分支。
2. 修改後確保 `python -m unittest discover -s tests -v` 全部通過。
3. 新判定規則必須同時附帶正例（應報告）與反例（不應報告）測試。
4. 保持零依賴與「只報告、不刪除」的原則。
5. 提交訊息遵循 Angular 規範，例如 `feat: add unused argument detection`。

## 📄 開源協議

本專案採用 [MIT](LICENSE) 協議。
