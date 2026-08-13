---
name: zotero-annotations-cli
description: Zotero 批注命令行工具（独立可执行文件，与 Python 解耦）——一条命令读批注元数据，或读批注原文上下文（前后 N 句），可导出全文/PDF 副本。当用户问"某篇文献的批注/标注/高亮"、"这条/这个颜色批注的原文上下文/前后几句/解释一下"、"导出某篇 PDF 的全文或副本"时使用。运行的是打包后的可执行文件 zotero_annotations_cli（Windows 为 .exe）。
---

# Zotero 批注 CLI（独立可执行文件）

CLI 打包后为**独立可执行文件**，与 Python 完全解耦：运行 `zotero_annotations_cli`（Windows 下
`zotero_annotations_cli.exe`），不需要 Python/PyMuPDF。合并了"读批注元数据"与"读批注原文
上下文"为**一个命令**：给上下文参数就自动进入上下文模式，否则是元数据模式。全程只读
（Zotero 本地 API + 本地 PDF），对应钩子对本命令**所有调用全放行**（只读安全）。

## 可执行文件位置

本 skill 的 `scripts/` 目录下放的就是**打包好的可执行文件**（onedir 目录，exe 依赖同目录
`_internal/`，勿单独移动）。按 skill 规范，AI 加载本 skill 后优先启动 `scripts/` 下的
可执行文件：

- 全局安装后：`<skill目录>/scripts/zotero_annotations_cli/zotero_annotations_cli.exe`

```bash
# 调用方式（Windows）
<skill目录>/scripts/zotero_annotations_cli/zotero_annotations_cli.exe --key AAAA0000
```

> 定位方式任选其一：`--key`（最快最精确）/ `--query` / `--query --collection`。
> `scripts/` 下只有可执行文件（exe），不包含 .py 源码；构建源码只存在于仓库
> `skills/zotero-annotations-cli/scripts/zotero_annotations_cli.py`，仅用于打包，不是运行形态。

## 元数据模式（默认）

不读 PDF，纯标准库逻辑，增量缓存。只要**不给**上下文参数即进入：

> 以下示例中 `zotero_annotations_cli` 均指本 skill 内的可执行文件
> `<skill目录>/scripts/zotero_annotations_cli/zotero_annotations_cli.exe`（Windows）。

```bash
zotero_annotations_cli --key AAAA0000
zotero_annotations_cli --query "示例标题" --collection 示例合集
zotero_annotations_cli --key AAAA0000 --full     # 忽略缓存全量输出
zotero_annotations_cli --key AAAA0000 --json
```

## 上下文模式（给了上下文参数任一只即进入）

按批注的精确位置（`annotationPosition`）从 PDF 提取高亮处所在句及前后 N 句。
**只在用户明确要求看批注原文/前后几句/解释时使用**；会读取 Zotero 本地存储的 PDF（只读）。

```bash
zotero_annotations_cli --key AAAA0000 --color red
zotero_annotations_cli --key AAAA0000 --ann-key BBBB1111 --before 2 --after 2
zotero_annotations_cli --key AAAA0000 --fulltext --export-pdf
zotero_annotations_cli --key AAAA0000 --color red --json
```

## 参数

- 定位：`--query` / `--collection` / `--key`（必选其一）
- 通用：`--json`（原始 JSON）、`--cache-dir`（缓存目录）
- 元数据模式：`--full`（全量）、`--no-color`（不分组）
- 上下文模式：`--color NAME|HEX`（颜色，可多次）、`--ann-key KEY`（批注 key，可多次）、
  `--before N / --after N`（前/后句数，默认 2/2，共 5 句）、`--fulltext`（导出全文 txt）、
  `--export-pdf`（复制 PDF 副本）

## 缓存目录

优先级：`--cache-dir`（显式）> 当前工作目录 `.zotero-annotations/`（默认，跟随项目）> 系统 temp。
**必须向用户提示缓存位置**：STATUS 行有 `cache=路径`；落到 temp 时明确说明。

## 输出与汇报

- **成败汇报**：成功时 stdout 有 `STATUS: OK | mode=annotate|context | ...`；失败时 stderr 有 `[zotero-annotations-cli] ERROR <HTTP码> <LABEL>: 文字`。
- **批注块（元数据模式，可 grep）**：
  ```text
  <<<ANN key=XXXX color=red hex=#ff6666 page=3 type=highlight
  TEXT: 高亮文字
  COMMENT: 批注
  >>>ANN
  ```
  定位：`grep '^<<<ANN'` 全部；`grep 'color=red'` 按颜色；`grep 'page=3'` 按页。
- **上下文块（上下文模式，可 grep `<<<CTX`）**：
  ```text
  <<<CTX key=XXXX color=red page=3
  PHRASE: 高亮短语
  COMMENT: 批注
    [S-2] 前第2句
  >>> [S0] 所在句（含高亮）
    [S+1] 后第1句
  >>>CTX
  ```
- **阅读定位（元数据模式自动输出 `### 阅读定位`）**：方法2 最远标记（批注页码最大的一条）+
  方法1 新增分布（本次新增批注的页码范围），推测用户读到哪，不拉全文。STATUS 行含 `reading=pageN`。

## 阻塞处理（以 stderr 文字里的 HTTP 风格码为准）

| 文本码 | 含义 | 处理 |
|---|---|---|
| 503 SERVICE_UNAVAILABLE | 端口/本地 API 未开 | 让用户在 Zotero 开启本地服务并重启（Settings→Advanced→Server→Allow...）。**不要**用插件 zotero |
| 404 NOT_FOUND | 集合/条目未找到 | 转告命令输出的文字；集合不存在会列出可用集合名 |
| 300 MULTIPLE_CHOICES | 标题歧义 | 命令列出候选 key，请用户用 `--key` 指定 |
| 422 UNPROCESSABLE_ENTITY | 条目无 PDF 附件 | 如实说明，可能只有网页快照 |
| 404 PDF_NOT_FOUND | 本地找不到 PDF 文件 | 附件可能未同步或为网页快照 |

## 钩子

`hook/auto-allow-zotero-cli.py` 对本可执行文件的**所有调用**（元数据 + 上下文 + 导出）一律放行，
因为整个命令只读（只发本地 API GET + 读本地 PDF），安全边界成立。它**只匹配可执行文件
作为命令本身**（支持 Windows/Unix 路径前缀、链式命令），不匹配 `cat`/`vim`/`echo` 等其它用法。
若将来给 CLI 增加写/改数据的参数，需重新收紧钩子白名单。

## 构建可执行文件

CLI 由源码 `scripts/zotero_annotations_cli.py` 打包而来（Python 脚本仅作构建源码，不是运行形态）。
在仓库根目录运行 `build_exe.bat`（或 `python -m PyInstaller zotero_annotations_cli.spec --noconfirm --clean`），
产物为 onedir 单一文件夹 `dist/zotero_annotations_cli/`（含 exe 与依赖），整目录拷贝即分发。
