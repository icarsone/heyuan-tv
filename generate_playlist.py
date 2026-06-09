#!/usr/bin/env python3
"""Build a compact Guangdong-friendly playlist from fanmingming/live."""

from __future__ import annotations

import re
import urllib.request
from pathlib import Path


UPSTREAM = "https://raw.githubusercontent.com/fanmingming/live/main/tv/m3u"
OUTPUT = Path(__file__).with_name("heyuan.m3u")

SOURCES = (
    ("index.m3u", "广东联通优先", ""),
    ("ipv6.m3u", "IPv6备用", " [IPv6备用]"),
    ("itv.m3u", "通用备用", " [通用备用]"),
)

WANTED = (
    "CCTV1",
    "CCTV2",
    "CCTV3",
    "CCTV4",
    "CCTV5",
    "CCTV5+",
    "CCTV6",
    "CCTV7",
    "CCTV8",
    "CCTV9",
    "CCTV10",
    "CCTV11",
    "CCTV12",
    "CCTV13",
    "CCTV14",
    "CCTV15",
    "CCTV16",
    "CCTV17",
    "广东卫视",
    "深圳卫视",
    "湖南卫视",
    "浙江卫视",
    "江苏卫视",
    "东方卫视",
    "北京卫视",
    "重庆卫视",
    "四川卫视",
    "广西卫视",
    "海南卫视",
    "湖北卫视",
    "江西卫视",
    "安徽卫视",
    "河南卫视",
    "山东卫视",
    "东南卫视",
    "天津卫视",
    "辽宁卫视",
    "黑龙江卫视",
    "吉林卫视",
    "贵州卫视",
    "云南卫视",
    "陕西卫视",
    "甘肃卫视",
)

NAME_RE = re.compile(r'tvg-name="([^"]+)"')
GROUP_RE = re.compile(r'group-title="[^"]*"')


def download(name: str) -> list[str]:
    request = urllib.request.Request(
        f"{UPSTREAM}/{name}",
        headers={"User-Agent": "heyuan-tv-playlist"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8-sig").splitlines()


def normalize(name: str) -> str:
    return re.sub(r"[\s_-]", "", name).upper()


def wanted_key(name: str) -> str | None:
    normalized = normalize(name)
    for item in WANTED:
        if normalized == normalize(item):
            return item
    return None


def entries(lines: list[str]):
    for index, line in enumerate(lines[:-1]):
        if line.startswith("#EXTINF") and lines[index + 1].startswith(("http://", "https://")):
            yield line, lines[index + 1]


def build() -> str:
    output = ['#EXTM3U x-tvg-url="https://live.fanmingming.cn/e.xml"']

    for filename, group, suffix in SOURCES:
        found: set[str] = set()
        for info, url in entries(download(filename)):
            match = NAME_RE.search(info)
            if not match:
                continue

            key = wanted_key(match.group(1))
            if not key or key in found:
                continue

            # The primary Guangdong list contains expired "备用" entries after
            # its main lineup. Keep only its first, area-specific occurrence.
            if filename == "index.m3u" and "备用" in info:
                continue

            info = GROUP_RE.sub(f'group-title="{group}"', info)
            display_name = info.rsplit(",", 1)[-1].strip() + suffix
            info = info.rsplit(",", 1)[0] + "," + display_name
            output.extend((info, url))
            found.add(key)

    return "\n".join(output) + "\n"


if __name__ == "__main__":
    OUTPUT.write_text(build(), encoding="utf-8", newline="\n")
    print(f"Wrote {OUTPUT}")
