from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    gs_webapp_url: str
    tz: str
    data_dir: str


def load_config() -> Config:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    gs_webapp_url = os.getenv("GS_WEBAPP_URL", "").strip()
    tz = os.getenv("TZ", "Asia/Jakarta").strip()
    data_dir = os.getenv("DATA_DIR", "data").strip()

    missing = [
        name
        for name, value in [
            ("BOT_TOKEN", bot_token),
            ("GS_WEBAPP_URL", gs_webapp_url),
        ]
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing env vars: {', '.join(missing)}")

    return Config(
        bot_token=bot_token,
        gs_webapp_url=gs_webapp_url,
        tz=tz,
        data_dir=data_dir,
    )
