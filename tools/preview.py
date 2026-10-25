"""Export real Textual rendering for visual QA; never connects to a real API."""

import asyncio
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))
if os.name == "nt" and sys.prefix == sys.base_prefix and (root / ".deps").is_dir():
    sys.path.insert(0, str(root / ".deps"))

os.environ.pop("NO_COLOR", None)
os.environ["TEXTUAL_COLOR_SYSTEM"] = "truecolor"

from ttrs.app import TicketApp
from ttrs.config import Config
from ttrs.screens import ReceiptScreen


async def main():
    output = root / ".local"
    output.mkdir(exist_ok=True)
    for ascii_mode in (False, True):
        app = TicketApp(Config(ascii=ascii_mode), demo=True)
        async with app.run_test(size=(120, 36)) as pilot:
            for _ in range(100):
                await pilot.pause(0.02)
                if app.client and not app.busy:
                    break
            await pilot.press("f12")
            for _ in range(100):
                await pilot.pause(0.02)
                if app.journeys and not app.busy:
                    break
            await pilot.press("enter")
            for _ in range(100):
                await pilot.pause(0.02)
                if app.drafts and not app.busy:
                    break
            name = "preview-ascii.svg" if ascii_mode else "preview.svg"
            app.save_screenshot(name, path=str(output))
            print(output / name)
            await pilot.press("alt+e", "ctrl+y")
            for _ in range(100):
                await pilot.pause(0.02)
                if not app.busy:
                    break
            await pilot.press("f12")
            for _ in range(100):
                await pilot.pause(0.02)
                if app.journeys and not app.busy:
                    break
            await pilot.press("enter")
            for _ in range(100):
                await pilot.pause(0.02)
                if app.flow.earliest and not app.busy:
                    break
            mode_name = "preview-roundtrip-ascii.svg" if ascii_mode else "preview-roundtrip.svg"
            app.save_screenshot(mode_name, path=str(output))
            await pilot.press("alt+n")
            await pilot.pause()
            await pilot.click("#yes")
            await pilot.pause()
            assert isinstance(app.screen, ReceiptScreen), "Receipt preview did not open"
            ticket_name = "preview-ticket-ascii.svg" if ascii_mode else "preview-ticket.svg"
            app.save_screenshot(ticket_name, path=str(output))
            await pilot.press("escape")


if __name__ == "__main__":
    asyncio.run(main())
