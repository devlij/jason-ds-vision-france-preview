#!/usr/bin/env python3
"""France 360 cumulative gap-fill — static-ambient Ken Burns clips.

Same delivery path as gap-fill packs 1 and 2: a genuine daylight 4:5 master,
label bar cropped off, 10.0s 864x1080 H.264. Real image-to-video is not used.
The motion is a smooth slow Ken Burns pan-zoom on that still.

Night-only scenes are not read. Clips already on main are not remade.
A scene that fails once is HOLD and is not retried. Three HOLDs in a row
stop the run.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FPS = 24
FRAMES = 240  # exactly 10.0s
PHOTO_H = 1080
PHOTO_W = 864
MIN_ZOOM = 1.018
MIN_TRAVEL = 8.0
EVIDENCE = ROOT / "evidence" / "motion" / "FR-360-gapfill-cumulative-2026-10-05.json"
INDEX = ROOT / "index.html"

# No separate daylight master. Primary plate is the night scene.
NIGHT_ONLY = (
    "FR-01-117",
    "FR-01-118",
    "FR-01-119",
    "FR-01-120",
    "FR-01-121",
    "FR-01-122",
    "FR-01-123",
    "FR-01-124",
    "FR-01-210",
    "FR-01-226",
    "FR-01-242",
    "FR-01-258",
    "FR-01-274",
    "FR-01-290",
    "FR-01-294",
    "FR-01-353",
    "FR-01-362",
)

# Sideways-sweep clips already on main. Do not remake.
PREEXISTING = (
    "FR-01-125", "FR-01-127", "FR-01-131", "FR-01-133", "FR-01-135",
    "FR-01-136", "FR-01-137", "FR-01-139", "FR-01-140", "FR-01-141",
    "FR-01-143", "FR-01-144", "FR-01-150", "FR-01-152", "FR-01-154",
    "FR-01-155", "FR-01-156", "FR-01-160", "FR-01-171", "FR-01-172",
    "FR-01-175", "FR-01-185", "FR-01-188", "FR-01-190", "FR-01-192",
    "FR-01-199", "FR-01-201", "FR-01-204", "FR-01-205", "FR-01-206",
    "FR-01-215", "FR-01-221", "FR-01-222", "FR-01-223", "FR-01-231",
    "FR-01-235", "FR-01-236", "FR-01-237", "FR-01-238", "FR-01-239",
    "FR-01-247", "FR-01-249", "FR-01-251", "FR-01-252", "FR-01-254",
    "FR-01-255", "FR-01-263", "FR-01-270", "FR-01-283", "FR-01-299",
    "FR-01-302", "FR-01-306", "FR-01-311", "FR-01-316", "FR-01-319",
    "FR-01-331", "FR-01-332", "FR-01-338", "FR-01-352", "FR-01-364",
)


def clip_path(entry_id: str) -> Path:
    return ROOT / "assets" / f"{entry_id.lower()}-motion-10s-4x5.mp4"


def anchor_for(entry_id: str) -> tuple[Path, str]:
    n = entry_id.lower()
    day = ROOT / "assets" / f"{n}-daylight-4x5.png"
    if day.is_file():
        return day, "daylight"
    return ROOT / "assets" / f"{n}-4x5.png", "primary"


def load_captions() -> dict[str, str]:
    html = INDEX.read_text(encoding="utf-8")
    caps: dict[str, str] = {}
    for match in re.finditer(
        r'entry_id:\s*"(FR-01-\d{3})"[\s\S]*?caption:\s*"((?:\\.|[^"\\])*)"',
        html,
    ):
        caps[match.group(1)] = json.loads(f'"{match.group(2)}"')
    return caps


def ease(n: int) -> float:
    u = n / (FRAMES - 1)
    return 0.5 - 0.5 * math.cos(math.pi * u)


def _feasible(span0: float, span1: float, view: float, limit: float) -> tuple[float, float]:
    lo = max(0.0, span1 - view)
    hi = min(limit - view, span0)
    return lo, hi


def plan_path(scene: dict) -> dict:
    """Smooth zoom plus a one-direction pan that keeps the subject inside.

    The window is an axis-aligned sample of the still. Nothing is warped
    locally, so the landmark cannot morph. The origin eases in one direction.
    """
    x0, y0, x1, y1 = (float(v) for v in scene["subject"])
    if not (0 <= x0 < x1 <= PHOTO_W - 1 and 0 <= y0 < y1 <= PHOTO_H - 1):
        raise RuntimeError("subject box is outside the plate")
    zoom = float(scene["zoom"])
    pin_top = bool(scene.get("pin_top"))
    pin_origin = bool(scene.get("pin_origin"))
    max_top = scene.get("max_top")

    def windows(z_end: float) -> list[tuple[float, float, float]]:
        out = []
        for n in range(FRAMES):
            e = ease(n)
            z = 1.0 + (z_end - 1.0) * e
            vw = PHOTO_W / z
            vh = PHOTO_H / z
            lo, hi = _feasible(x0, x1, vw, PHOTO_W)
            if lo > hi + 1e-3:
                raise RuntimeError("subject wider than the window")
            top_lo, top_hi = _feasible(y0, y1, vh, PHOTO_H)
            if top_lo > top_hi + 1e-3:
                raise RuntimeError("subject taller than the window")
            left = lo + (hi - lo) * 0.72 * e
            top = top_lo + (top_hi - top_lo) * 0.35 * e
            if pin_origin:
                left = 0.0
                top = 0.0
                if left < lo - 1e-3 or left > hi + 1e-3 or top < top_lo - 1e-3 or top > top_hi + 1e-3:
                    raise RuntimeError("pinned origin crops the subject")
            elif pin_top:
                top = 0.0
                if top < top_lo - 1e-3 or top > top_hi + 1e-3:
                    raise RuntimeError("pinned top crops the subject")
            if max_top is not None and top > float(max_top) + 1e-3:
                top = float(max_top)
                if top < top_lo - 1e-3:
                    raise RuntimeError("top cap crops the subject")
            if left < -1e-3 or top < -1e-3 or left + vw > PHOTO_W + 1e-3 or top + vh > PHOTO_H + 1e-3:
                raise RuntimeError("window leaves the plate")
            if x0 < left - 1e-3 or x1 > left + vw + 1e-3 or y0 < top - 1e-3 or y1 > top + vh + 1e-3:
                raise RuntimeError("subject left the frame")
            out.append((left, top, z))
        return out

    z_end = zoom
    last_err = "no path"
    while z_end >= MIN_ZOOM:
        try:
            path = windows(z_end)
        except RuntimeError as exc:
            last_err = str(exc)
            z_end = round(z_end - 0.005, 3)
            continue
        lefts = [w[0] for w in path]
        tops = [w[1] for w in path]
        zs = [w[2] for w in path]
        for seq in (lefts, tops, zs):
            signs = []
            for i in range(1, len(seq)):
                d = seq[i] - seq[i - 1]
                if abs(d) > 1e-6:
                    signs.append(1 if d > 0 else -1)
                if abs(d) > 1.6:
                    raise RuntimeError("window jumped")
            if signs and any(s != signs[0] for s in signs):
                last_err = "window reversed direction"
                z_end = round(z_end - 0.005, 3)
                break
        else:
            travel = math.hypot(lefts[-1] - lefts[0], tops[-1] - tops[0])
            if zs[-1] < MIN_ZOOM and travel < MIN_TRAVEL:
                raise RuntimeError(
                    f"pan-zoom would crop the subject; largest safe move is zoom {zs[-1]:.3f} travel {travel:.1f}px"
                )
            return {
                "zoom_end": zs[-1],
                "travel_px": round(travel, 2),
                "window_end": [round(lefts[-1], 2), round(tops[-1], 2)],
                "windows": path,
            }
    raise RuntimeError(last_err)


def top_has_tip(plate: np.ndarray) -> bool:
    """Pin the top when it is not open sky, or a narrow spire rises into it.

    Open sky can take the zoom so the base of the landmark stays in frame.
    A spire that already meets the top of the plate stays pinned.
    """
    hsv = cv2.cvtColor(plate[:36], cv2.COLOR_BGR2HSV)
    v = hsv[:, :, 2].astype(np.float32)
    s = hsv[:, :, 1].astype(np.float32)
    sky = (v > 170) & (s < 70)
    if float(sky.mean()) < 0.62:
        return True
    col = v.mean(axis=0)
    med = float(np.median(col))
    dark = np.where(col < med - 55)[0]
    if len(dark) == 0:
        return False
    start = int(dark[0])
    prev = start
    runs: list[tuple[int, int]] = []
    for x in dark[1:]:
        x = int(x)
        if x <= prev + 2:
            prev = x
        else:
            runs.append((start, prev))
            start = prev = x
    runs.append((start, prev))
    for a, b in runs:
        width = b - a + 1
        if 4 <= width <= 40 and float(col[a : b + 1].min()) < med - 70:
            return True
    return False


def subject_for(plate: np.ndarray) -> dict:
    """One subject box with enough slack for a slow pan-zoom.

    The side inset is 18px. That is the slack the pan uses, so a centered
    landmark stays inside every frame and the window still moves. The top
    stays pinned when a tip or canopy is there.
    """
    pin_top = top_has_tip(plate)
    if pin_top:
        # Top row stays. The zoom spends the slack under the subject.
        y0, y1 = 0, 1044
        zoom = 1.045
    else:
        # Open sky may leave. The base of the plate stays inside.
        y0, y1 = 24, 1068
        zoom = 1.04
    return {
        "subject": (18, y0, 846, y1),
        "zoom": zoom,
        "pin_top": pin_top,
    }


def crop_plate(path: Path) -> np.ndarray:
    im = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if im is None:
        raise RuntimeError(f"missing anchor {path}")
    if im.shape[1] != PHOTO_W or im.shape[0] < PHOTO_H + 40:
        raise RuntimeError(f"{path.name} is {im.shape[1]}x{im.shape[0]}, expected {PHOTO_W}x>={PHOTO_H + 40}")
    # The label block sits under the 1080 photo. A dark foreground can
    # share the bar's tone; that is still the photo, so the crop stays
    # at the photo edge. Only a row that is already the flat bar fails.
    photo_bottom = im[PHOTO_H - 1]
    bar = im[PHOTO_H]
    gap = float(np.abs(photo_bottom.astype(np.int16) - bar.astype(np.int16)).mean())
    if gap < 0.8 and float(photo_bottom.std()) < 1.0 and float(bar.std()) < 1.0:
        raise RuntimeError(f"{path.name} bottom photo row is the label bar")
    return im[:PHOTO_H].copy()


def render_frame(plate: np.ndarray, left: float, top: float, z: float) -> np.ndarray:
    vw = PHOTO_W / z
    vh = PHOTO_H / z
    xs = left + (np.arange(PHOTO_W, dtype=np.float32) + 0.5) * (vw / PHOTO_W) - 0.5
    ys = top + (np.arange(PHOTO_H, dtype=np.float32) + 0.5) * (vh / PHOTO_H) - 0.5
    map_x = np.broadcast_to(xs, (PHOTO_H, PHOTO_W)).copy()
    map_y = np.broadcast_to(ys[:, None], (PHOTO_H, PHOTO_W)).copy()
    step = float(map_x[0, 1] - map_x[0, 0])
    if abs(step - (vw / PHOTO_W)) > 2e-4:
        raise RuntimeError("horizontal scale is not uniform")
    ystep = float(map_y[1, 0] - map_y[0, 0])
    if abs(ystep - (vh / PHOTO_H)) > 2e-4:
        raise RuntimeError("vertical scale is not uniform")
    if abs(step - ystep) > 2e-3:
        raise RuntimeError("zoom is not square")
    frame = cv2.remap(
        plate,
        map_x,
        map_y,
        interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0),
    )
    if frame.shape != (PHOTO_H, PHOTO_W, 3):
        raise RuntimeError(f"frame is {frame.shape}")
    if int(frame[0].min()) == 0 and float(frame[0].mean()) < 1.0:
        raise RuntimeError("frame has an empty edge")
    if int(frame[:, 0].min()) == 0 and float(frame[:, 0].mean()) < 1.0:
        raise RuntimeError("frame has an empty edge")
    return frame


def encode(plate: np.ndarray, windows: list[tuple[float, float, float]], dest: Path) -> float:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{PHOTO_W}x{PHOTO_H}",
        "-r", str(FPS), "-i", "-",
        "-frames:v", str(FRAMES),
        "-an", "-c:v", "libx264", "-profile:v", "high", "-level:v", "3.2",
        "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "fast",
        "-movflags", "+faststart",
        str(dest),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    assert proc.stdin is not None
    first = last = None
    try:
        for n, (left, top, z) in enumerate(windows):
            frame = render_frame(plate, left, top, z)
            if n == 0:
                first = frame
            elif n == FRAMES - 1:
                last = frame
            proc.stdin.write(frame.tobytes())
    finally:
        proc.stdin.close()
    err = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
    code = proc.wait()
    if code != 0:
        raise RuntimeError(f"ffmpeg failed\n{err[-2000:]}")
    if first is None or last is None:
        raise RuntimeError("did not render both ends")
    mae = float(np.mean(np.abs(first.astype(np.int16) - last.astype(np.int16))))
    if mae < 4.0:
        raise RuntimeError(f"ends MAE {mae:.2f} is a locked hold")
    return mae


def probe_clip(path: Path) -> dict:
    raw = subprocess.check_output(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,nb_frames,codec_name,pix_fmt,avg_frame_rate,duration",
            "-show_entries", "format=duration",
            "-of", "json", str(path),
        ]
    )
    data = json.loads(raw)
    stream = data["streams"][0]
    duration = float(stream.get("duration") or data["format"]["duration"])
    head = path.read_bytes()[:262144]
    moov = head.find(b"moov")
    mdat = head.find(b"mdat")
    return {
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "codec": stream["codec_name"],
        "pix_fmt": stream["pix_fmt"],
        "nb_frames": int(stream.get("nb_frames") or 0),
        "avg_frame_rate": stream.get("avg_frame_rate"),
        "duration": round(duration, 3),
        "faststart": moov > 0 and (mdat < 0 or moov < mdat),
    }


def assert_spec(info: dict) -> None:
    if info["width"] != PHOTO_W or info["height"] != PHOTO_H:
        raise RuntimeError(f"dims {info['width']}x{info['height']}")
    if info["codec"] != "h264" or info["pix_fmt"] != "yuv420p":
        raise RuntimeError(f"codec {info['codec']} {info['pix_fmt']}")
    if info["nb_frames"] != FRAMES:
        raise RuntimeError(f"frames {info['nb_frames']}")
    if abs(info["duration"] - 10.0) > 0.1:
        raise RuntimeError(f"duration {info['duration']}")
    if info["avg_frame_rate"] != f"{FPS}/1":
        raise RuntimeError(f"fps {info['avg_frame_rate']}")
    if not info["faststart"]:
        raise RuntimeError("moov is not before mdat")


def qc_decoded(path: Path, plate: np.ndarray, subject: tuple[int, int, int, int]) -> None:
    """Frame 0 is the full plate. The last frame still holds the subject and is not empty."""
    raw = subprocess.check_output(
        [
            "ffmpeg", "-v", "error", "-i", str(path),
            "-vf", "select=eq(n\\,0)+eq(n\\,239)", "-vsync", "0",
            "-f", "rawvideo", "-pix_fmt", "bgr24", "-",
        ]
    )
    frame_bytes = PHOTO_W * PHOTO_H * 3
    if len(raw) != frame_bytes * 2:
        raise RuntimeError(f"decoded {len(raw)} bytes, expected {frame_bytes * 2}")
    first = np.frombuffer(raw[:frame_bytes], dtype=np.uint8).reshape(PHOTO_H, PHOTO_W, 3)
    last = np.frombuffer(raw[frame_bytes:], dtype=np.uint8).reshape(PHOTO_H, PHOTO_W, 3)
    mae = float(np.mean(np.abs(first.astype(np.int16) - plate.astype(np.int16))))
    if mae > 8.0:
        raise RuntimeError(f"frame 0 MAE {mae:.2f} does not match the daylight plate")
    if float(last.std()) < 8.0:
        raise RuntimeError("last frame is flat")
    x0, y0, x1, y1 = subject
    # The subject was kept inside the window, so the last frame's central
    # mass should still carry the plate's detail rather than a border.
    crop = last[max(0, y0) : min(PHOTO_H, y1), max(0, x0) : min(PHOTO_W, x1)]
    if crop.size == 0 or float(crop.std()) < 6.0:
        raise RuntimeError("subject crop on the last frame is empty")
    black = np.all(last < 3, axis=2)
    if float(black.mean()) > 0.01:
        raise RuntimeError("last frame has a black border")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mean_v(plate: np.ndarray) -> float:
    hsv = cv2.cvtColor(plate, cv2.COLOR_BGR2HSV)
    return float(hsv[:, :, 2].mean())


def top_v(plate: np.ndarray) -> float:
    hsv = cv2.cvtColor(plate[: PHOTO_H // 5], cv2.COLOR_BGR2HSV)
    return float(hsv[:, :, 2].mean())


def bake(entry_id: str, caption: str, encode_file: bool) -> dict:
    anchor, kind = anchor_for(entry_id)
    row = {
        "entry_id": entry_id,
        "caption": caption,
        "method": "static-ambient",
        "variant": "ken-burns",
        "anchor": str(anchor.relative_to(ROOT)) if anchor.is_file() else str(anchor),
        "anchor_kind": kind,
        "crop": "864:1080:0:0",
        "approval_status": "unchanged",
        "attempts": 1,
        "status": "HOLD",
    }
    dest = clip_path(entry_id)
    partial = dest.with_suffix(".partial.mp4")
    try:
        if dest.is_file() and dest.stat().st_size > 0 and entry_id in PREEXISTING:
            raise RuntimeError("refusing to remake a clip that already exists on main")
        plate = crop_plate(anchor)
        chosen = subject_for(plate)
        row["subject"] = list(chosen["subject"])
        row["pin_top"] = chosen["pin_top"]
        row["mean_v"] = round(mean_v(plate), 2)
        row["top_v"] = round(top_v(plate), 2)
        scene = {
            "subject": chosen["subject"],
            "zoom": chosen["zoom"],
            "pin_top": chosen["pin_top"],
        }
        planned = plan_path(scene)
        row["zoom_end"] = planned["zoom_end"]
        row["travel_px"] = planned["travel_px"]
        row["window_end"] = planned["window_end"]
        if not encode_file:
            row["status"] = "planned"
            return row
        if partial.exists():
            partial.unlink()
        mae = encode(plate, planned["windows"], partial)
        info = probe_clip(partial)
        assert_spec(info)
        qc_decoded(partial, plate, chosen["subject"])
        partial.replace(dest)
        info["sha256"] = sha256(dest)
        info["bytes"] = dest.stat().st_size
        row["probe"] = info
        row["ends_mae"] = round(mae, 3)
        row["status"] = "shipped"
        row["file"] = str(dest.relative_to(ROOT))
    except Exception as exc:
        partial.unlink(missing_ok=True)
        if row.get("status") != "shipped":
            dest.unlink(missing_ok=True)
        row["error"] = str(exc)
        row["hold_reason"] = str(exc)
        row["status"] = "HOLD"
    return row


def _scene_span(html: str, entry_id: str) -> tuple[int, int]:
    key = f'entry_id: "{entry_id}"'
    start = html.find(key)
    if start < 0:
        raise RuntimeError(f"{entry_id} is not in index.html")
    if html.find(key, start + len(key)) >= 0:
        raise RuntimeError(f"{entry_id} appears more than once")
    obj = html.rfind("{", 0, start)
    depth = 0
    in_str = False
    esc = False
    for j in range(obj, len(html)):
        c = html[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return obj, j + 1
    raise RuntimeError(f"unclosed scene object {entry_id}")


def wire_index() -> int:
    """Add ▶ 360° data only for clips that exist. Leave every other field alone."""
    html = INDEX.read_text(encoding="utf-8")
    added = 0
    # Walk ids from the end so earlier offsets stay valid.
    ids = []
    for i in range(1, 366):
        entry_id = f"FR-01-{i:03d}"
        if clip_path(entry_id).is_file():
            ids.append(entry_id)
    for entry_id in reversed(ids):
        rel = f"assets/{entry_id.lower()}-motion-10s-4x5.mp4"
        a, b = _scene_span(html, entry_id)
        block = html[a:b]
        if f'motion_clip: "{rel}"' in block:
            continue
        if "motion_clip:" in block:
            raise RuntimeError(f"{entry_id} already has a different motion_clip")
        body = block[:-1].rstrip()
        if body.endswith(","):
            body = body[:-1].rstrip()
        if "has_360:" in body:
            body = re.sub(r"\n[ \t]*has_360:\s*true,?\s*", "\n", body)
            body = body.rstrip().rstrip(",")
        body = body + f',\n        has_360: true,\n        motion_clip: "{rel}"\n      }}'
        html = html[:a] + body + html[b:]
        added += 1
    if html.count("function stopCardMotion") != 1:
        raise RuntimeError("motion player was duplicated or dropped")
    if html.count('class="motion-tab"') != 1:
        raise RuntimeError("motion button template was duplicated or dropped")
    if html.count('id="f-daynight"') != 1:
        raise RuntimeError("day/night filter changed")
    INDEX.write_text(html, encoding="utf-8")
    return added


def _prior_rows() -> list[dict]:
    rows = []
    for name in (
        "FR-360-gapfill-pack1-2026-10-05.json",
        "FR-360-gapfill-pack2-2026-10-05.json",
    ):
        path = ROOT / "evidence" / "motion" / name
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for row in data.get("scenes") or []:
            row = dict(row)
            row["source"] = name
            rows.append(row)
    return rows


def base_catalog(captions: dict[str, str]) -> list[dict]:
    prior = {row["entry_id"]: row for row in _prior_rows()}
    night = set(NIGHT_ONLY)
    pre = set(PREEXISTING)
    catalog = []
    for i in range(1, 366):
        entry_id = f"FR-01-{i:03d}"
        if entry_id in prior:
            catalog.append(prior[entry_id])
            continue
        if entry_id in night:
            catalog.append({
                "entry_id": entry_id,
                "caption": captions.get(entry_id, ""),
                "method": "static-ambient",
                "status": "excluded-night-only",
                "hold_reason": "night-only scene; no daylight master",
            })
            continue
        if entry_id in pre:
            catalog.append({
                "entry_id": entry_id,
                "caption": captions.get(entry_id, ""),
                "method": "sideways-sweep",
                "status": "preexisting",
                "file": str(clip_path(entry_id).relative_to(ROOT)),
                "note": "clip already on main; not remade",
            })
            continue
        catalog.append({
            "entry_id": entry_id,
            "caption": captions.get(entry_id, ""),
            "method": "static-ambient",
            "status": "pending",
        })
    return catalog


def load_evidence(captions: dict[str, str]) -> dict:
    if EVIDENCE.is_file():
        return json.loads(EVIDENCE.read_text(encoding="utf-8"))
    return {
        "work_order": "wo-france-360-gapfill-2026-10-05",
        "pack": "gapfill-cumulative",
        "method": "static-ambient",
        "variant": "ken-burns",
        "i2v": "not used; Ken Burns pan-zoom on the daylight still",
        "supersedes_draft_prs": ["#42", "#43"],
        "contains_branches": [
            "cursor/fr-gapfill-pack2-static-8fc4",
            "cursor/fr-gapfill-static-ambient-380d",
        ],
        "spec": {
            "duration_s": 10.0,
            "tolerance_s": 0.1,
            "fps": FPS,
            "frames": FRAMES,
            "width": PHOTO_W,
            "height": PHOTO_H,
            "codec": "h264",
            "pix_fmt": "yuv420p",
            "faststart": True,
            "crop": "864:1080:0:0",
        },
        "approval_status": "unchanged",
        "scene_approval": "unchanged; no Cosmo QC",
        "escalated": False,
        "stop_reason": "",
        "consecutive_holds": 0,
        "night_only_excluded": list(NIGHT_ONLY),
        "preexisting_not_remade": list(PREEXISTING),
        "daylight_gap_before": 264,
        "scenes": base_catalog(captions),
    }


def write_evidence(payload: dict) -> None:
    scenes = payload["scenes"]
    holds = [r["entry_id"] for r in scenes if r.get("status") == "HOLD"]
    shipped = [r["entry_id"] for r in scenes if r.get("status") == "shipped" and r.get("method") == "static-ambient"]
    pending = [r["entry_id"] for r in scenes if r.get("status") in ("pending", "not-attempted")]
    payload["holds"] = holds
    payload["shipped"] = shipped
    payload["shipped_count"] = len(shipped)
    payload["daylight_gap_after"] = len(holds) + len(pending)
    payload["escalated"] = bool(payload.get("escalated"))
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    tmp = EVIDENCE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(EVIDENCE)


def run_encode(limit: int, plan_only: bool) -> int:
    captions = load_captions()
    payload = load_evidence(captions)
    if payload.get("escalated"):
        print("already escalated; not attempting more scenes", flush=True)
        return 3
    by_id = {row["entry_id"]: row for row in payload["scenes"]}
    streak = int(payload.get("consecutive_holds") or 0)
    attempted = 0
    stopped = False
    for i in range(25, 366):
        if attempted >= limit:
            break
        entry_id = f"FR-01-{i:03d}"
        row = by_id[entry_id]
        if row.get("status") in ("shipped", "HOLD", "excluded-night-only", "preexisting", "not-attempted"):
            continue
        if stopped:
            row.clear()
            row.update({
                "entry_id": entry_id,
                "caption": captions.get(entry_id, ""),
                "method": "static-ambient",
                "status": "not-attempted",
                "hold_reason": "stopped after 3 HOLDs in a row",
            })
            continue
        baked = bake(entry_id, captions.get(entry_id, ""), encode_file=not plan_only)
        by_id[entry_id] = baked
        attempted += 1
        brief = {k: v for k, v in baked.items() if k != "probe"}
        if "probe" in baked:
            brief["bytes"] = baked["probe"].get("bytes")
            brief["duration"] = baked["probe"].get("duration")
            brief["sha256"] = baked["probe"].get("sha256")
        print(json.dumps(brief), flush=True)
        if baked["status"] == "HOLD":
            streak += 1
            if streak >= 3:
                stopped = True
                payload["escalated"] = True
                payload["stop_reason"] = (
                    "3 consecutive different scenes HOLD: "
                    + ", ".join(
                        r["entry_id"]
                        for r in list(by_id.values())
                        if r.get("status") == "HOLD"
                    )[-80:]
                )
        elif baked["status"] in ("shipped", "planned"):
            streak = 0
    # Rewrite scenes in id order with the updated rows.
    payload["scenes"] = [by_id[f"FR-01-{i:03d}"] for i in range(1, 366)]
    payload["consecutive_holds"] = streak
    if not plan_only:
        write_evidence(payload)
        print(f"wrote {EVIDENCE.relative_to(ROOT)} attempted={attempted} streak={streak} escalated={payload['escalated']}", flush=True)
    return 3 if payload.get("escalated") else 0


def main() -> None:
    if "--wire" in sys.argv:
        added = wire_index()
        print(f"wired {added} new motion fields", flush=True)
        return
    if "--encode" not in sys.argv and "--plan" not in sys.argv:
        raise SystemExit("pass --plan, --encode, or --wire")
    limit = 40
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    code = run_encode(limit, plan_only="--plan" in sys.argv and "--encode" not in sys.argv)
    if code:
        raise SystemExit(code)


if __name__ == "__main__":
    main()
