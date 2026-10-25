# 氢气工艺服务器交通信息单一窗口 tTRS

tTRS 是 MTR 电子客票后端的终端售票客户端，使用 Python、Textual 和 HTTPX，参考 sTRS 的固定窗口与键盘操作方式。主界面提供日期、车次、发到站、旅客录入、余票表、待办表和实时状态栏，支持 Unicode 及 ASCII 线框。

本项目通过 HTTP API 连接已有的 ThinkPHP / MariaDB 电子客票系统，不直接访问业务数据库。核心售票链路已经过真实后端验证，详见 [对接验证记录](docs/integration-verification.md)。

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

## 窗口标题与本地版本

窗口标题格式为：

```text
氢气工艺服务器交通信息单一窗口 HydCraft Server Transit Information Single Windows tTRS | 0.4.0
```

默认版本号读取随程序安装的 src/ttrs/version.toml。可在本地 config.local.toml 或 --config 指定的 TOML 中设置 version = "0.4.0" 覆盖，不需要修改 Python 源码。配置优先级为：显式 --config → 工作目录 config.local.toml → 程序默认配置。启动脚本会将工作目录切到项目根目录。

主界面保留简短中文标头，并显示同一个配置版本号；按键诊断窗口也使用完整窗口标题。

## 售票流程

1. **选择区间**：F1 输入日期，F2 可填车次，F3 / F4 选择发站和到站。
2. **选择旅客**：F5 输入姓名，或从证件库查询、登记并选择证件。
3. **查询余票**：F12 查询，方向键选择具体班次。
4. **取入待办**：Enter 或 Alt+R 保存当前区间与旅客。
5. **核对出票**：在待办表中选行，Alt+N 确认出票。
6. **查票退票**：已出票记录按 Enter，或 Ctrl+G 输入票号查询。

车站支持站名、拼音、拼音首字母及完整站 ID；超过服务端目录上限时，可在选择窗口按中文名称向服务器重新查询。车次号不是唯一主键，出票使用真实班次 ID 和停站序号。

日期支持 YYYY-MM-DD、YYYYMMDD、日简码和相对天数。例如 30 是从当前 UTC 日期起最近的 30 日，+1 是 UTC 明天。完整日期允许查询已导入的历史运营日，实际查询日期显示在余票表标题。

**待办不锁库存，不代表已收款。** 余票和票价是查询快照，出票仍由后端检查机构权限、发车时间、库存和报价版本。

### 往返与联程

- **Ctrl+Y 往返**：取入首程后自动交换发到站，取入返程后回到普通模式。
- **Ctrl+L 联程**：下一程发站沿用上一程到站，F4 选择新的到站。
- 后续出发时间不得早于上一程到达，支持跨午夜。
- **Alt+S** 返回普通售票，**F6** 通过菜单选择模式。
- **Alt+M** 修改未提交待办的旅客姓名或证件库 ID。

各程独立计价和出票，不提供通票票价、整体原子交易或联程保障。

## 快捷键

| 按键 | 功能 |
| --- | --- |
| F1 / F2 | 日期 / 车次 |
| F3 / F4 / F5 | 发站 / 到站 / 旅客 |
| F6 | 选择业务模式 |
| Ctrl+P / F8 | 证件库 / 帮助（主界面） |
| F9 | 切换余票与待办表 |
| F10 / F12 | 菜单 / 查询余票 |
| Enter | 当前表格取入待办或打开订单；表单下一项 |
| Alt+R / Alt+N / Alt+E | 取入待办 / 出票 / 取消未提交待办 |
| Alt+M | 修改未提交待办旅客 |
| Ctrl+Y / Ctrl+L / Alt+S | 往返 / 联程 / 普通售票 |
| Ctrl+O / Ctrl+G | 连接 / 查票与退票 |
| Ctrl+F12 | 逐站时刻 |
| Ctrl+Q / Ctrl+C | 主界面退出 |
| 表单 F1–F7 / F8 / Esc | 定位字段 / 提交 / 返回 |
| 票面 F7 / F8 | 原始数据 / 导出 |

顶部按钮直接显示快捷键：菜单 F10、业务 F6、连接 Ctrl+O、证件 Ctrl+P、查退 Ctrl+G、帮助 F8、退出 Ctrl+Q。小窗口用 ^ 表示 Ctrl，例如 ^Q。附加键位配置会同步更新按钮显示。

快捷键按当前窗口生效，普通字母可正常输入。所有业务也有按钮或菜单入口。笔记本功能键可能需要 Fn；终端可能截获 F11、Alt 或 Ctrl 组合键。用 --keys 查看程序实际收到的键名，再通过配置增加替代键。

## 实时状态栏

底部显示运行信息，不再显示原先的演示测试文案：

| 指标 | 含义 |
| --- | --- |
| 本地时间 | 跟随运行电脑的本地时区，每秒刷新，并显示 UTC 偏移 |
| 本张票号 | 当前选中或正在查看的实际票号；草稿显示待生成，结果未知显示待确认 |
| 下一张票号 | 原后端在出票时随机生成，显示“出票时生成”，不虚构递增号码 |
| 累计操作 | 当前会话的用户指令次数；失败或取消也计入，菜单选择只计一次；后台探测不计入 |
| 网络 | 到所连接后端的连通状态，可显示未连接、断开、服务异常或验签异常 |
| 服务器往返 | 最近一次 HTTP 往返耗时，包含服务器处理；不是单独的 ICMP Ping |
| 上次服务处理 | 最近业务响应中已验签的 X-Process-Time-Ms，后台健康探测不会覆盖 |
| 客户端 CPU | 当前 tTRS 进程的非阻塞 CPU 采样，多核忙碌时可能超过 100% |
| 内存 RSS | 当前 tTRS 进程驻留内存，单位 MiB |

健康探测每 10 秒执行一次，单次超时 3 秒，不办理业务。CPU 与内存每秒采样，缺少可信数据时显示 —。本地演示没有远端网络，显示“本地”，不把模拟响应耗时当作真实服务器指标。

**售票日期与列车时刻仍保持 API 的 UTC。** 本地时区只用于运行时钟，不能将状态栏时间直接当作列车发车时间。

## 待办与断线恢复

取入、修改、取消待办都会立即保存到本地 SQLite。退出或切换服务与出票方不会丢弃记录，重新连接相同服务和出票方即可恢复。录入模式重置为普通售票，下一程输入栏不会自动恢复。

确认出票时，在同一个事务内将当前版本草稿转成固定请求和幂等键。数据库写入失败整体回滚，陈旧窗口不能重复提交同一待办。

网络中断、验签失败或服务端 5xx 后保留“待确认”。已验签的后端 4xx 拒绝单独保存错误原因。重试沿用原请求和幂等键，同时生成新签名时间戳和 nonce。不要另建相同待办猜测出票结果。

已提交记录不能按草稿取消或修改。已出票客票通过查票办理整票退票，状态以后端最新结果为准。多张待办不是原子交易，可能部分成功。

默认数据位置：

- Windows：%LOCALAPPDATA%\tTRS\orders.sqlite3。
- Linux / WSL：$XDG_STATE_HOME/tTRS/orders.sqlite3，未设置时为 ~/.local/state/tTRS/orders.sqlite3。
- TTRS_STATE_DIR 可覆盖数据目录。
- 本地演示使用内存数据库。

本地订单库含旅客、证件库 ID 和客票快照，应按业务数据管理访问权限、备份和保留周期。

## 电子票面与导出

票面展示票号、PNR、旅客、票价、区间、车次、发到时刻、站序与出票方。缺少的服务端字段显示“未提供”，不生成虚构席位。

F8 选择 .txt 或 .json 完整路径，默认位于数据目录的 receipts/。TXT 遮蔽证件号码，JSON 包含完整后台数据，可能包括证件快照。导出由用户主动触发，已有文件不会覆盖。

票面核对单不是实体纸票或付款凭证。状态可能随退票等操作变化，请以服务器最新查询为准。

## 当前边界

原后端尚未提供指定席位、用途票额、学生等优惠定价、真实支付、改签、通票签证、实体制票机和交班结算。这些功能仍不可办理，F7 读证件设备也尚未接入。

车站目录单次最多 500 条，区间查询最多 200 条，过多时应缩小条件。站名拼音查询不等于铁路电报码。

## 开发与验证

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
