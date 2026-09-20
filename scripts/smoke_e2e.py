"""Run one real, allowlisted Playwright capture without Redis."""

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from serv01.config import Settings
from serv01.execution import (
    crawl_page,
    fetch_robots_text,
    is_host_allowed,
    robots_permits,
    robots_url_for,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url", nargs="?", default="https://example.com")
    arguments = parser.parse_args()
    settings = Settings()
    if not is_host_allowed(arguments.url, settings.parsed_allowed_hosts):
        host = urlsplit(arguments.url).hostname or "invalid"
        raise SystemExit(f"blocked_by_allowlist: {host}")
    if not robots_permits(
        arguments.url,
        fetch_robots_text(robots_url_for(arguments.url), settings),
        settings.bot_user_agent,
    ):
        raise SystemExit(f"blocked_by_robots_txt: {arguments.url}")
    output = Path(settings.screenshot_dir) / "smoke.png"
    page = crawl_page(arguments.url, output, settings)
    print(
        json.dumps(
            {
                "title": page.title,
                "url": page.url,
                "status_code": page.status_code,
                "forms": page.forms,
                "screenshot": str(output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
