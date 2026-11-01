#!/usr/bin/env python3
"""Upload the approved Probe avatar to the dedicated bot. Token stays local."""
import getpass
import io
import json
import os
from pathlib import Path

import httpx
from PIL import Image


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or getpass.getpass("Telegram bot token (hidden): ").strip()
    if not token:
        raise SystemExit("A local bot token is required.")
    # Telegram's static profile-photo API requires JPG. Convert the generated art for transport.
    source = Image.open(Path(__file__).resolve().parents[1] / "web/public/probe.png").convert("RGBA")
    background = Image.new("RGB", source.size, "#121211")
    background.paste(source, mask=source.getchannel("A"))
    output = io.BytesIO()
    background.save(output, format="JPEG", quality=92)
    base = "https://api.telegram.org/bot" + token + "/"
    try:
        with httpx.Client(timeout=30) as client:
            me = client.post(base + "getMe").json()
            if not me.get("ok"):
                raise SystemExit("Bot authentication failed. Check the token locally.")
            username = me["result"]["username"]
            if username.lower() != "protosstradingdemobot":
                raise SystemExit("Token belongs to another bot. Expected @ProtossTradingDemoBot; no changes made.")
            result = client.post(base + "setMyProfilePhoto",
                data={"photo": json.dumps({"type": "static", "photo": "attach://avatar"})},
                files={"avatar": ("probe.jpg", output.getvalue(), "image/jpeg")}).json()
            if not result.get("ok"):
                raise SystemExit("Avatar upload failed. You can also use BotFather /setuserpic with web/public/probe.png.")
            print(f"Probe avatar applied to @{username}.")
    except (httpx.HTTPError, ValueError):
        raise SystemExit("Telegram request failed. Check connectivity and retry; token was not printed.") from None


if __name__ == "__main__":
    main()
