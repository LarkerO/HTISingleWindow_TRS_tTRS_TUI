# 开发与测试

[文档目录](README.md) · [项目首页](../README.md)

```bash
uv sync --locked --extra dev
uv run --locked pytest -q
uv run --locked ruff check src tests tools dev.py
uv run --locked ruff format --check src tests tools dev.py
```

自动化覆盖签名、响应篡改、幂等恢复、草稿持久化与版本冲突、键盘售退票、票面对齐与导出、小窗口布局，以及实时指标和网络探测。

真实后端只读检查，需要环境变量 TICKETING_API_KEY：

```bash
uv run --locked python tools/smoke_backend.py
```

真实 TUI 端到端检查需要 PHP、已配置的后端数据库和后端测试 fixture。默认后端源码位于本项目同级 backend/，也可通过 TTRS_BACKEND_DIR 指定：

```bash
uv run --locked python tools/live_backend.py
```

此工具创建独立测试机构、未来班次及临时旅客，验证实际出票、同键重试、查询、退票和库存恢复，最后清理并检查测试记录；不会输出密钥。详细报告仅写入忽略目录 .local/。

tools/preview.py 可导出真实界面的 SVG 供本地布局复核。运行时、订单库、生成报告和私有配置均不会进入 Git 仓库。

## 目录

```text
src/ttrs/
  app.py          主界面与业务流程
  screens.py      表单、选择窗口及电子票面
  client.py       HTTP、双向签名衔接和连接指标
  auth.py         HMAC-SM3-V1
  runtime.py      本地时钟、进程资源采样与状态格式
  store.py        持久化待办及幂等订单
  flow.py         往返和联程连续录入
  receipt.py      票面对齐与显式导出
  demo.py         进程内本地演示
tests/            自动化测试
tools/            本地验证与界面预览
docs/             设计、更新及对接验证说明
```
