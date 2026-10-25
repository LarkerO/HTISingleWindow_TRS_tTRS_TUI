# 安装与连接

[文档目录](README.md) · [项目首页](../README.md)

## 快速开始

需要 Python 3.12+。推荐使用 [uv](https://docs.astral.sh/uv/) 管理 Python 和依赖。

```bash
git clone https://github.com/LarkerO/HTISingleWindow_TRS_tTRS_TUI.git
cd HTISingleWindow_TRS_tTRS_TUI
uv sync --locked
uv run --locked ttrs
```

第一次同步时，uv 可按 .python-version 准备 Python 3.12。连接真实后端时不加 --demo。

本地体验：

```bash
uv run --locked ttrs --demo
uv run --locked ttrs --demo --ascii
uv run --locked ttrs --keys
```

本地演示不访问后端，使用内存数据，退出即清空。默认选择西安到南京，可按 **F12 → Enter → Alt+N**，确认后体验出票。

建议使用 Windows Terminal，窗口为 120 列 × 36 行。80×24 小窗口会自动使用紧凑布局，长表格和弹窗内容可以滚动。

### 使用 pip 安装

Linux / WSL：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m ttrs
```

Windows PowerShell：

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -e .
.\run.cmd
```

Windows 也可用 run.ps1，受 PowerShell 签名策略限制时使用 run.cmd。Linux / WSL 可用 sh run.sh。Windows 和 Linux 虚拟环境不能共用。

## 连接已有系统

1. 启动原电子客票后端，确认服务地址可达。
2. 在 tTRS 按 **Ctrl+O** 或选择“连接”。
3. 输入地址，例如 http://127.0.0.1:8000，以及后端分配的 API 密钥。
4. 管理员可填写代操作出票方代码；普通出票方密钥留空即可。
5. 连接成功后选择车站、日期和旅客，查询余票并出票。

密钥输入框隐藏明文。也可通过进程环境变量 TICKETING_API_KEY 提供密钥。客户端不会自动读取后端 .env，也不会将密钥保存到 TOML、订单数据库、导出文件或日志中。运营方密钥不能用于出票窗口。

所有业务请求使用 **HMAC-SM3-V1 双向认证**。客户端对实际 URL 和请求字节签名，先校验原始响应签名再使用数据。正常部署应使用 HTTPS，双方时钟需同步。

复制 config.example.toml 为 config.local.toml，可设置服务地址、出票方、外观、超时和附加快捷键：

```bash
uv run --locked ttrs --config config.local.toml
```

下一步：[使用教程与快捷键](user-guide.md)。
