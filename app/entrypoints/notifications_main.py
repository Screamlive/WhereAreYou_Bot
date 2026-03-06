import asyncio

from notifications import send_daily_notifications


def main() -> None:
    asyncio.run(send_daily_notifications())

