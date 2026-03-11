from __future__ import annotations

import argparse
from datetime import datetime, timezone

UTC = timezone.utc


def parse_utc_to_ms(value: str) -> int:
    dt = datetime.fromisoformat(str(value).strip())
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.astimezone(UTC).timestamp() * 1000)


def parse_utc_ms_to_iso(value: int | str) -> str:
    ms = int(value)
    return datetime.fromtimestamp(ms / 1000, tz=UTC).isoformat()


def _parse_cli() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="UTC time helper: ISO <-> milliseconds")
    sub = p.add_subparsers(dest="cmd", required=True)
    to_ms = sub.add_parser("to-ms", help="convert ISO datetime to UTC ms")
    to_ms.add_argument("value", type=str)
    to_iso = sub.add_parser("to-iso", help="convert UTC ms to ISO datetime")
    to_iso.add_argument("value", type=str)
    return p.parse_args()


if __name__ == "__main__":
    ns = _parse_cli()
    if ns.cmd == "to-ms":
        print(parse_utc_to_ms(ns.value))
    elif ns.cmd == "to-iso":
        print(parse_utc_ms_to_iso(ns.value))
