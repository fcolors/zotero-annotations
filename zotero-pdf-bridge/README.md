# zotero-pdf-bridge

一个极小的 Zotero 9 插件：把 Zotero 自己管理的（imported/managed）PDF 附件，
通过 Zotero 本地 HTTP 服务（端口 `23119`）以 **base64 文本** 只读暴露出来。

## 为什么存在

隔离环境（WSL / 沙箱 agent）通常**没有 Windows 文件系统权限**：没有 `/mnt`、
没有 `C:`、也读不到 `~/Zotero/storage/`。本插件的意义只有一点：

> 让没有 Windows 文件系统权限的本地 agent，通过 Zotero 自身的授权边界，
> 只读获取 Zotero 管理的 PDF。

拿到的是 PDF 的 base64 文本，解码后作为字节流交给 PDF 解析库（如 PyMuPDF）
分析——agent 进程全程不接触 Windows 文件系统。

## Endpoints

```text
GET /pdf-bridge/ping
GET /pdf-bridge/<itemKey>
```

默认地址：`http://127.0.0.1:23119`。

- `/pdf-bridge/ping` 返回 JSON，例如：

```json
{
  "ok": true,
  "plugin": "zotero-pdf-bridge",
  "version": "0.2.2",
  "zotero": "9.0.6",
  "transport": "base64"
}
```

- `/pdf-bridge/<itemKey>`：
  - 接受 Zotero **parent item key**，也接受 **attachment item key**；
  - 是 parent item 时自动寻找其 PDF attachment；
  - **只允许** Zotero managed/imported PDF；**拒绝** linked-file；
  - 返回 PDF 的 base64 文本；解码后必须以 `%PDF-` 开头。

## 安装

```text
GitHub Releases
→ 下载 zotero-pdf-bridge.xpi
→ Zotero
→ Plugins / Add-ons
→ Install Add-on From File
```

本仓库不保存 `.xpi` 二进制；`zotero-pdf-bridge.xpi` 只作为 GitHub Release artifact
发布（源码目录已 gitignore `zotero-pdf-bridge/*.xpi`）。

## Build

需要 POSIX `zip`。在 `zotero-pdf-bridge/` 目录内执行：

```sh
./build.sh
# 产物：zotero-pdf-bridge.xpi（XPI 根目录直接是 manifest.json + bootstrap.js）
```

## Smoke test

推荐用 `curl`。不要以裸 PowerShell `Invoke-WebRequest` 作为首选，因为 Zotero
会对 browser-like User-Agent 做请求限制。

```sh
curl -fsS http://127.0.0.1:23119/connector/ping
curl -fsS http://127.0.0.1:23119/pdf-bridge/ping
```

实际 PDF（已知测试 key）：

```sh
KEY=G56EI7SD

curl -fsS \
  "http://127.0.0.1:23119/pdf-bridge/$KEY" \
  | base64 -d \
  > "$KEY.pdf"

head -c 5 "$KEY.pdf"
```

期望输出：

```text
%PDF-
```

## 安全边界

| 能力 | 允许 |
|---|---|
| metadata / annotation 读取 | ✓ |
| managed/imported PDF 读取 | ✓ |
| 任意 Windows 路径（`?path=C:\...`、`file://...`、`../`） | ✗ |
| linked-file 附件 | ✗ |
| Zotero DB 直接访问 / 写操作 | ✗ |

本插件刻意**不**扩展成通用文件服务器，也不支持任意路径读取；不要因为“方便”
增加 linked-file 支持。若未来需要，应作为单独明确设计，而不是顺手加入。
