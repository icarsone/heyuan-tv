#!/usr/bin/env python3
"""Build a playlist containing streams that work on the current network."""

from __future__ import annotations

import concurrent.futures
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path


OUTPUT = Path(__file__).with_name("heyuan.m3u")
TIMEOUT = 7
MAX_CANDIDATES_PER_CHANNEL = 14

SOURCE_LISTS = (
    "https://raw.githubusercontent.com/zilong7728/Collect-IPTV/refs/heads/main/best_sorted.m3u",
    "https://live.zbds.top/tv/iptv4.m3u",
    "https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/ipv4/result.m3u",
    "https://peterhchina.github.io/iptv/CNTV-V4.m3u",
    "https://raw.githubusercontent.com/122566/cn-iptv/main/cn_live.m3u",
    "https://raw.githubusercontent.com/hujingguang/ChinaIPTV/main/cnTV_AutoUpdate.m3u8",
    "https://iptv-org.github.io/iptv/categories/kids.m3u",
    "https://iptv-org.github.io/iptv/categories/animation.m3u",
)

CHANNELS = (
    ("河源综合", "河源本地", ("河源综合",)),
    ("河源公共", "河源本地", ("河源公共",)),
    ("广东卫视", "广东频道", ("广东卫视",)),
    ("广东珠江", "广东频道", ("广东珠江", "珠江频道")),
    ("广东体育", "广东频道", ("广东体育",)),
    ("广东新闻", "广东频道", ("广东新闻",)),
    ("大湾区卫视", "广东频道", ("大湾区卫视",)),
    ("南方卫视", "广东频道", ("南方卫视",)),
    ("金鹰卡通", "动画备用", ("金鹰卡通",)),
    ("韩国EBS少儿", "动画少儿", ("韩国EBS少儿",)),
    ("EBS Kids", "动画少儿", ("EBS Kids",)),
    ("猫和老鼠", "动画少儿", ("Tom And Jerry", "猫和老鼠")),
    ("火影忍者", "动画少儿", ("Naruto", "火影忍者")),
    ("Moonbug Kids", "动画少儿", ("Moonbug Kids",)),
    ("Toon Goggles Junior", "动画少儿", ("Toon Goggles Junior",)),
    ("Kartoon Channel", "动画少儿", ("Kartoon Channel",)),
    *tuple((f"CCTV{i}", "央视频道", (f"CCTV{i}",)) for i in range(1, 18)),
    ("CCTV5+", "央视频道", ("CCTV5+",)),
    ("北京卫视", "卫视频道", ("北京卫视",)),
    ("东方卫视", "卫视频道", ("东方卫视",)),
    ("湖南卫视", "卫视频道", ("湖南卫视",)),
    ("江苏卫视", "卫视频道", ("江苏卫视",)),
    ("浙江卫视", "卫视频道", ("浙江卫视",)),
    ("深圳卫视", "卫视频道", ("深圳卫视",)),
    ("广西卫视", "卫视频道", ("广西卫视",)),
    ("海南卫视", "卫视频道", ("海南卫视",)),
    ("湖北卫视", "卫视频道", ("湖北卫视",)),
    ("江西卫视", "卫视频道", ("江西卫视",)),
    ("安徽卫视", "卫视频道", ("安徽卫视",)),
    ("河南卫视", "卫视频道", ("河南卫视",)),
    ("山东卫视", "卫视频道", ("山东卫视",)),
    ("东南卫视", "卫视频道", ("东南卫视",)),
    ("天津卫视", "卫视频道", ("天津卫视",)),
    ("辽宁卫视", "卫视频道", ("辽宁卫视",)),
    ("黑龙江卫视", "卫视频道", ("黑龙江卫视",)),
    ("吉林卫视", "卫视频道", ("吉林卫视",)),
    ("四川卫视", "卫视频道", ("四川卫视",)),
    ("重庆卫视", "卫视频道", ("重庆卫视",)),
    ("贵州卫视", "卫视频道", ("贵州卫视",)),
    ("云南卫视", "卫视频道", ("云南卫视",)),
    ("陕西卫视", "卫视频道", ("陕西卫视",)),
    ("甘肃卫视", "卫视频道", ("甘肃卫视",)),
)

CHANNEL_BY_NAME = {name: (group, aliases) for name, group, aliases in CHANNELS}
REQUEST_HEADERS = {"User-Agent": "PotPlayer/240618", "Accept": "*/*"}
NAME_RE = re.compile(r'tvg-name="([^"]+)"', re.IGNORECASE)
CCTV_RE = re.compile(r"CCTV\D*?(\d{1,2})(\+)?", re.IGNORECASE)


@dataclass(frozen=True)
class Candidate:
    channel: str
    url: str


def request(url: str, limit: int = 512_000) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers=REQUEST_HEADERS)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
        return response.read(limit), response.geturl()


def fetch_text(url: str) -> str:
    last_error: OSError | None = None
    for _ in range(3):
        try:
            data, _ = request(url, 2_000_000)
            return data.decode("utf-8-sig", errors="replace")
        except OSError as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


def normalize(value: str) -> str:
    value = value.upper().replace("＋", "+")
    return re.sub(r"[\s\-_·•（）()\[\]]", "", value)


def identify_channel(value: str) -> str | None:
    normalized = normalize(value)

    cctv = CCTV_RE.search(normalized)
    if cctv:
        number = int(cctv.group(1))
        if 1 <= number <= 17:
            return f"CCTV{number}{'+' if cctv.group(2) else ''}"

    for channel, (_, aliases) in CHANNEL_BY_NAME.items():
        if channel.startswith("CCTV"):
            continue
        if any(normalize(alias) in normalized for alias in aliases):
            return channel
    return None


def parse_playlist(text: str) -> list[Candidate]:
    found: list[Candidate] = []
    current_channel: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("#EXTINF"):
            name_match = NAME_RE.search(line)
            display_name = line.rsplit(",", 1)[-1]
            current_channel = identify_channel(name_match.group(1) if name_match else display_name)
        elif current_channel and line.startswith(("http://", "https://")):
            # Options appended with "|" or "$" need player-specific headers.
            url = line.split("|", 1)[0].split("$", 1)[0].strip()
            if "live.php" not in url and url not in {item.url for item in found}:
                found.append(Candidate(current_channel, url))
    return found


def media_uri(text: str) -> str | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    uris = [line for line in lines if not line.startswith("#")]
    if len(uris) >= 2:
        # The newest HLS segment is occasionally advertised a fraction of a
        # second before it is available. Test the preceding completed segment.
        return uris[-2]
    return uris[-1] if uris else None


def probe_stream(url: str, depth: int = 0) -> bool:
    if depth > 2:
        return False

    data, final_url = request(url)
    if not data.lstrip().startswith(b"#EXTM3U"):
        return False

    text = data.decode("utf-8", errors="replace")
    if "backup_" in text or "#EXT-X-ENDLIST" in text:
        return False

    next_uri = media_uri(text)
    if not next_uri:
        return False

    next_url = urllib.parse.urljoin(final_url, next_uri)
    if "#EXT-X-STREAM-INF" in text:
        return probe_stream(next_url, depth + 1)

    if "#EXT-X-MEDIA-SEQUENCE" not in text:
        return False

    segment, _ = request(next_url, 96_000)
    return len(segment) >= 32_768


def choose_working(channel: str, candidates: list[Candidate]) -> tuple[str, str | None]:
    for candidate in candidates[:MAX_CANDIDATES_PER_CHANNEL]:
        lowered = candidate.url.lower()
        if any(
            marker in lowered
            for marker in (".mp4", "wssecret=", "auth_token=", "user_session_id=")
        ):
            continue
        if channel == "CCTV4" and "cgtn" in lowered:
            continue
        try:
            if probe_stream(candidate.url):
                return channel, candidate.url
        except (OSError, socket.timeout, urllib.error.URLError, ValueError):
            continue
    return channel, None


def build() -> tuple[str, list[str]]:
    candidates: dict[str, list[Candidate]] = {name: [] for name in CHANNEL_BY_NAME}

    for source in SOURCE_LISTS:
        try:
            for candidate in parse_playlist(fetch_text(source)):
                known_urls = {item.url for item in candidates[candidate.channel]}
                if candidate.url not in known_urls:
                    candidates[candidate.channel].append(candidate)
        except (OSError, socket.timeout, urllib.error.URLError) as exc:
            print(f"Could not read {source}: {exc}")

    selected: dict[str, str] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=18) as executor:
        futures = {
            executor.submit(choose_working, channel, items): channel
            for channel, items in candidates.items()
            if items
        }
        for future in concurrent.futures.as_completed(futures):
            channel, url = future.result()
            print(f"{'OK  ' if url else 'MISS'} {channel}")
            if url:
                selected[channel] = url

    lines = ['#EXTM3U x-tvg-url="https://live.fanmingming.cn/e.xml"']
    missing: list[str] = []
    for channel, group, _ in CHANNELS:
        url = selected.get(channel)
        if not url:
            missing.append(channel)
            continue
        logo_name = channel.replace("CCTV", "CCTV")
        lines.append(
            f'#EXTINF:-1 tvg-name="{channel}" '
            f'tvg-logo="https://live.fanmingming.cn/tv/{logo_name}.png" '
            f'group-title="{group}",{channel}'
        )
        lines.append(url)
    return "\n".join(lines) + "\n", missing


if __name__ == "__main__":
    playlist, missing_channels = build()
    OUTPUT.write_text(playlist, encoding="utf-8", newline="\n")
    channel_count = playlist.count("#EXTINF")
    print(f"Wrote {OUTPUT} with {channel_count} verified channels")
    if missing_channels:
        print("Missing: " + ", ".join(missing_channels))
