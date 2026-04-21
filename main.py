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


def save_images_as_pdf(images: List[Image.Image], out_pdf_path: str) -> None:
    pdf_parts: List[bytes] = [b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"]
    offsets: List[int] = [0]
    objects: List[bytes] = []
    page_ids: List[int] = []
    next_object_id = 3

    for image in images:
        rgb_image = image.convert("RGB")
        width, height = rgb_image.size
        compressed_data = zlib.compress(rgb_image.tobytes())

        content_stream = f"q\n{width} 0 0 {height} 0 0 cm\n/Im0 Do\nQ\n".encode("ascii")
        image_object_id = next_object_id
        content_object_id = next_object_id + 1
        page_object_id = next_object_id + 2
        next_object_id += 3

        image_object = (
            f"{image_object_id} 0 obj\n"
            f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} "
            f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode "
            f"/Length {len(compressed_data)} >>\nstream\n".encode("ascii")
            + compressed_data
            + b"\nendstream\nendobj\n"
        )
        content_object = (
            f"{content_object_id} 0 obj\n"
            f"<< /Length {len(content_stream)} >>\nstream\n".encode("ascii")
            + content_stream
            + b"endstream\nendobj\n"
        )
        page_object = (
            f"{page_object_id} 0 obj\n"
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] "
            f"/Resources << /XObject << /Im0 {image_object_id} 0 R >> >> "
            f"/Contents {content_object_id} 0 R >>\nendobj\n".encode("ascii")
        )

        objects.extend([image_object, content_object, page_object])
        page_ids.append(page_object_id)

    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    catalog_object = b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    pages_object = (
        f"2 0 obj\n<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>\nendobj\n".encode(
            "ascii"
        )
    )
    objects = [catalog_object, pages_object] + objects

    for obj in objects:
        offsets.append(sum(len(part) for part in pdf_parts))
        pdf_parts.append(obj)

    xref_offset = sum(len(part) for part in pdf_parts)
    xref_lines = [f"xref\n0 {len(offsets)}\n", "0000000000 65535 f \n"]
    xref_lines.extend(f"{offset:010d} 00000 n \n" for offset in offsets[1:])
    trailer = (
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    )
    pdf_parts.append("".join(xref_lines).encode("ascii"))
    pdf_parts.append(trailer.encode("ascii"))

    with open(out_pdf_path, "wb") as f:
        f.write(b"".join(pdf_parts))


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
    images: List[ImageFile.ImageFile] = []
    for img_path in file_list:
        print(img_path)
        images.append(Image.open(img_path).convert("RGB"))
    out_pdf_path: str = os.path.join(OUTPUT_DIR, f"{ph_name}.pdf")
    save_images_as_pdf(images, out_pdf_path)
    if CLEAR_CACHE:
        for img_path in file_list:
            os.remove(img_path)


def process_ph(ph_name: str) -> None:
    parsed_result: Dict[str, str | Any] = {}
    safe_name = os.path.splitext(os.path.basename(ph_name))[0]
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
