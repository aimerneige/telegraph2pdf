import os
import json
import requests
from PIL import Image, ImageFile
from requests import Response
from bs4 import BeautifulSoup
from typing import List, Dict, Any
from bs4.element import ResultSet, Tag
from urllib.request import urlretrieve

ImageFile.LOAD_TRUNCATED_IMAGES = True

BASE_URL = "https://telegra.ph"
CACHE_DIR = "./cache"
PH_NAME = "ZZZero-1-08-19"
RESULT_JSON_PATH = f"./{PH_NAME}.json"
OUT_PDF_PATH = f"./{PH_NAME}.pdf"


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
    img_url_list: List[str] = [f'{BASE_URL}{img.attrs["src"].strip()}' for img in imgs]
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
        "img_url_list": img_url_list,
        "origin_link": origin_link,
    }
    return parsed_result


def download_img(img_url: str) -> None:

    def reporthook(a, b, c):
        print("\rdownloading: %5.1f%%" % (a * b * 100.0 / c), end="")

    file_name = img_url.split("/")[-1]
    file_path = os.path.join(CACHE_DIR, file_name)
    if os.path.isfile(file_path):
        print(f"File {file_path} exists! skipped")
        return
    urlretrieve(img_url, file_path, reporthook=reporthook)
    print()


def generate_pdf(img_urls: List[str]) -> None:
    total = len(img_urls)
    print("start download all images")
    for i, img_url in enumerate(img_urls):
        print(f'{i}/{total} {img_url}')
        download_img(img_url)
    print("image download complete")
    print("start merging pdf file")
    file_list = [
        os.path.join(CACHE_DIR, img_url.split("/")[-1]) for img_url in img_urls
    ]
    images: List[ImageFile.ImageFile] = []
    for img_path in file_list:
        print(img_path)
        images.append(Image.open(img_path).convert('RGB'))
    images[0].save(
        OUT_PDF_PATH, resolution=100.0, save_all=True, append_images=images[1:]
    )


def main() -> None:
    parsed_result = parse_ph(PH_NAME)
    write_to_file(
        RESULT_JSON_PATH, json.dumps(parsed_result, ensure_ascii=False, indent=4)
    )
    generate_pdf(parsed_result["img_url_list"])


if __name__ == "__main__":
    main()
