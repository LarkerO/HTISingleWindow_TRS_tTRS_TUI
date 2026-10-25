import argparse
from pathlib import Path

from . import APP_TITLE
from .app import TicketApp
from .config import Config


def main():
    parser = argparse.ArgumentParser(description=APP_TITLE)
    parser.add_argument("--demo", action="store_true", help="本地模拟 API，无需密钥，不访问后端")
    parser.add_argument("--ascii", action="store_true", help="使用 + - | ASCII 边框")
    parser.add_argument("--keys", action="store_true", help="按键诊断，不启动售票")
    parser.add_argument("--config", type=Path, help="TOML 配置文件")
    args = parser.parse_args()
    try:
        config = Config.load(args.config)
        config.ascii = config.ascii or args.ascii
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    if args.keys:
        from .keys import KeyApp

        KeyApp(title=config.window_title).run()
        return
    TicketApp(config, demo=args.demo).run()


if __name__ == "__main__":
    main()
