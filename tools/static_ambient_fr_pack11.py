#!/usr/bin/env python3
"""France 360 pack 11 — static-camera ambient clips.

True image-to-video is not available in this environment, so the lateral
sweep prompt is not sent to a video model. This script does not orbit,
fake an orbit, pan, or zoom.

The camera stays locked on a genuine daylight 4:5 plate. The label bar
under the photo is cropped off (864x1080 from y=0) before any frame is
made. Only sky, water, foliage, and flags already in that plate are
displaced, and only inside their own masks, so architecture cannot smear,
spawn, or flip.

A plate with too little sky, water, foliage, or flag is encoded locked-off
(the same cropped frame for 10.0s). That is still static-ambient. A scene
that fails twice is HOLD and no clip is left behind. Night masters are
not read.
"""

from __future__ import annotations

import hashlib
import json
import math
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
# Daylight sky is bright. The top fifth of a night plate is not.
MIN_TOP_V = 90.0
# Life-mask share of the plate. Thinner than this is a locked-off clip.
MIN_LIFE = 0.04

# Final daylight 4:5 masters on main after pack10. Night-only scenes
# (no *-daylight-4x5.png) are not in this list.
# Pack1–pack10 already shipped earlier daylight windows and are not rebaked.
# HOLD FR-01-263 stays held and is not processed.
# Window FR-01-344–365 has no daylight 4:5 master for:
# 344, 346, 353, 355, 356, 362.
SCENES = (
    {"entry_id": "FR-01-345", "caption": "Îlot Mbouzi, Mamoudzou"},
    {"entry_id": "FR-01-347", "caption": "Plage de Saleccia, Santo-Pietro-di-Tenda"},
    {"entry_id": "FR-01-348", "caption": "Château du Lude, Le Lude"},
    {"entry_id": "FR-01-349", "caption": "Cathédrale Saint-Étienne, Toul"},
    {"entry_id": "FR-01-350", "caption": "Cathédrale Notre-Dame, Noyon"},
    {"entry_id": "FR-01-351", "caption": "Abbaye de Saint-Wandrille, Rives-en-Seine"},
    {"entry_id": "FR-01-352", "caption": "Phare des Baleines, Saint-Clément-des-Baleines"},
    {"entry_id": "FR-01-354", "caption": "Grand Barachois, Miquelon"},
    {"entry_id": "FR-01-357", "caption": "Îles de la Petite-Terre, La Désirade"},
    {"entry_id": "FR-01-358", "caption": "Plage des Hattes, Awala-Yalimapo"},
    {"entry_id": "FR-01-359", "caption": "Trou de Fer, Salazie"},
    {"entry_id": "FR-01-360", "caption": "Grand'Rivière, Grand'Rivière"},
    {"entry_id": "FR-01-361", "caption": "Mont Choungui, Chirongui"},
    {"entry_id": "FR-01-363", "caption": "Centre Pompidou, Paris"},
    {"entry_id": "FR-01-364", "caption": "Château d'If, Marseille"},
    {"entry_id": "FR-01-365", "caption": "Château de Peyrepertuse, Duilhac-sous-Peyrepertuse"},
)

# Gaps inside the processed window that have no genuine daylight 4:5 master.
SKIPPED_NO_DAYLIGHT = (
    "FR-01-344", "FR-01-346", "FR-01-353", "FR-01-355", "FR-01-356", "FR-01-362",
)


def anchor_path(entry_id: str) -> Path:
    return ROOT / "assets" / f"{entry_id.lower()}-daylight-4x5.png"


def clip_path(entry_id: str) -> Path:
    return ROOT / "assets" / f"{entry_id.lower()}-motion-10s-4x5.mp4"


def poster_path(entry_id: str) -> Path:
    return ROOT / "assets" / f"{entry_id.lower()}-motion-10s-4x5-poster.jpg"


def crop_plate(path: Path) -> np.ndarray:
    im = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if im is None:
        raise RuntimeError(f"missing anchor {path}")
    if im.shape[1] != PHOTO_W or im.shape[0] < PHOTO_H + 2:
        raise RuntimeError(f"{path.name} is {im.shape[1]}x{im.shape[0]}, expected {PHOTO_W}x>={PHOTO_H + 2}")
    # The label bar begins at y=1080. A dark or flat foreground can also
    # have a low standard deviation, so reject only a bottom row that
    # matches the bar itself.
    bar = im[PHOTO_H]
    photo_bottom = im[PHOTO_H - 1]
    gap = float(np.abs(photo_bottom.astype(np.int16) - bar.astype(np.int16)).mean())
    if gap < 3.0 and float(photo_bottom.std()) < 4:
        raise RuntimeError(f"{path.name} bottom photo row looks like the label bar")
    plate = im[:PHOTO_H].copy()
    return plate


def _components(mask: np.ndarray, pred) -> np.ndarray:
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=4)
    keep = np.zeros(mask.shape, np.uint8)
    for i in range(1, n):
        x, y, w, h, area = (int(v) for v in stats[i])
        if pred(x, y, w, h, area):
            keep[labels == i] = 255
    return keep


def build_masks(plate: np.ndarray) -> dict[str, np.ndarray]:
    hsv = cv2.cvtColor(plate, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    height, width = h.shape
    yy = np.arange(height)[:, None]

    overcast = (s < 70) & (v > 145)
    blue_sky = (h >= 90) & (h <= 125) & (s >= 15) & (s < 210) & (v > 145)
    sky_cand = (overcast | blue_sky).astype(np.uint8)
    sky_cand[(h >= 32) & (h <= 88) & (s > 48)] = 0
    sky_cand[((h < 12) | (h > 168)) & (s > 55)] = 0
    sky = _components(sky_cand, lambda x, y, w, hh, area: y <= 8 and area > 400)
    sky = cv2.erode(sky, np.ones((3, 3), np.uint8), iterations=1)

    blue_water = (h >= 88) & (h <= 128) & (s >= 40) & (s <= 180) & (v >= 35) & (v <= 185)
    water_cand = (blue_water & (sky == 0) & (yy > int(height * 0.28))).astype(np.uint8)
    water_cand[(h >= 35) & (h <= 88) & (s > 42)] = 0
    water = _components(
        water_cand,
        lambda x, y, w, hh, area: (
            area > 2200
            and w > 48
            and w > hh * 0.45
            and (y + hh / 2) > height * 0.40
        ),
    )
    water = cv2.erode(water, np.ones((3, 3), np.uint8), iterations=1)
    water = _components(
        water,
        lambda x, y, w, hh, area: area > 800 and w > 24 and hh < w * 2.0 and (y + hh / 2) > height * 0.45,
    )

    fol_cand = ((h >= 18) & (h <= 100) & (s >= 28) & (v >= 20) & (sky == 0) & (water == 0)).astype(np.uint8)
    foliage = _components(fol_cand, lambda x, y, w, hh, area: area > 120)
    foliage = cv2.erode(foliage, np.ones((3, 3), np.uint8), iterations=1)

    red = (((h <= 8) | (h >= 170)) & (s >= 150) & (v >= 100)).astype(np.uint8)
    blue = ((h >= 105) & (h <= 130) & (s >= 160) & (v >= 80) & (sky == 0)).astype(np.uint8)
    flag_cand = cv2.bitwise_or(red, blue)
    flag_cand[water > 0] = 0
    flags = _components(flag_cand, lambda x, y, w, hh, area: 40 <= area <= 4200 and hh < 180 and w < 160)
    flags = cv2.erode(flags, np.ones((2, 2), np.uint8), iterations=1)

    foliage[water > 0] = 0
    flags[foliage > 0] = 0
    flags[water > 0] = 0
    return {"sky": sky, "water": water, "foliage": foliage, "flags": flags}


def _factor(mask: np.ndarray, reach: float) -> np.ndarray:
    dist = cv2.distanceTransform((mask > 0).astype(np.uint8), cv2.DIST_L2, 3)
    return np.clip(dist / reach, 0, 1).astype(np.float32)


def _apply(out: np.ndarray, plate: np.ndarray, mask: np.ndarray, dx: np.ndarray, dy: np.ndarray) -> None:
    if not np.any(mask):
        return
    height, width = mask.shape
    xs = np.broadcast_to(np.arange(width, dtype=np.float32), (height, width)).copy()
    ys = np.broadcast_to(np.arange(height, dtype=np.float32)[:, None], (height, width)).copy()
    map_x = xs - dx
    map_y = ys - dy
    warped = cv2.remap(plate, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    src = cv2.remap(mask.astype(np.float32) / 255.0, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    use = (mask > 0) & (src > 0.985)
    out[use] = warped[use]


REACH = {"sky": 32.0, "water": 14.0, "foliage": 16.0, "flags": 6.0}


def render_frame(plate: np.ndarray, masks: dict[str, np.ndarray], factors: dict[str, np.ndarray], n: int) -> np.ndarray:
    t = n / FRAMES
    s1 = math.sin(2 * math.pi * t)
    s2 = math.sin(4 * math.pi * t)
    out = plate.copy()
    height, width = plate.shape[:2]
    ys = np.arange(height, dtype=np.float32)[:, None]
    xs = np.arange(width, dtype=np.float32)[None, :]

    if np.any(masks["foliage"]):
        phase = s1 * np.sin(ys * 0.035 + 0.4)
        dx = (4.6 * phase * factors["foliage"]).astype(np.float32)
        dy = (1.1 * s2 * factors["foliage"]).astype(np.float32)
        _apply(out, plate, masks["foliage"], dx, dy)

    if np.any(masks["water"]):
        dx = (3.4 * np.sin(2 * math.pi * t + ys * 0.045) * factors["water"]).astype(np.float32)
        dy = (1.6 * np.sin(4 * math.pi * t + xs * 0.05) * factors["water"]).astype(np.float32)
        _apply(out, plate, masks["water"], dx, dy)
        shimmer = (6.0 * np.sin(4 * math.pi * t + xs * 0.08 + ys * 0.03) * factors["water"]).astype(np.float32)
        region = masks["water"] > 0
        lifted = out.astype(np.float32)
        lifted[region] += shimmer[region, None]
        out[region] = np.clip(lifted[region], 0, 255).astype(np.uint8)

    if np.any(masks["flags"]):
        dx = (5.5 * np.sin(4 * math.pi * t + ys * 0.12) * factors["flags"]).astype(np.float32)
        dy = (1.2 * s2 * factors["flags"]).astype(np.float32)
        _apply(out, plate, masks["flags"], dx, dy)

    if np.any(masks["sky"]):
        dx = (22.0 * s1 * factors["sky"]).astype(np.float32)
        dy = (2.0 * s1 * factors["sky"]).astype(np.float32)
        _apply(out, plate, masks["sky"], dx, dy)
        breath = (10.0 * s1 * np.sin(xs * 0.03 + ys * 0.012) * factors["sky"]).astype(np.float32)
        region = masks["sky"] > 0
        lifted = out.astype(np.float32)
        lifted[region] += breath[region, None]
        out[region] = np.clip(lifted[region], 0, 255).astype(np.uint8)

    life = (masks["sky"] | masks["water"] | masks["foliage"] | masks["flags"]) > 0
    if not np.array_equal(out[~life], plate[~life]):
        raise RuntimeError("architecture pixel moved; refusing to encode")
    return out


def _ffmpeg_encode(frames, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{PHOTO_W}x{PHOTO_H}",
        "-r", str(FPS), "-i", "-",
        "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-crf", "18", "-preset", "medium", "-movflags", "+faststart",
        str(dest),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    assert proc.stdin is not None
    try:
        for frame in frames:
            proc.stdin.write(frame.tobytes())
    finally:
        proc.stdin.close()
    err = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
    code = proc.wait()
    if code != 0:
        raise RuntimeError(f"ffmpeg failed for {dest.name}\n{err[-2000:]}")


def encode_ambient(plate: np.ndarray, masks: dict[str, np.ndarray], dest: Path) -> None:
    factors = {name: _factor(mask, REACH[name]) for name, mask in masks.items()}

    def frames():
        for n in range(FRAMES):
            yield render_frame(plate, masks, factors, n)

    _ffmpeg_encode(frames(), dest)


def encode_locked(plate: np.ndarray, dest: Path) -> None:
    def frames():
        for _n in range(FRAMES):
            yield plate

    _ffmpeg_encode(frames(), dest)


def write_poster(plate: np.ndarray, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(dest), plate, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    if not ok:
        raise RuntimeError(f"poster write failed {dest}")


def coverage(masks: dict[str, np.ndarray]) -> dict[str, float]:
    total = float(PHOTO_H * PHOTO_W)
    return {name: round(float(np.count_nonzero(mask)) / total, 4) for name, mask in masks.items()}


def mean_v(plate: np.ndarray) -> float:
    hsv = cv2.cvtColor(plate, cv2.COLOR_BGR2HSV)
    return float(hsv[:, :, 2].mean())


def top_v(plate: np.ndarray) -> float:
    hsv = cv2.cvtColor(plate[: PHOTO_H // 5], cv2.COLOR_BGR2HSV)
    return float(hsv[:, :, 2].mean())


def probe_clip(path: Path) -> dict:
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,codec_name,pix_fmt,nb_frames,avg_frame_rate,duration:format=duration",
        "-of", "json", str(path),
    ]
    raw = subprocess.check_output(cmd, text=True)
    data = json.loads(raw)
    stream = data["streams"][0]
    duration = float(stream.get("duration") or data["format"]["duration"])
    head = path.read_bytes()[:262144]
    moov = head.find(b"moov")
    mdat = head.find(b"mdat")
    fast = moov > 0 and (mdat < 0 or moov < mdat)
    return {
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "codec": stream["codec_name"],
        "pix_fmt": stream["pix_fmt"],
        "nb_frames": int(stream.get("nb_frames") or 0),
        "avg_frame_rate": stream.get("avg_frame_rate"),
        "duration": round(duration, 3),
        "faststart": fast,
    }


def assert_spec(info: dict) -> None:
    if info["width"] != PHOTO_W or info["height"] != PHOTO_H:
        raise RuntimeError(f"dims {info['width']}x{info['height']}")
    if info["codec"] != "h264" or info["pix_fmt"] != "yuv420p":
        raise RuntimeError(f"codec {info['codec']} {info['pix_fmt']}")
    if info["nb_frames"] != FRAMES:
        raise RuntimeError(f"frames {info['nb_frames']}")
    if abs(info["duration"] - 10.0) > 0.05:
        raise RuntimeError(f"duration {info['duration']}")
    if not info["faststart"]:
        raise RuntimeError("moov is not before mdat")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def finish_clip(entry_id: str, plate: np.ndarray, tmp: Path) -> dict:
    info = probe_clip(tmp)
    assert_spec(info)
    dest = clip_path(entry_id)
    tmp.replace(dest)
    write_poster(plate, poster_path(entry_id))
    info["sha256"] = sha256(dest)
    info["bytes"] = dest.stat().st_size
    return info


def bake_scene(scene: dict) -> dict:
    entry_id = scene["entry_id"]
    row = {
        "entry_id": entry_id,
        "caption": scene["caption"],
        "method": "static-ambient",
        "anchor": str(anchor_path(entry_id).relative_to(ROOT)),
        "crop": "864:1080:0:0",
        "approval_status": "Candidate",
        "attempts": 0,
        "status": "HOLD",
    }
    tmp = clip_path(entry_id).with_suffix(".partial.mp4")
    try:
        plate = crop_plate(anchor_path(entry_id))
    except Exception as exc:
        row["attempts"] = 1
        row["error"] = str(exc)
        row["hold_reason"] = "anchor failed the daylight crop check"
        return row
    row["mean_v"] = round(mean_v(plate), 2)
    row["top_v"] = round(top_v(plate), 2)
    if row["top_v"] < MIN_TOP_V:
        row["attempts"] = 2
        row["hold_reason"] = f"cropped plate top-fifth V {row['top_v']} is below {MIN_TOP_V}; not a daylight plate"
        return row
    masks = build_masks(plate)
    cov = coverage(masks)
    row["coverage"] = cov
    life = sum(cov.values())
    row["life"] = round(life, 4)
    if tmp.exists():
        tmp.unlink()
    if life < MIN_LIFE:
        row["attempts"] = 1
        row["variant"] = "locked-off"
        try:
            encode_locked(plate, tmp)
            row["probe"] = finish_clip(entry_id, plate, tmp)
            row["status"] = "shipped"
            row["file"] = str(clip_path(entry_id).relative_to(ROOT))
        except Exception as exc:
            tmp.unlink(missing_ok=True)
            row["attempts"] = 2
            row["error"] = str(exc)
            row["hold_reason"] = "locked-off encode failed"
            clip_path(entry_id).unlink(missing_ok=True)
        return row
    row["variant"] = "ambient"
    row["attempts"] = 1
    try:
        encode_ambient(plate, masks, tmp)
        row["probe"] = finish_clip(entry_id, plate, tmp)
        row["status"] = "shipped"
        row["file"] = str(clip_path(entry_id).relative_to(ROOT))
        return row
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        clip_path(entry_id).unlink(missing_ok=True)
        row["attempt1_error"] = str(exc)
        row["attempts"] = 2
        row["variant"] = "locked-off"
        try:
            encode_locked(plate, tmp)
            row["probe"] = finish_clip(entry_id, plate, tmp)
            row["status"] = "shipped"
            row["file"] = str(clip_path(entry_id).relative_to(ROOT))
        except Exception as exc2:
            tmp.unlink(missing_ok=True)
            clip_path(entry_id).unlink(missing_ok=True)
            poster_path(entry_id).unlink(missing_ok=True)
            row["error"] = str(exc2)
            row["hold_reason"] = "ambient failed and locked-off retry failed"
            row["status"] = "HOLD"
    return row


def probe_scene(scene: dict) -> dict:
    plate = crop_plate(anchor_path(scene["entry_id"]))
    masks = build_masks(plate)
    cov = coverage(masks)
    return {
        "entry_id": scene["entry_id"],
        "caption": scene["caption"],
        "mean_v": round(mean_v(plate), 2),
        "top_v": round(top_v(plate), 2),
        "shape": list(plate.shape),
        "coverage": cov,
        "life": round(sum(cov.values()), 4),
    }


def main() -> None:
    only = [arg for arg in sys.argv[1:] if arg.startswith("FR-")]
    chosen = [scene for scene in SCENES if not only or scene["entry_id"] in only]
    if "--probe" in sys.argv:
        for scene in chosen:
            print(json.dumps(probe_scene(scene)), flush=True)
        return
    rows = []
    for scene in chosen:
        print(f"bake {scene['entry_id']}", flush=True)
        row = bake_scene(scene)
        rows.append(row)
        print(json.dumps({k: row[k] for k in ("entry_id", "status", "variant", "attempts", "life", "mean_v", "top_v") if k in row}), flush=True)
    evidence = {
        "work_order": "wo-france-360-2026-10-02",
        "pack": "pack11",
        "method": "static-ambient",
        "i2v": "unavailable in this environment (no video model and no image-to-video API). Lateral-sweep prompt was not sent. No orbit, no fake orbit, no pan, no zoom.",
        "spec": {
            "duration_s": 10.0,
            "fps": FPS,
            "frames": FRAMES,
            "width": PHOTO_W,
            "height": PHOTO_H,
            "codec": "h264",
            "pix_fmt": "yuv420p",
            "faststart": True,
            "crop": "864:1080:0:0",
        },
        "approval_status": "Candidate",
        "processed_window": "FR-01-344 through FR-01-365",
        "skipped_no_daylight": list(SKIPPED_NO_DAYLIGHT),
        "held_not_processed": ["FR-01-263"],
        "remaining_daylight_after_pack": [],
        "scenes": rows,
        "shipped": [row["entry_id"] for row in rows if row["status"] == "shipped"],
        "hold": [row["entry_id"] for row in rows if row["status"] == "HOLD"],
    }
    dest = ROOT / "evidence" / "motion" / "FR-360-pack11-2026-10-02.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {dest}", flush=True)
    print(f"shipped {len(evidence['shipped'])} hold {len(evidence['hold'])}", flush=True)


if __name__ == "__main__":
    main()
