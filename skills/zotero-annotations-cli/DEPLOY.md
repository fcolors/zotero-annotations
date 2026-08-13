# zotero-annotations-cli — Release 部署说明

> 环境：本包基于 **ZCode v3.7.6** 构建并测试。Zotero 桌面版需开启本地 API 服务。
> 版本：2026-08-13

## 这是什么

`zotero-annotations-cli` 是一个**独立的只读命令行工具**：读取 Zotero 文献 PDF 里的批注
（高亮/颜色/批注文本），并可从 PDF 提取批注原文上下文（前后 N 句）、导出全文 / PDF 副本。

- **与 Python 解耦**：运行形态是打包好的可执行文件 `zotero_annotations_cli.exe`，不需要
  安装 Python / PyMuPDF。
- **全程只读**：只连本机 Zotero 本地 API（端口 23119）+ 读本地 Zotero 存储里的 PDF，
  不写库、不改 PDF、不下载。

## 部署其实就是两件事

1. **装 skill**（让 AI 知道这个工具怎么用）
2. **加一个免审批钩子**（让 AI 调用它时不弹审批窗）

没有数据库、没有服务、没有配置文件要改。

---

## 第 1 步：安装 skill

把本包里的 `skills/zotero-annotations-cli/` 整个目录复制到任意 ZCode skills 目录：

| 作用域 | 路径（Windows 示例） |
|---|---|
| 全局（所有项目） | `C:\Users\<用户名>\.agents\skills\zotero-annotations-cli\` |
| 项目内 | `<仓库>\.agents\skills\zotero-annotations-cli\` |

> ZCode 的 skill 查找优先级：`<项目>/.zcode/skills` > `<项目>/.agents/skills` >
> `~/.zcode/skills` > `~/.agents/skills`。同名 skill 只加载最先命中的一份。

## 第 2 步：安装免审批钩子（可选，推荐）

钩子 `hook/auto-allow-zotero-cli.py` 对本 CLI 的**所有调用一律放行**（因为命令只读安全）。
它匹配的是**可执行文件本身**（`zotero_annotations_cli.exe` / 裸二进制），不匹配
`cat`/`vim`/`echo` 等其它用法。

### 2a. 复制钩子文件

```bash
# Windows（把 <用户名> 换成你的）
copy hook\auto-allow-zotero-cli.py C:\Users\<用户名>\.zcode\hooks\
```

### 2b. 注册到 config.json

在 `~/.zcode/cli/config.json`（用户级）或 `<仓库>/.zcode/config.json`（工作区级）的
`hooks` 块加一条 `PreToolUse`：

```jsonc
{
  "hooks": {
    "enabled": true,
    "events": {
      "PreToolUse": [
        {
          "matcher": "Bash",
          "hooks": [
            {
              "type": "process",
              "command": "C:\Users\<用户名>\.zcode\hooks\auto-allow-zotero-cli.py",
              "timeoutMs": 5000
            }
          ]
        }
      ]
    }
  }
}
```

> **如果已有 PreToolUse 钩子**（例如敏感路径拦截 `block-sensitive-paths.py`）：
> 建议把本钩子的 `ALLOW_PATTERNS` 放行逻辑**并入同一个脚本**，保持单一决策点，
> 避免多个钩子各自返回决策时产生组合歧义。本项目正是这样做的。

### 2c. 环境兼容性

钩子基于 **ZCode v3.7.6** 测试：其输出协议的 `decision` 取值是 `{"approve","block"}`
（`approve` = 放行、`block` = 阻止；写成 `"allow"` 不在枚举内会被静默丢弃）。
**其它 ZCode 版本**请先核对你本地的钩子协议（`decision` 取值、`PreToolUse` 事件字段）
再使用，跨版本不保证完全兼容。

---

## 第 3 步：使用

运行形态（`<dist> = 本包里的 bin`）：

```bash
# 元数据模式（默认，不读 PDF）
<dist>\zotero_annotations_cli.exe --key AAAA0000
<dist>\zotero_annotations_cli.exe --key AAAA0000 --full --json

# 上下文模式（给了上下文参数即进入；读 PDF）
<dist>\zotero_annotations_cli.exe --key AAAA0000 --color red
<dist>\zotero_annotations_cli.exe --key AAAA0000 --ann-key BBBB1111 --before 2 --after 2
<dist>\zotero_annotations_cli.exe --key AAAA0000 --fulltext --export-pdf
```

定位参数三选一：`--key`（最快最精确）/ `--query` / `--query --collection`。
详细参数与输出格式见 `skills/zotero-annotations-cli/SKILL.md`。

### 前置条件

- Zotero 桌面版运行中，且已开启本地 API：
  Settings（Preferences）→ Advanced → Server → "Allow other applications on this
  system to communicate with Zotero"，然后重启 Zotero。
- 文献要有 PDF 附件，且 PDF 已在本地（Zotero 存储同步完成）。

---

## 包内容

```
zotero-annotations-cli-release/
├── DEPLOY.md                     # 本文件（部署说明）
├── bin/                          # 可执行文件（onedir 单一文件夹，整目录拷贝即用）
│   └── zotero_annotations_cli/
│       ├── zotero_annotations_cli.exe
│       └── _internal/            # 运行时依赖（不要单独移动 exe）
├── skills/
│   └── zotero-annotations-cli/   # skill（SKILL.md + README.md + 构建源码）
│       ├── SKILL.md
│       ├── README.md
│       └── scripts/zotero_annotations_cli.py   # 构建源码（不直接运行）
└── hook/
    └── auto-allow-zotero-cli.py  # 免审批钩子
```

> **不要把 exe 单独拷走**：`zotero_annotations_cli.exe` 依赖同目录 `_internal/`，
> 必须整个 `bin/zotero_annotations_cli/` 目录一起拷贝/压缩。

## 重新构建（可选）

源码在 `skills/zotero-annotations-cli/scripts/zotero_annotations_cli.py`。如需自行打包：

```bash
pip install pyinstaller pyinstaller-hooks-contrib pymupdf
python -m PyInstaller zotero_annotations_cli.spec --noconfirm --clean
```

产物为 `dist/zotero_annotations_cli/`。平台绑定：Windows 打的 exe 只能 Windows x64 跑；
Linux/macOS 需在对应平台重新打包（产物为裸可执行文件，钩子同样匹配）。
