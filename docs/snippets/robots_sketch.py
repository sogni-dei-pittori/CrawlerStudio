from urllib.parse import urlsplit, urlunsplit

CACHE_TTL = 3600                              # 一个域名缓存 1 小时
_CACHE: dict[str, tuple] = {}                 # host -> (写入时间, robots 原文, 说明)


def robots_url(url: str) -> str:
    """由任意 URL 推出它所属站点的 robots.txt 地址。"""
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc.lower(), "/robots.txt", "", ""))
