# 🪵 PyDeadwood — Python 死代码扫描器

> 不运行你的代码，也能找出没人用的那部分。

[English](README.en.md) · [繁體中文](README.zh-TW.md) · 简体中文

PyDeadwood 是一个零依赖的 Python 死代码扫描工具：它只用标准库的 `ast` 解析代码、**绝不导入或执行目标代码**，哪怕扫描不可信代码也是安全的。它能找出未使用的导入、函数、类和方法，以及 `return` 之后的不可达代码和 `if False:` 这类常量死分支，并以文本或 JSON 输出，方便接进 CI。

## ✨ 核心特性

- 🔍 **未用导入检测**：`import` / `from … import`（含别名），星号导入永不误报
- 🧩 **未用定义检测**：顶层函数、类、方法，跨文件引用也会被算作“已使用”
- 🚫 **不可达代码检测**：`return` / `raise` / `break` / `continue` 之后的语句
- 🌿 **常量死分支检测**：`if False:`、`if True:` 的 `else`、`while False:`
- 🛡️ **只报告、不删除**：默认不改动任何文件，删代码的决定永远留给人
- 🧪 **低误报豁免**：`__all__` 公开导出、双下划线方法、`main`、测试函数与 `setUp/tearDown` 等生命周期方法默认不报
- 📄 **两种输出**：人类可读文本 + 机器可读 JSON，退出码可直接用于 CI 门禁
- 🪶 **零依赖**：仅 Python 标准库，Python ≥ 3.9 即可运行

## 🚀 快速开始

```bash
# 不需要安装任何第三方依赖
git clone https://github.com/gitstq/pydeadwood.git
cd pydeadwood

# 扫描当前目录
python -m pydeadwood .

# 扫描指定目录，并以 JSON 输出
python -m pydeadwood path/to/your/project --format json

# 试试自带示例（应报出 6 条，六种类型各 1 条）
python -m pydeadwood examples/sample_project
```

安装为命令行工具（可选）：

```bash
pip install .
pydeadwood --help
```

## 📖 详细使用指南

### 基本用法

```bash
pydeadwood [路径 ...] [选项]
```

不传路径时默认扫描当前目录。可以同时传多个文件或目录，目录会递归扫描，`.git`、`__pycache__`、`venv`、`.venv`、`build`、`dist` 等目录自动跳过。

### 选项一览

| 选项 | 说明 |
| --- | --- |
| `--format text\|json` | 输出格式，默认 `text` |
| `--exclude PATTERN` | 跳过匹配该 glob 的文件或目录（可重复使用） |
| `--ignore-names PATTERN` | 永不报告匹配该 glob 的名称（可重复使用） |
| `--include-tests` | 同时报告测试函数/测试类（默认排除，因为测试运行器不靠文本引用调用它们） |
| `--fail-on any\|unused\|unreachable\|none` | 哪些发现会使退出码为 1，默认 `any` |
| `--version` | 显示版本 |

### 退出码

| 退出码 | 含义 |
| --- | --- |
| `0` | 没有达到 `--fail-on` 阈值的发现 |
| `1` | 发现了死代码 |
| `2` | 用法错误，例如扫描路径不存在 |

### CI 接入示例

```bash
# 仅把不可达代码和死分支当作失败条件，未用导入只做提醒
pydeadwood src --fail-on unreachable

# 严格模式：任何发现都失败
pydeadwood src --fail-on any
```

### JSON 输出结构

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

### 发现类型与严重级别

| 类型 | 严重级别 | 说明 |
| --- | --- | --- |
| `unused-import` | warning | 文件内从未使用的导入 |
| `unused-function` | warning | 项目内从未被引用的顶层函数 |
| `unused-class` | warning | 项目内从未被引用的类（其方法不再重复报告） |
| `unused-method` | warning | 从未以属性形式使用的类方法 |
| `unreachable-code` | error | 终止语句之后的同块语句 |
| `dead-branch` | error | 恒为假/恒为真的常量分支 |
| `parse-error` | error | 无法解析的文件（不会悄悄跳过） |

### 判断规则（刻意保守）

- 一个名称只要在项目任何位置出现过引用，就不算未用。宁可漏报，也不误报。
- 方法只要其名称曾以属性形式出现（如 `obj.run()`、`self.run`），就算已用。
- 未用类的方法不再单独报告，避免同一处死代码重复刷屏。
- `from … import *` 和 `from __future__ import …` 永不报告：前者名字无法从导入文件推断，后者是编译期指令。
- 动态调用（`getattr`、反射、插件注册、字符串拼接出的名字）无法被静态分析看到——这类名称请用 `--ignore-names` 豁免，或在 `__all__` 中声明。

## 🧠 设计思路与迭代规划

### 为什么只做静态分析

运行目标代码才能确认“是否被调用”，但那既慢又危险。PyDeadwood 选择纯 AST 静态分析：速度快、可离线、可扫描不可信代码，代价是接受保守的漏报——这是有意为之的取舍。

### 架构

| 模块 | 职责 |
| --- | --- |
| 🧠 `pydeadwood/core.py` | AST 收集、跨文件引用统计、七种发现的判定与排序 |
| 💻 `pydeadwood/cli.py` | 参数解析、文本/JSON 渲染、退出码 |
| 🧪 `tests/` | 28 个单元测试，全部用临时目录构造独立小项目 |

### 迭代规划

- [ ] v1.1：支持未用模块级变量与未用参数的报告（默认关闭，避免噪音）
- [ ] v1.2：`--fix` 仅删除未用导入（仍不碰函数与类），并先输出 diff 供确认
- [ ] v1.3：配置文件 `pyproject.toml` 中的 `[tool.pydeadwood]` 小节
- [ ] v1.4：按文件/目录维度的统计摘要与基线文件（只报告新增死代码）

## 📦 打包与部署指南

PyDeadwood 是工具库类项目，**不发 Release**，按以下方式安装使用：

```bash
# 方式一：从源码安装
pip install .

# 方式二：直接用源码运行（无需安装）
python -m pydeadwood <路径>

# 方式三：作为库调用
python - <<'PY'
from pydeadwood import analyze
for finding in analyze(["src"]):
    print(finding.file, finding.line, finding.kind, finding.name)
PY
```

### 环境要求

- Python ≥ 3.9
- 无第三方依赖
- 支持 macOS、Linux、Windows

### 本地开发与自测

```bash
python -m unittest discover -s tests -v
python -m pydeadwood pydeadwood   # 自检，应输出 No dead code found.
```

## 🤝 贡献指南

欢迎提交 Issue 与 Pull Request：

1. Fork 本仓库，创建特性分支。
2. 修改后确保 `python -m unittest discover -s tests -v` 全部通过。
3. 新判定规则必须同时附带正例（应报告）与反例（不应报告）测试。
4. 保持零依赖与“只报告、不删除”的原则。
5. 提交信息遵循 Angular 规范，例如 `feat: add unused argument detection`。

## 📄 开源协议

本项目采用 [MIT](LICENSE) 协议。
