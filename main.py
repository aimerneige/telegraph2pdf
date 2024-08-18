import json
import requests
from requests import Response
from bs4 import BeautifulSoup
from bs4.element import ResultSet, Tag
from typing import List, Dict, Any

BASE_URL = "https://telegra.ph"
RESULT_JSON_PATH = "./result.json"


def write_to_file(file_path: str, data: str) -> None:
    with open(file_path, "w") as f:
        f.write(data)


def read_from_file(file_path: str) -> str:
    with open(file_path, "r") as f:
        return f.read()


def curl_url_text(url: str) -> str:
    response: Response = requests.get(url)
    if response.status_code != 200:
        print("HTTP NOT OK")
        print(response)
        exit()
    return response.text


def parse_ph(ph: str) -> Dict[str, str | Any]:
    url: str = f"{BASE_URL}/{ph}"
    html_str: str = curl_url_text(url)
    soup: BeautifulSoup = BeautifulSoup(html_str, "lxml")
    article_header: Tag = soup.find("header", {"class": "tl_article_header"})
    title: str = article_header.find("h1").text.strip()
    author_tag: Tag = article_header.find("a")
    author: str = author_tag.text.strip()
    author_href: str = author_tag.attrs["href"]
    publish_time: Tag = article_header.find("time")
    datetime_str: str = publish_time.attrs["datetime"]
    date_str: str = publish_time.text.strip()
    article: Tag = soup.find(
        "article", {"class": "tl_article_content", "id": "_tl_editor"}
    )
    imgs: ResultSet[Tag] = article.find_all("img")
    url_list: List[str] = [f'{BASE_URL}{img.attrs["src"].strip()}' for img in imgs]
    p_tags: ResultSet[Tag] = article.select("p")
    origin_link: str
    for p in p_tags:
        if p.text.strip().startswith("Original link:"):
            origin_link = p.find("a").attrs["href"]
    parsed_result: Dict[str, str | Any] = {
        "title": title,
        "author": author,
        "author_href": author_href,
        "datetime_str": datetime_str,
        "date_str": date_str,
        "url_list": url_list,
        "origin_link": origin_link,
    }
    return parsed_result


def main() -> None:
    parsed_result = parse_ph("Nukunuku-Mini-Holes-08-18")
    write_to_file(
        RESULT_JSON_PATH, json.dumps(parsed_result, ensure_ascii=False, indent=4)
    )


if __name__ == "__main__":
    main()
