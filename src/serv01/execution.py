import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx
from playwright.sync_api import Route, sync_playwright

from serv01.config import Settings


@dataclass(frozen=True)
class CrawledPage:
    title: str
    url: str
    status_code: int | None
    forms: list[dict[str, str | None]]


class ExecutionBlocked(RuntimeError):
    """Raised when a safety policy prevents a navigation."""


def is_host_allowed(url: str, allowed_hosts: set[str]) -> bool:
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return False
    return bool(
        parsed.scheme.lower() in {"http", "https"}
        and hostname
        and hostname.lower().rstrip(".") in allowed_hosts
        and parsed.username is None
        and parsed.password is None
        and (port is None or 1 <= port <= 65535)
    )


def robots_url_for(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, "/robots.txt", "", ""))


def robots_permits(url: str, robots_text: str, user_agent: str) -> bool:
    groups: list[tuple[list[str], list[tuple[bool, str]]]] = []
    agents: list[str] = []
    rules: list[tuple[bool, str]] = []
    for raw_line in robots_text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, value = (part.strip() for part in line.split(":", 1))
        field = field.lower()
        if field == "user-agent":
            if rules:
                groups.append((agents, rules))
                agents, rules = [], []
            agents.append(value.lower())
        elif field in {"allow", "disallow"} and agents:
            if value or field == "allow":
                rules.append((field == "allow", value))
    if agents:
        groups.append((agents, rules))

    product = user_agent.split("/", 1)[0].split(maxsplit=1)[0].lower()
    specific_groups = [
        group for group in groups if any(agent != "*" and agent == product for agent in group[0])
    ]
    selected = specific_groups or [group for group in groups if "*" in group[0]]
    path = urlsplit(url).path or "/"
    query = urlsplit(url).query
    if query:
        path = f"{path}?{query}"
    matches: list[tuple[int, bool]] = []
    for _, group_rules in selected:
        for allow, pattern in group_rules:
            if not pattern:
                continue
            end_anchored = pattern.endswith("$")
            raw_pattern = pattern[:-1] if end_anchored else pattern
            expression = re.escape(raw_pattern).replace(r"\*", ".*")
            if re.match(f"^{expression}{'$' if end_anchored else ''}", path):
                specificity = len(raw_pattern.replace("*", ""))
                matches.append((specificity, allow))
    if not matches:
        return True
    longest = max(match[0] for match in matches)
    return any(allow for specificity, allow in matches if specificity == longest)


def fetch_robots_text(url: str, settings: Settings) -> str:
    try:
        with httpx.Client(
            timeout=settings.page_timeout_seconds,
            follow_redirects=False,
            headers={"User-Agent": settings.bot_user_agent},
        ) as client:
            response = client.get(url)
        if response.status_code == 404:
            return ""
        if response.is_redirect:
            raise ExecutionBlocked(f"robots_txt_redirect_not_followed: {url}")
        response.raise_for_status()
        return response.text
    except httpx.HTTPError as exc:
        raise ExecutionBlocked(f"robots_txt_unavailable: {url}") from exc


def crawl_page(url: str, screenshot_path: Path, settings: Settings) -> CrawledPage:
    allowed_hosts = settings.parsed_allowed_hosts

    def enforce_allowlist(route: Route) -> None:
        if is_host_allowed(route.request.url, allowed_hosts):
            route.continue_()
        else:
            route.abort("blockedbyclient")

    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-background-networking",
                "--disable-component-update",
                "--disable-default-apps",
                "--no-first-run",
            ],
        )
        try:
            context = browser.new_context(user_agent=settings.bot_user_agent)
            context.route("**/*", enforce_allowlist)
            page = context.new_page()
            response = page.goto(
                url,
                wait_until="load",
                timeout=settings.page_timeout_seconds * 1000,
            )
            final_url = page.url
            if not is_host_allowed(final_url, allowed_hosts):
                host = urlsplit(final_url).hostname or "invalid"
                raise ExecutionBlocked(f"blocked_by_allowlist: {host}")
            forms: list[dict[str, str | None]] = page.locator("form").evaluate_all(
                """forms => forms.map(form => ({
                    method: (form.getAttribute('method') || 'get').toLowerCase(),
                    action: form.getAttribute('action'),
                    name: form.getAttribute('name'),
                    id: form.getAttribute('id')
                }))"""
            )
            page.screenshot(path=str(screenshot_path), full_page=True)
            return CrawledPage(
                title=page.title(),
                url=final_url,
                status_code=response.status if response is not None else None,
                forms=forms,
            )
        finally:
            browser.close()


Crawler = Callable[[str, Path], CrawledPage]
RobotsFetcher = Callable[[str], str]
