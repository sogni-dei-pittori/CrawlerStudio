import re
from bs4 import BeautifulSoup


def _digits_to_int(text: str) -> int:
    m = re.search(r"\d+", text)
    return int(m.group()) if m else 0


def parse_top250_movie(html):
    soup = BeautifulSoup(html, "html.parser")
    rows = []

    for item in soup.select("div.item"):
        rank = int(item.select_one("em").get_text(strip=True))
        title = item.select_one("span.title").get_text(strip=True)
        info = item.select_one(".bd p").get_text(separator=" ", strip=True).replace("\xa0", " ")
        rating = item.select_one(".rating_num").get_text(strip=True)
        spans = item.select(".bd div span")  # 取列表
        votes_text = "".join(spans[-1].get_text().split()) if spans else ""
        votes = _digits_to_int(votes_text)
        quote = (n.get_text(strip=True) if (n := item.select_one("p.quote span")) else "")
        url = item.select_one(".hd a")["href"]
        rows.append({
            "rank": rank, "title": title, "info": info, "rating": rating, "votes": votes, "quote": quote,
            "url": url,
        })

    return rows


def parse_top250_book(html, rank_offset=0):
    soup = BeautifulSoup(html, "html.parser")
    rows = []

    for i, item in enumerate(soup.select("tr.item")):
        rank = rank_offset + i + 1
        a = item.select_one(".pl2 a")
        n = item.select_one(".inq")
        title = a["title"]
        url = a["href"]
        info = item.select_one("p.pl").get_text(strip=True).replace("\xa0", " ")
        rating = item.select_one(".rating_nums").get_text(strip=True)
        votes_text = "".join(item.select_one(".star .pl").get_text().split())
        votes = _digits_to_int(votes_text)
        quote = n.get_text(strip=True) if n else ""
        rows.append({
            "rank": rank, "title": title, "info": info, "rating": rating, "votes": votes, "quote": quote,
            "url": url,
        })
    return rows


def parse_doulist(html):
    soup = BeautifulSoup(html, "html.parser")
    rows = []

    for item in soup.select("div.doulist-item"):
        a = item.select_one(".title a")
        if a is None:  # 结构不完整（失效条目）→ 跳过
            continue

        rank = int(item.select_one(".pos").get_text(strip=True))
        title = a.get_text(strip=True)
        url = a["href"]

        rnode = item.select_one(".rating .rating_nums")
        rating = rnode.get_text(strip=True) if rnode else ""  # 非关键 → 空值

        spans = item.select(".rating span")
        votes_text = "".join(spans[-1].get_text().split()) if spans else ""
        votes = _digits_to_int(votes_text)

        anode = item.select_one(".abstract")
        info = anode.get_text(separator=" ", strip=True) if anode else ""

        rows.append({
            "rank": rank, "title": title, "info": info, "rating": rating, "votes": votes, "url": url, "quote": "",
        })
    return rows


