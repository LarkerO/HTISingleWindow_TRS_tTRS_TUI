# 氢气工艺服务器交通信息单一窗口 tTRS

面向 MTR 电子客票后端的键盘优先终端售票客户端，使用 Python、Textual 和 HTTPX，支持 Unicode / ASCII 线框。

## 功能

- 车站、车次、余票和逐站时刻查询。
- 旅客证件管理、出票、查票与整票退票。
- 往返／联程连续录入，待办保存和断线恢复。
- 电子票面导出，以及时间、网络和资源状态监控。

支付、指定席位及改签等功能需后端支持，目前暂不可用。

## 快速启动

安装 [uv](https://docs.astral.sh/uv/) 后，在项目目录运行：

```bash
uv sync --locked
uv run --locked ttrs
```

本地体验：`uv run --locked ttrs --demo --ascii`。连接真实后端请按 `Ctrl+O`。

## 文档

- [安装与连接](docs/getting-started.md)
- [使用教程与快捷键](docs/user-guide.md)
- [配置与窗口版本](docs/configuration.md)
- [状态栏、数据与恢复机制](docs/runtime-and-recovery.md)
- [开发与测试](docs/development.md)
- [真实后端对接验证](docs/integration-verification.md)
- [全部文档与更新记录](docs/README.md)
