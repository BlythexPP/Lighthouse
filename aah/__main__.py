"""python3 -m aah"""

from __future__ import annotations

import sys

import uvicorn

from aah.config import ConfigError, load_settings


def main() -> None:
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"AAH configuration error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    uvicorn.run(
        "aah.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
