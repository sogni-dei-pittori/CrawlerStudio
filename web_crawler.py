import re
import requests
import time
import random
from bs4 import BeautifulSoup, Comment
from urllib.parse import urlparse, urljoin, urldefrag, parse_qs, urlencode, urlunparse
from utils.site_csv import SiteCsvStore
from utils.paths import BASE_DIR
from utils.net import is_allowed, make_browser_session
from utils.logger import get_logger

logger = get_logger("web_crawler")

# 常见非 HTML 资源扩展名（可根据需要增删）
EXCLUDED_EXTENSIONS = {
    # 图片
    '.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.ico', '.bmp',
    # 样式与脚本
    '.css', '.js', '.json', '.xml', '.txt',
    # 文档
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    # 压缩包
    '.zip', '.rar', '.7z', '.tar', '.gz',
    # 音视频
    '.mp3', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.wav',
    # 字体
    '.woff', '.woff2', '.ttf', '.eot'
}

# 常见反爬虫关键字（可根据需要增删）
BLOCKED_KEYWORDS = ["反爬虫"]
# 抓的是网页：按"地址栏打开"发头；点了站内链接才有 Referer
sess = make_browser_session(dest="document", mode="navigate", site="none")


# 获取HTML页面
def get_html(base_domain, referer=None):
    headers = dict(sess.headers)  # 复制一份基础头，别改全局的
    if referer:
        headers['Referer'] = referer  # 有来源页才带 Referer
        headers['sec-fetch-site'] = 'same-origin'  # 从站内页面点过来的
    else:
        headers['sec-fetch-site'] = 'none'

    allowed, reason = is_allowed(sess, base_domain)  # 抓之前先问 robots（放在重试循环外面！）
    if not allowed:
        logger.error("robots 不允许抓取：%s（%s）", base_domain, reason)
        return None

    for attempt in range(1, 5):
        try:
            resp = sess.get(base_domain, headers=headers, timeout=10)
            if (resp.encoding or "").lower() in ("", "iso-8859-1"): resp.encoding = resp.apparent_encoding or 'utf-8'
            if resp.status_code != 429:
                time.sleep(random.uniform(1, 5))
                return resp
            wait = random.uniform(0, 1) + 2 ** attempt
            logger.warning("429限流，第 %s 次尝试，等 %.1f 秒", attempt, wait)

        except Exception as e:
            wait = random.uniform(0, 1) + attempt
            logger.warning("网络错误：%s，第 %d 次尝试，等 %.1f 秒", e, attempt, wait)

        time.sleep(wait)
    logger.error("多次尝试失败，放弃这个页面")
    return None


# 询问是否继续
def ask_yes_no(prompt):
    while True:
        choice = input(prompt).strip().lower()
        if choice in ("y", "是", "yes", "是的", "好", "ok"):
            return True
        elif choice in ("n", "否", "no", "否的", "不", "不要"):
            return False
        print("输入错误，请重新输入，可以输入 y/n 是/否 yes/no 好/不 （不限制大小写）")


# 发现子页面
def discover_subpages(resp, base_domain):
    subpages_urls = []
    soup = BeautifulSoup(resp.text, 'html.parser')
    for a in soup.find_all('a', href=True):
        href = a.get('href')
        absolute_url = urljoin(base_domain, href)
        parsed = urlparse(absolute_url)
        if parsed.netloc.lower() == urlparse(base_domain).netloc.lower():
            subpages_urls.append(absolute_url)
    return subpages_urls


# 规范化URL
def normalize_url(url):
    new_url = url.strip()
    parsed = urlparse(new_url)
    new_netloc = parsed.netloc.lower()
    new_fragment = ''
    new_path = parsed.path if parsed.path else '/'
    return urlunparse((parsed.scheme, new_netloc, new_path, parsed.params, parsed.query, new_fragment))


# 校验输入是不是一个能抓的网址（不合格就别发请求，直接结束本次爬取）
def check_url(raw):
    """先做域名校验 → (ok, 结果或原因)。

    ok=True 时第二个值是规范化后的 URL，可以直接拿去请求；
    ok=False 时第二个值是给用户看的原因，调用方直接结束本次抓取。
    """
    text = (raw or "").strip()
    if not text:
        return False, "没有输入网址"
    if any(ch.isspace() for ch in text):
        return False, f"网址里不能有空格：{text}"
    if "://" not in text:                       # 用户常忘写协议，自动补 https://
        text = "https://" + text

    try:
        parsed = urlparse(text)
    except ValueError as exc:                   # 例如 https://[abc/ 这种括号不配对
        return False, f"网址格式不对：{exc}"

    if parsed.scheme.lower() not in ("http", "https"):
        return False, f"只支持 http/https，不支持「{parsed.scheme}」"
    host = parsed.hostname or ""
    if not host:
        return False, f"看不出域名：{raw}"
    if "." not in host:
        return False, f"「{host}」不是域名（少了 .com / .cn 这类后缀）"

    labels = host.split(".")
    for label in labels:
        if not re.fullmatch(r"[A-Za-z0-9-]+", label):
            return False, f"「{host}」不是合法域名（只能用字母、数字、连字符）"
    is_ip = len(labels) == 4 and all(x.isdigit() for x in labels)
    if not is_ip and (not labels[-1].isalpha() or len(labels[-1]) < 2):
        return False, f"「{host}」的域名后缀不对（例如 .com / .cn）"

    try:
        parsed.port                             # 端口写成 :abc 这种会在这里报错
    except ValueError:
        return False, f"端口号不对：{raw}"
    return True, normalize_url(text)


# 清洗子页面的URL
def resolve_internal_url(subpages_urls, base_domain, excluded_path_patterns=None):
    new_subpages_urls = []
    parsed_base = urlparse(base_domain)
    for url in subpages_urls:
        parsed = urlparse(url)
        if parsed.scheme in ('http', 'https'):
            path = parsed.path.lower()
            if not any(path.endswith(ext) for ext in EXCLUDED_EXTENSIONS):
                if parsed_base.netloc.lower() == parsed.netloc.lower():
                    new_subpages_urls.append(url)
    return new_subpages_urls


# 提取页面信息
def extract_page_info(resp, url):
    soup = BeautifulSoup(resp.text, 'html.parser')
    title = soup.title.string if soup.title else None
    dict_html = {"url": url, "title": title, "crawled_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
                 "content": extract_text(soup)}
    return dict_html


# 提取页面文字
def extract_text(soup):
    for tag in soup(["script", "style", "noscript", "iframe", "svg", "textarea"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


# 判断页面是否被封禁
def is_blocked(resp):
    if resp.status_code in (429, 403):
        return True
    elif any(keyword in resp.text for keyword in BLOCKED_KEYWORDS):
        return True
    else:
        return False


# 主函数
# 爬取主程序入口
def main():
    try:
        while True:
            base_domain = normalize_url(input("输入URL："))
            store = SiteCsvStore(base_domain)
            seen = {base_domain}
            resp = get_html(base_domain)
            if resp:
                if is_blocked(resp):
                    logger.warning("有反爬虫机制，无法爬取：%s", base_domain)
                    continue
                store.save(extract_page_info(resp, base_domain))
                if ask_yes_no("是否继续爬取子页："):
                    for subpages in resolve_internal_url(discover_subpages(resp, base_domain), base_domain):
                        sub_url = normalize_url(subpages)
                        if sub_url in seen:
                            continue
                        else:
                            seen.add(sub_url)
                        sub_resp = get_html(sub_url, referer=base_domain)
                        if sub_resp:
                            if is_blocked(sub_resp):
                                logger.warning("有反爬虫机制，无法爬取：%s", sub_url)
                                continue
                            store.save(extract_page_info(sub_resp, sub_url))
                            logger.info("已爬取：%s", sub_url)
            if ask_yes_no("是否继续爬取其他网站："):
                continue
            else:
                break
    except KeyboardInterrupt:
        logger.info("检测到用户手动终止程序")
    except Exception as e:
        logger.error("发生错误：%s", e)
    finally:
        logger.info("程序结束")


if __name__ == "__main__":
    main()
