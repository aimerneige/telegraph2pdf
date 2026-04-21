import os
import json
import zlib
import requests
from PIL import Image, ImageFile
from requests import Response
from bs4 import BeautifulSoup
from typing import List, Dict, Any
from bs4.element import ResultSet, Tag
from urllib.parse import urljoin

ImageFile.LOAD_TRUNCATED_IMAGES = True

BASE_URL = "https://telegra.ph"
CACHE_DIR = "./cache"
OUTPUT_DIR = "./output"
PH_NAME_LIST = [
    "Barbara-08-23-4",
    "Nukunuku-Mini-Holes-08-18-2",
    "僕らのラブライブ-15-SHAMROCK-おぎ-昨日の僕と明日の君-ラブライブ-中国翻訳-Preview-07-12",
    "ぼっちざろっくぼ喜多虹マンガ-Preview-04-19-3",
    "僕らのラブライブ-6-蒼井ホログラム-めの-クリスマスマジック-ラブライブ-中国翻訳-Preview-03-18",
    "C92-Do-well--ながれぼし-夏風ベクレムト-ラブライブラブライブ-サンシャイン-中国翻訳-Preview-04-08",
    "C102-悠遠monochrome-ゆうえむ-絡まるリボンを抱きしめて-ラブライブ-中国翻訳-Preview-03-22",
    "さんしきすみれ-モルゲン-きょうはわたしがするんです-ラブライブ-中国翻訳-DL版-Preview-03-22",
    "僕らのラブライブ-13-towai-Hzk-Yr-ラブライブ-サンシャイン-中国翻訳-Preview-03-19",
    "アクアマリンドリーム5th-帰宅時間-きたく-サクラホリック-ラブライブ-サンシャイン-中国翻訳-Preview-03-08-2"
]
CLEAR_CACHE = True
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/135.0.0.0 Safari/537.36"
    ),
    "Referer": f"{BASE_URL}/",
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def write_to_file(file_path: str, data: str) -> None:
    with open(file_path, "w") as f:
        f.write(data)


def read_from_file(file_path: str) -> str:
    with open(file_path, "r") as f:
        return f.read()


def curl_url_text(url: str) -> str:
    response: Response = requests.get(url, headers=DEFAULT_HEADERS, timeout=30)
    if response.status_code != 200:
        print("HTTP NOT OK")
        print(response)
        exit()
    return response.text


def get_html_source(source: str) -> tuple[str, str]:
    if os.path.isfile(source):
        return read_from_file(source), f"file://{os.path.abspath(source)}"
    url = source if source.startswith(("http://", "https://")) else f"{BASE_URL}/{source}"
    return curl_url_text(url), url


def parse_ph(source: str) -> Dict[str, str | Any]:
    html_str, page_url = get_html_source(source)
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
    img_url_list: List[str] = [urljoin(page_url, img.attrs["src"].strip()) for img in imgs]
    p_tags: ResultSet[Tag] = article.select("p")
    origin_link = ""
    for p in p_tags:
        if p.text.strip().startswith("Original link:"):
            link_tag = p.find("a")
            if link_tag and link_tag.has_attr("href"):
                origin_link = link_tag.attrs["href"]
                break
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
    file_name = img_url.split("/")[-1]
    file_path = os.path.join(CACHE_DIR, file_name)
    if os.path.isfile(file_path):
        print(f"File {file_path} exists! skipped")
        return

    with requests.get(img_url, headers=DEFAULT_HEADERS, stream=True, timeout=60) as response:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"Failed to download image: {img_url} ({response.status_code})") from exc

        total_size = int(response.headers.get("content-length", 0))
        downloaded = 0
        with open(file_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 64):
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)
                if total_size > 0:
                    progress = downloaded * 100.0 / total_size
                    print(f"\rdownloading: {progress:5.1f}%", end="")
    print()


def save_images_as_pdf(image_paths: List[str], out_pdf_path: str) -> None:
    object_offsets: Dict[int, int] = {}
    page_ids: List[int] = []
    next_object_id = 3

    def write_object(f, object_id: int, payload: bytes) -> None:
        object_offsets[object_id] = f.tell()
        f.write(f"{object_id} 0 obj\n".encode("ascii"))
        f.write(payload)
        f.write(b"\nendobj\n")

    with open(out_pdf_path, "wb") as f:
        f.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

        for index, img_path in enumerate(image_paths, start=1):
            print(f"merging {index}/{len(image_paths)} {img_path}")
            with Image.open(img_path) as image:
                rgb_image = image.convert("RGB")
                width, height = rgb_image.size
                compressed_data = zlib.compress(rgb_image.tobytes())

            image_object_id = next_object_id
            content_object_id = next_object_id + 1
            page_object_id = next_object_id + 2
            next_object_id += 3

            image_payload = (
                f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} "
                f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode "
                f"/Length {len(compressed_data)} >>\nstream\n".encode("ascii")
            )
            write_object(
                f,
                image_object_id,
                image_payload + compressed_data + b"\nendstream",
            )

            content_stream = (
                f"q\n{width} 0 0 {height} 0 0 cm\n/Im0 Do\nQ\n".encode("ascii")
            )
            content_payload = (
                f"<< /Length {len(content_stream)} >>\nstream\n".encode("ascii")
                + content_stream
                + b"endstream"
            )
            write_object(f, content_object_id, content_payload)

            page_payload = (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] "
                f"/Resources << /XObject << /Im0 {image_object_id} 0 R >> >> "
                f"/Contents {content_object_id} 0 R >>".encode("ascii")
            )
            write_object(f, page_object_id, page_payload)
            page_ids.append(page_object_id)

        pages_payload = (
            f"<< /Type /Pages /Kids [{' '.join(f'{page_id} 0 R' for page_id in page_ids)}] "
            f"/Count {len(page_ids)} >>".encode("ascii")
        )
        write_object(f, 2, pages_payload)
        write_object(f, 1, b"<< /Type /Catalog /Pages 2 0 R >>")

        max_object_id = next_object_id - 1
        xref_offset = f.tell()
        f.write(f"xref\n0 {max_object_id + 1}\n".encode("ascii"))
        f.write(b"0000000000 65535 f \n")
        for object_id in range(1, max_object_id + 1):
            f.write(f"{object_offsets[object_id]:010d} 00000 n \n".encode("ascii"))

        trailer = (
            f"trailer\n<< /Size {max_object_id + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        )
        f.write(trailer.encode("ascii"))


def generate_pdf(img_urls: List[str], ph_name: str) -> None:
    total = len(img_urls)
    print("start download all images")
    for i, img_url in enumerate(img_urls):
        print(f"{i}/{total} {img_url}")
        download_img(img_url)
    print("image download complete")
    print("start merging pdf file")
    file_list = [
        os.path.join(CACHE_DIR, img_url.split("/")[-1]) for img_url in img_urls
    ]
    out_pdf_path: str = os.path.join(OUTPUT_DIR, f"{ph_name}.pdf")
    save_images_as_pdf(file_list, out_pdf_path)
    if CLEAR_CACHE:
        for img_path in file_list:
            os.remove(img_path)


def process_ph(ph_name: str) -> None:
    parsed_result: Dict[str, str | Any] = {}
    safe_name = os.path.splitext(os.path.basename(ph_name))[0]
    out_pdf_path = os.path.join(OUTPUT_DIR, f"{safe_name}.pdf")
    if os.path.exists(out_pdf_path):
        print(f"Skip {safe_name}: {out_pdf_path} already exists")
        return
    result_json_path = os.path.join(OUTPUT_DIR, f"{safe_name}.json")
    if not os.path.exists(result_json_path):
        parsed_result = parse_ph(ph_name)
        write_to_file(
            result_json_path, json.dumps(parsed_result, ensure_ascii=False, indent=4)
        )
    else:
        with open(result_json_path, "r") as f:
            parsed_result = json.load(f)
    generate_pdf(parsed_result["img_url_list"], safe_name)


def main() -> None:
    if not os.path.exists(CACHE_DIR):
        os.mkdir(CACHE_DIR)
    if not os.path.exists(OUTPUT_DIR):
        os.mkdir(OUTPUT_DIR)
    for ph_name in PH_NAME_LIST:
        print(f"Processing {ph_name}")
        process_ph(ph_name)


if __name__ == "__main__":
    main()
