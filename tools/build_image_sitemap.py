#!/usr/bin/env python3
"""Build image-sitemap.xml from the live France catalogue.

Reads SCENES in index.html (the published cards) and corroborates
approval_status with manifests when a manifest exists. Only scenes whose
live status is Approved are emitted. Candidate scenes drop out on the next
run. This script does not change approval status.

    python3 tools/build_image_sitemap.py
    python3 tools/build_image_sitemap.py --check

Each Approved scene becomes one <url> at the canonical gallery address plus
the copy-link fragment (https://france.jdvision.org/#FR-01-001). Each
existing master among 16:9, 4:5, and 9:16 becomes one <image:image>.
Daylight variants are not separate master formats and are left out.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_index import INDEX, ROOT, parse_scenes  # noqa: E402

CANONICAL = "https://france.jdvision.org"
SITEMAP_PATH = ROOT / "image-sitemap.xml"
ROBOTS_PATH = ROOT / "robots.txt"
ROBOTS_LINE = f"Sitemap: {CANONICAL}/image-sitemap.xml"
PAGE_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
IMAGE_NS = "http://www.google.com/schemas/sitemap-image/1.1"
FORMATS = (
    ("16:9", "file_16x9"),
    ("4:5", "file_4x5"),
    ("9:16", "file_9x16"),
)


def xml_text(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def local_master(raw: str) -> Path | None:
    """Return the on-disk master for a scene file field, if it exists."""
    if not raw:
        return None
    path = str(raw).split("?", 1)[0]
    if path.startswith("http://") or path.startswith("https://"):
        name = path.rsplit("/", 1)[-1]
        local = ROOT / "assets" / name
    else:
        local = ROOT / path.lstrip("/")
    return local if local.is_file() else None


def manifest_status(entry_id: str) -> str | None:
    path = ROOT / "manifests" / f"{entry_id}.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    status = data.get("approval_status")
    return str(status) if status else None


def collect(scenes: list[dict]) -> tuple[list[dict], list[str]]:
    """Approved scenes with the master files that exist on disk."""
    problems: list[str] = []
    entries: list[dict] = []
    for scene in scenes:
        entry_id = scene["entry_id"]
        page_status = scene.get("approval_status") or "Candidate"
        noted = manifest_status(entry_id)
        if page_status != "Approved":
            if noted == "Approved":
                problems.append(
                    f"{entry_id} manifest is Approved but the gallery still says {page_status}; left out"
                )
            continue
        if noted is not None and noted != "Approved":
            problems.append(
                f"{entry_id} gallery says Approved but manifest says {noted}; left out"
            )
            continue
        city = str(scene.get("city") or "").strip()
        country = str(scene.get("country") or "").strip()
        title = str(scene.get("caption") or "").strip()
        description = str(scene.get("description") or "")
        if not description:
            problems.append(f"{entry_id} has no card description")
        if city and not title.endswith(", " + city):
            problems.append(f"{entry_id} caption {title!r} does not end with ', {city}'")
        images = []
        for label, key in FORMATS:
            local = local_master(str(scene.get(key) or ""))
            if local is None:
                continue
            rel = local.relative_to(ROOT).as_posix()
            images.append(
                {
                    "format": label,
                    "loc": f"{CANONICAL}/{rel}",
                    "caption": description,
                    "title": title,
                    "geo_location": f"{city}, {country}",
                }
            )
        if not images:
            problems.append(f"{entry_id} is Approved but has no existing 16:9, 4:5, or 9:16 master")
            continue
        entries.append(
            {
                "entry_id": entry_id,
                "loc": f"{CANONICAL}/#{entry_id}",
                "images": images,
            }
        )
    return entries, problems


def render_xml(entries: list[dict]) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"',
        '        xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">',
    ]
    for entry in entries:
        lines.append("  <url>")
        lines.append(f"    <loc>{xml_text(entry['loc'])}</loc>")
        for image in entry["images"]:
            lines.append("    <image:image>")
            lines.append(f"      <image:loc>{xml_text(image['loc'])}</image:loc>")
            lines.append(f"      <image:caption>{xml_text(image['caption'])}</image:caption>")
            lines.append(f"      <image:title>{xml_text(image['title'])}</image:title>")
            lines.append(
                f"      <image:geo_location>{xml_text(image['geo_location'])}</image:geo_location>"
            )
            lines.append("    </image:image>")
        lines.append("  </url>")
    lines.append("</urlset>")
    lines.append("")
    return "\n".join(lines)


def ensure_robots() -> None:
    text = ROBOTS_PATH.read_text(encoding="utf-8")
    if ROBOTS_LINE in text.splitlines():
        return
    if text and not text.endswith("\n"):
        text += "\n"
    text += ROBOTS_LINE + "\n"
    ROBOTS_PATH.write_text(text, encoding="utf-8")


def format_counts(entries: list[dict]) -> dict[str, int]:
    counts = {label: 0 for label, _key in FORMATS}
    for entry in entries:
        for image in entry["images"]:
            counts[image["format"]] += 1
    return counts


def validate_xml(path: Path, entries: list[dict]) -> list[str]:
    problems: list[str] = []
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        return [f"XML parse error: {exc}"]
    if root.tag != f"{{{PAGE_NS}}}urlset":
        problems.append(f"root tag is {root.tag}")
    urls = list(root)
    if len(urls) != len(entries):
        problems.append(f"url count {len(urls)} != approved scenes {len(entries)}")
    for node, entry in zip(urls, entries):
        loc = node.find(f"{{{PAGE_NS}}}loc")
        if loc is None or (loc.text or "") != entry["loc"]:
            problems.append(f"loc mismatch for {entry['entry_id']}")
        images = node.findall(f"{{{IMAGE_NS}}}image")
        if len(images) != len(entry["images"]):
            problems.append(f"{entry['entry_id']} image count mismatch")
            continue
        for image_node, image in zip(images, entry["images"]):
            for tag, key in (
                ("loc", "loc"),
                ("caption", "caption"),
                ("title", "title"),
                ("geo_location", "geo_location"),
            ):
                child = image_node.find(f"{{{IMAGE_NS}}}{tag}")
                if child is None or (child.text or "") != image[key]:
                    problems.append(f"{entry['entry_id']} {image['format']} {tag} mismatch")
    return problems


def check_image_urls(entries: list[dict]) -> list[str]:
    """Require HTTP 200 and a PNG body for every image:loc."""
    problems: list[str] = []
    for entry in entries:
        for image in entry["images"]:
            url = image["loc"]
            request = urllib.request.Request(url, headers={"User-Agent": "france-image-sitemap-check"})
            try:
                with urllib.request.urlopen(request, timeout=40) as response:
                    status = getattr(response, "status", None) or response.getcode()
                    content_type = response.headers.get("Content-Type", "")
                    body = response.read(8)
            except Exception as exc:  # noqa: BLE001 — report every failed loc
                problems.append(f"{url} request failed: {exc}")
                continue
            if status != 200:
                problems.append(f"{url} HTTP {status}")
            if "image/png" not in content_type.lower():
                problems.append(f"{url} content-type {content_type!r}")
            if not body.startswith(b"\x89PNG"):
                problems.append(f"{url} is not a PNG")
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the France image sitemap from live Approved scenes.")
    parser.add_argument("--check", action="store_true", help="Validate XML and require every image:loc to return a PNG.")
    args = parser.parse_args()
    scenes = parse_scenes(INDEX.read_text(encoding="utf-8"))
    entries, problems = collect(scenes)
    xml = render_xml(entries)
    SITEMAP_PATH.write_text(xml, encoding="utf-8")
    ensure_robots()
    problems.extend(validate_xml(SITEMAP_PATH, entries))
    if args.check:
        problems.extend(check_image_urls(entries))
    counts = format_counts(entries)
    image_total = sum(counts.values())
    print(f"approved scenes {len(entries)}")
    print(f"images {image_total}")
    for label, _key in FORMATS:
        print(f"{label} {counts[label]}")
    print(f"catalogue scenes {len(scenes)}")
    print(f"wrote {SITEMAP_PATH.name}")
    if problems:
        print(f"problems {len(problems)}")
        for item in problems:
            print(f"- {item}")
        raise SystemExit(1)
    print("problems 0")


if __name__ == "__main__":
    main()
