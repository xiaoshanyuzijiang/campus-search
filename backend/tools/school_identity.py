"""Normalize the school identity and optional official website."""

import ipaddress
from urllib.parse import urlsplit

from backend.schemas import ResearchRequest, SchoolIdentity


def official_domain(website: str) -> tuple[str, str]:
    value = website.strip()
    if not value:
        return "", ""
    if "://" not in value:
        value = "https://" + value
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
        raise ValueError("学校官网地址无效，请输入 http(s) 网站地址。")
    if host == "localhost" or "." not in host:
        raise ValueError("学校官网需要使用公开域名。")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("学校官网需要使用域名，不能使用 IP 地址。")
    return parsed.geturl(), host.removeprefix("www.")


def resolve_school(request: ResearchRequest) -> SchoolIdentity:
    website, domain = official_domain(request.website)
    name = request.school_name.strip()
    if not name:
        raise ValueError("请输入学校名称。")
    return SchoolIdentity(
        name=name,
        website=website,
        domain=domain,
    )
