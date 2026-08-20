# zotero-annotations-cli

合并版 Zotero 批注命令行工具（**单一命令**）：读批注元数据，或读批注原文上下文
（前后 N 句），可导出全文 / PDF 副本。全程只读（元数据/批注走 Zotero 本地 API；
PDF 原文经 zotero-pdf-bridge 的 `/pdf-bridge/<itemKey>` 只读获取，不访问 Windows 文件系统）。

**CLI 是独立可执行文件，与 Python 完全解耦**：运行形态是 `zotero_annotations_cli`
（Windows 为 `zotero_annotations_cli.exe`），不需要安装 Python / PyMuPDF。
Python 脚本 `scripts/zotero_annotations_cli.py` 只是**构建源码**，不是运行方式。

> **零第三方依赖**：元数据模式只用 Python 标准库（argparse/base64/json/os/re/sys/
> tempfile/urllib），任何装了 Python 3 的机器直接 `python3 scripts/zotero_annotations_cli.py
> --key XXXX` 就能跑，无需安装任何东西；只有**上下文模式**（读 PDF 原文）需要 PyMuPDF，
> 且仅直接跑 `.py` 时需手动装（`pip install -r requirements.txt`）——正式分发的 exe 已内置。
> 缺依赖时上下文模式报 `ERROR 500 DEPENDENCY_MISSING`，元数据模式照常可用。

---

## 运行形态

| 形态 | 命令 | 说明 |
|---|---|---|
| 打包可执行文件（运行形态） | `zotero_annotations_cli --key AAAA0000`（Windows：`zotero_annotations_cli.exe`） | 免装 Python/PyMuPDF，可分发 |
| Python 源码（仅构建用） | — | 供 `build_exe.bat` / spec 打包，不直接运行 |

---

## 钩子（免审批）—— 匹配可执行文件本身

`hook/auto-allow-zotero-cli.py` 的放行白名单**只匹配打包后的可执行文件作为命令本身**：

```python
# 匹配：zotero_annotations_cli.exe / zotero_annotations_cli （可带任意路径前缀、可链式）
# 不匹配：cat ... / vim ... / echo ... （CLI 不是命令本身）
```

- **匹配可执行文件而非 Python**：CLI 已与 Python 解耦，运行的就是可执行文件；`.py`
  只是构建源码，不是调用方式，钩子无需（也不应）匹配它。
- **为什么全放行**：CLI 全程只读——只发本地 API GET，需要 PDF 时经 zotero-pdf-bridge
  只读取（base64，不碰 Windows 文件系统），绝不写库、不改 PDF、不下载。所有参数组合都安全。
- **安全边界**：若将来给 CLI 增加写/改数据的参数，必须收紧此钩子的白名单。

### 安装钩子

1. 把 `hook/auto-allow-zotero-cli.py` 复制到 `~/.zcode/hooks/`（或项目 `.zcode/hooks/`）。
2. 在 `~/.zcode/cli/config.json`（或 `<仓库>/.zcode/config.json`）的 `hooks` 块注册：

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

> 若你已有 PreToolUse 钩子（如敏感路径拦截），建议把放行逻辑**并入同一个脚本**，
> 保持单一决策点，避免多个钩子各自返回决策的组合歧义（详见仓库根 README）。

---

## 打包可执行文件

```bash
# 前提（一次，构建机上）
pip install pyinstaller pyinstaller-hooks-contrib pymupdf
# 打包（仓库根目录执行）
python -m PyInstaller zotero_annotations_cli.spec --noconfirm --clean
# 或 Windows 下直接运行 build_exe.bat
# 产物：dist\zotero_annotations_cli\zotero_annotations_cli.exe（整目录拷贝即分发）
```

- onedir 单一文件夹：启动快、免临时解压、更少杀毒误报；整目录拷贝到其它机器即可。
- 平台绑定：Windows 打的 exe 只能 Windows x64 跑；Linux/macOS 需在目标平台重打
  （产物为对应平台的裸可执行文件，钩子同样匹配）。
- 产物 `dist/`、`build/` 已在仓库 `.gitignore` 忽略，不提交。

---

## 用法

不给上下文参数即元数据模式；给了上下文参数（任一只）自动进入上下文模式：

```bash
# 元数据（不读 PDF）
zotero_annotations_cli --key AAAA0000
zotero_annotations_cli --key AAAA0000 --full --json

# 上下文（读 PDF）：--color / --ann-key / --before/--after / --fulltext / --export-pdf
zotero_annotations_cli --key AAAA0000 --color red
zotero_annotations_cli --key AAAA0000 --ann-key BBBB1111 --before 2 --after 2
zotero_annotations_cli --key AAAA0000 --fulltext --export-pdf
```

详细参数与输出格式见 `SKILL.md`。
