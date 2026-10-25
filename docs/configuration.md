# 配置与窗口版本

[文档目录](README.md) · [项目首页](../README.md)

将 [配置示例](../config.example.toml) 复制为 config.local.toml，可调整服务地址、版本、外观、超时和附加快捷键。API 密钥通过连接窗口或 TICKETING_API_KEY 环境变量提供，不写入配置文件。

## 窗口标题与本地版本

窗口标题格式为：

```text
氢气工艺服务器交通信息单一窗口 HydCraft Server Transit Information Single Windows tTRS | 0.4.0
```

默认版本号读取随程序安装的 src/ttrs/version.toml。可在本地 config.local.toml 或 --config 指定的 TOML 中设置 version = "0.4.0" 覆盖，不需要修改 Python 源码。配置优先级为：显式 --config → 工作目录 config.local.toml → 程序默认配置。启动脚本会将工作目录切到项目根目录。

主界面保留简短中文标头，并显示同一个配置版本号；按键诊断窗口也使用完整窗口标题。

## 指定配置

```bash
uv run --locked ttrs --config config.local.toml
```

[keys] 中的配置为动作附加按键，顶部按钮同步显示首个配置键名。完整默认键位见 [使用教程](user-guide.md#快捷键)。数据目录可通过 TTRS_STATE_DIR 指定，详见 [恢复机制](runtime-and-recovery.md#待办与断线恢复)。
