# zotero-annotations

## 这是什么

读你 Zotero 文献库里的**批注**，并回答这些问题的工具：

- **我标了什么？** 列出某篇文献的高亮/下划线/笔记，按颜色（红=重点、蓝=生词…）和页码展示。
- **这句话在原文哪、上下文是什么？** 从 PDF 提取高亮处前后 N 句，帮你理解你标的那句话。
- **能导出吗？** 导出某篇的全文纯文本 / PDF 副本，方便配合 PDF 阅读工具检索。

使用场景：读文献时做批注 → 让 AI 帮你回顾"标了什么、为什么标、上下文是什么"。

> 附带的合并版 CLI（`zotero-annotations-cli`）把"读元数据 + 读原文上下文 + 导出"合并成一个
> 独立可执行文件，可打包分发。

---

## 设计要点

- **不依赖任何 Zotero 插件**：只依赖 Zotero 桌面版自身的本地 API（端口 `23119`）是否开启；读批注元数据是纯标准库（`urllib` 发 HTTP GET），全程只读、绝不写库
- **两个 skill 功能不一致，按需选用**（详见下方"两个 skill 的区别"）：
  - `zotero-annotations`：**只读批注元数据**（轻量，Python 脚本，免审批）
  - `zotero-annotations-cli`：**完整版**（元数据 + 原文上下文 + 导出全文/PDF，打包为可执行文件）
- skill、CLI、钩子相互独立，可单独使用

### 如何开启 Zotero 本地 API（前置条件）

所有脚本只读 Zotero 桌面版自带的本地 API（`http://127.0.0.1:23119`）。使用前需在 Zotero 里
**开启本地服务**（默认关闭），步骤如下：

1. 打开 Zotero，进入设置：**Settings（偏好设置）→ Advanced（高级）→ Server（服务器）**。
2. 勾选 **"Allow other applications on this system to communicate with Zotero"**
   （允许本机其它应用与 Zotero 通信）。
3. **重启 Zotero** 使设置生效。

验证是否已开启：命令行执行 `curl http://127.0.0.1:23119/api/schema`，能返回 JSON 即正常
（浏览器直接访问 127.0.0.1 的原生 JSON 可能被当作文件下载或白屏，用命令行验证更直观）。

> - 只读、免 API key：该本地 API 无需配置密钥，仅本机可访问。
> - 脚本启动时会自动检测端口；若未开启会提示 `503 SERVICE_UNAVAILABLE`，
>   按上述步骤开启并重启即可。
> - 旧版 Zotero（7 之前）的入口在 **Settings → Advanced → General** 里，勾选同一选项。

---

## 它是如何工作的

整体分两层，各自独立：

### 第 1 层：读取批注 —— Zotero 本地 API（只读）

Zotero 桌面版自带一个 HTTP 本地服务：`http://127.0.0.1:23119`。它是**只读**的，也**不需要 API key**。数据层次大致是：

```
collections（集合） → items（条目/文献） → attachments（附件，PDF） → annotations（批注）
```

批注是 PDF 附件的子条目（`parentItem` 指向 PDF），每条包含：

| 字段 | 含义 | 示例 |
|---|---|---|
| `annotationType` | 类型 | `highlight` / `underline` / `note` |
| `annotationColor` | 颜色 | `#ff6666`（红）、`#ffd400`（黄）、`#2ea8e5`（蓝） |
| `annotationText` | 高亮/下划线的文字 | `highlight context` |
| `annotationComment` | 你写的批注 | `这里是批注` |
| `annotationPageLabel` / `annotationSortIndex` | 页码与排序 | `1234` |
| `annotationPosition` | 精确位置（JSON：pageIndex + rects） | 供读原文上下文时定位高亮处 |

### 第 2 层：免审批 —— ZCode PreToolUse 钩子返回 `approve`

ZCode 在每次工具调用前会先执行 `PreToolUse` 钩子（可配置）。钩子从 stdin 收到类似
`{"tool_name":"Bash","tool_input":{"command":"..."}}` 的 JSON，并可以返回一个**决策**：

| 钩子输出 / 退出码 | 效果 |
|---|---|
| `{"decision":"block"}` 或 exit 2 | 阻止该次调用 |
| `{"decision":"approve"}` | 直接放行，**跳过审批弹窗** |
| 无决策 + exit 0 | 不干预，照常走审批流程 |

> ⚠️ **decision 取值**：ZCode（v3.7.6）解析钩子 stdout 的 schema 里，顶层 `decision`
> 只接受 `{"approve","block"}`——`approve` 即放行、`block` 即阻止。写成 `"allow"`
> 不在枚举内，会**校验失败并被静默丢弃**（日志 `hook.run.failed`），弹窗照旧出现。
> 想让钩子"放行"必须用 `"approve"`。

---

## 目录结构

```
zotero-annotations/
├── README.md
├── LICENSE
├── skills/
│   ├── zotero-annotations/            # skill 1：只读批注元数据（纯标准库，免审批）
│   │   ├── SKILL.md
│   │   └── scripts/zotero_annotations.py
│   └── zotero-annotations-cli/        # skill 2：合并版 CLI（元数据 + 原文上下文）
│       ├── SKILL.md
│       ├── README.md                  # CLI 用法/钩子/打包说明
│       └── scripts/zotero_annotations_cli.py   # 构建源码（打包为可执行文件，不直接运行）
├── hook/
│   ├── auto-allow-zotero.py           # skill 1 免审批钩子（匹配 zotero_annotations.py）
│   └── auto-allow-zotero-cli.py       # skill 2 免审批钩子（匹配可执行文件，全放行）
├── zotero_annotations_cli.spec        # CLI 打包配置（onedir 单一文件夹）
├── build_exe.bat                      # 一键打包脚本（产物不提交仓库）
└── .gitignore                         # 忽略缓存 / __pycache__ / build / dist
```

---

## 安装

### 1. 安装 skill

把 `skills/zotero-annotations/` 或 `skills/zotero-annotations-cli/` 整个目录复制到任意 ZCode skills 目录：

| 作用域 | 路径（Windows） |
|---|---|
| 全局（所有项目） | `C:\Users\<用户名>\.agents\skills\<skill名>\` |
| 项目内 | `<仓库>\.agents\skills\<skill名>\` |

> 优先级：`<项目>/.zcode/skills` > `<项目>/.agents/skills` > `~/.zcode/skills` > `~/.agents/skills`。
> 同名 skill 只加载最先命中的一份。

### 2. （可选）安装免审批钩子

两个钩子二选一（按你要用的 skill）：
- 只用元数据（`zotero-annotations`）→ `hook/auto-allow-zotero.py`
- 用合并版 CLI（`zotero-annotations-cli`）→ `hook/auto-allow-zotero-cli.py`（对可执行文件全放行）

> **环境声明**：钩子基于 **ZCode v3.7.6** 构建并测试（`decision` 取值 `approve`/`block` 的
> schema 以该版本为准）。其它 ZCode 版本如需使用，请按你本地的钩子协议核对
> `decision` 取值与 `PreToolUse` 事件字段后自行配置；不同版本之间不保证完全兼容。

在 `~/.zcode/cli/config.json` 的 `hooks` 块注册（或在 `<仓库>/.zcode/config.json` 里做工作区级配置）：

```jsonc
{
  "hooks": {
    "enabled": true,
    "events": {
      "PreToolUse": [
        {
          "matcher": "Bash",
          "hooks": [
            { "type": "process", "command": "C:\\path\\to\\auto-allow-zotero-cli.py", "timeoutMs": 5000 }
          ]
        }
      ]
    }
  }
}
```

> **关于合并**：如果你已经有一个 PreToolUse 钩子（例如拦截敏感路径的
> `block-sensitive-paths.py`），建议把"放行逻辑"并进**同一个**脚本，保持单一决策点。

---

## 两个 skill 的区别（功能不一致，按需选用）

两个 skill **不是**同一功能的两种安装形态，而是**功能层级不同**：

| 能力 | `zotero-annotations` | `zotero-annotations-cli` |
|---|---|---|
| 读批注元数据（颜色/页码/批注文本） | ✅ | ✅ |
| 增量缓存 / 阅读定位 | ✅ | ✅ |
| 读原文上下文（高亮前后 N 句） | ❌ | ✅ |
| 导出全文 txt / PDF 副本 | ❌ | ✅ |
| 运行形态 | Python 脚本（`.py`） | 独立可执行文件（exe） |
| 免审批钩子 | 匹配 `.py` 脚本 | 匹配可执行文件 |

- **只要批注元数据** → 用 `zotero-annotations`（轻量，不碰 PDF）。
- **还要原文上下文 / 导出** → 用 `zotero-annotations-cli`（完整版）。

---

## 使用

### skill 1：`zotero-annotations`（只读批注元数据）

```bash
python3 skills/zotero-annotations/scripts/zotero_annotations.py --query "示例标题" [--collection "示例合集"]
python3 skills/zotero-annotations/scripts/zotero_annotations.py --key ASDFGHJK
python3 skills/zotero-annotations/scripts/zotero_annotations.py --key ASDFGHJK --full
```

### skill 2：`zotero-annotations-cli`（合并版，单一命令，独立可执行文件）

CLI 打包为独立可执行文件（Windows：`zotero_annotations_cli.exe`），与 Python 解耦，
运行的是可执行文件本身（`.py` 仅作构建源码）。不给上下文参数即元数据模式；
给了上下文参数自动进入上下文模式：

```bash
# 元数据（等同 skill 1，不读 PDF）
zotero_annotations_cli --key ASDFGHJK
zotero_annotations_cli --key ASDFGHJK --full --json

# 原文上下文（给了上下文参数即进入；读 PDF）
zotero_annotations_cli --key ASDFGHJK --color red
zotero_annotations_cli --key ASDFGHJK --ann-key AAAA0000 --before 2 --after 2
zotero_annotations_cli --key ASDFGHJK --fulltext --export-pdf
```

---

## 增量与缓存（对话模式省 token）

- **缓存目录优先级**：`--cache-dir`（显式）> 当前工作目录下 `.zotero-annotations/`（默认，跟随项目）> 系统 temp
- **建议 gitignore**：缓存默认落在工作目录时，建议把 `.zotero-annotations/` 加入项目的 `.gitignore`
- **始终提示缓存位置**：脚本 STATUS 行给出 `cache=路径`；落到 temp 时明确说明
- **增量**：元数据模式第一次读取全量并建缓存；之后只打印**新增/更新/删除**的批注
- **`--full`**：忽略缓存，强制全量输出
- **`--json`**：原始 JSON（含 `delta`、`reading`/`reading_prev` 与 `cache_path`）
- **阅读定位**：元数据模式自动输出 `### 阅读定位` 块，两种方法推测当前读到哪（不拉全文）——
  ① **方法1 新增分布**：本次新增/更新批注的页码范围；② **方法2 最远标记**：批注页码最大的一条。

---

## 输出与汇报

**成败汇报**：成功时 stdout 有机器可读状态行：

```text
STATUS: OK | mode=annotate | mode2=first|incremental|full | annotations=N | reading=pageN | cache=路径
STATUS: OK | mode=context | item=KEY | contexts=N | before=2 after=2 | fulltext_txt=... | pdf_copy=...
```

失败时 stderr **直接输出可读文字**，带 HTTP 风格错误码，例如：

```text
[zotero-annotations-cli] ERROR 404 NOT_FOUND: 没有匹配标题 'xxx' 的条目
[zotero-annotations-cli] ERROR 300 MULTIPLE_CHOICES: 标题 'scanning' 命中 8 条，有歧义。请用 --key 精确定位
```

| 文本码 | 含义 |
|---|---|
| 503 SERVICE_UNAVAILABLE | 端口 / 本地 API 不可用 |
| 404 NOT_FOUND | 集合或条目未找到 |
| 300 MULTIPLE_CHOICES | 标题歧义（列出候选 key） |
| 422 UNPROCESSABLE_ENTITY | 条目无 PDF 附件 |
| 404 PDF_NOT_FOUND | 本地找不到 PDF 文件（未同步/网页快照） |

> 进程退出码仅 `0` 成功 / `1` 失败（HTTP 码 >255 会被 shell 截断，故只放在文字里）。

**批注块（元数据模式，可 grep）**：

```text
<<<ANN key=XXXX color=red hex=#ff6666 page=3 type=highlight
TEXT: 高亮文字
COMMENT: 批注
>>>ANN
```

**上下文块（上下文模式，可 grep `<<<CTX`）**：

```text
<<<CTX key=XXXX color=red page=3
PHRASE: 高亮短语
COMMENT: 批注
  [S-2] 前第2句
>>> [S0] 所在句（含高亮）
  [S+1] 后第1句
>>>CTX
```

---

## 严格获取范围（Acquisition scope）

- **元数据模式**：只向 Zotero 本地 API 发 GET，读 `collections / items / attachments /
  annotations` 元数据。**不读 PDF**。
- **上下文模式**：读取 Zotero 本地存储里的 PDF（只读），按批注 `annotationPosition`
  精确定位高亮处，输出前后 N 句（PyMuPDF 已内置进 exe，无需另装）。
- **全程只读**：两种模式都不写库、不改 PDF、不下载。因此对应钩子对本 CLI **所有调用
  一律放行**（只读安全）。若将来给 CLI 增加写/改数据的参数，需重新收紧钩子白名单。
- ❌ **禁止**：插件的 `zotero.py` 助手、直接 `curl`/WebFetch 访问 Zotero 本地 API、
  下载/修改 PDF 本体、写库。

---

## 打包可执行文件（可选，方便分发/免装 Python）

CLI 打包为 onedir 单一文件夹（整目录自包含，免装 Python/PyMuPDF）：

```bash
# 前提（一次，构建机）
pip install pyinstaller pyinstaller-hooks-contrib pymupdf
# 打包（用仓库里的 spec）
python -m PyInstaller zotero_annotations_cli.spec --noconfirm --clean
# Windows 下也可直接运行 build_exe.bat
# 产物：dist\zotero_annotations_cli\zotero_annotations_cli.exe（整目录拷贝即分发）
```

- **产物不提交仓库**：`dist/`、`build/` 已在 `.gitignore` 忽略；仓库只保留
  `zotero_annotations_cli.spec` 与 `build_exe.bat`，需要时在目标机器重建。
- **坑与解决**（已在 spec 注释记录，2026-08-13 实测）：
  1. 两个脚本已**合并为单一入口**，打包无动态兄弟模块问题。
  2. PyMuPDF 需 `pyinstaller-hooks-contrib` 提供官方 hook；警告里 pandas/cppyy 等
     缺失均为可选功能，excludes 排除以减小体积。
  3. onedir（单一文件夹）：启动快、免临时解压、更少杀毒误报；要单文件可改回 onefile。
  4. 杀毒误报：PyInstaller 产物常见误报，加白名单即可。
  5. 平台绑定：Windows 打的 exe 只能 Windows x64 跑；跨平台要在目标平台重打。
- **exe 仍是本机工具**：照样要连本机 Zotero 本地 API + 读 `~/Zotero/storage/` 里的 PDF；
  exe 解决的是"免装 Python/PyMuPDF"，不是"脱离 Zotero 远程可用"。
- **钩子与 exe**：钩子匹配**可执行文件本身**（支持 Windows/Unix 路径前缀、链式命令），
  对本 CLI 所有调用一律放行（只读安全）。不匹配 `cat`/`vim`/`echo` 等其它用法。

---

## 是否泛用？

- **机制是通用的。** `PreToolUse 返回 approve` 的钩子模式适用于**任何你信任的只读命令**。
- **skill 是可移植的。** skill 目录零项目路径、纯标准库，拷贝到任何项目或全局都能用。
- **内容本身是专用的。** `zotero-annotations` 只做"读 Zotero 批注"；但
  "定位 → 提取 → 格式化"的骨架可以照抄，套用到其它数据源做成新 skill。

一句话：**骨架通用，血肉专用。**

---

## 故障排查

- **提示本地 API 不可用** → 在 Zotero 设置中开启本地服务并重启：
  Settings（Preferences）→ Advanced → Server → "Allow other applications on this system to communicate with Zotero"。
- **集合找不到** → 命令会把所有可用集合名列出来。
- **仍出现审批弹窗** → 确认钩子已启用（`hooks.enabled: true`）且已注册；
  或者把该命令加入 ZCode 权限白名单 / 调整权限模式。
