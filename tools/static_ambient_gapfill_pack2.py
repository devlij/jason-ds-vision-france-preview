#!/usr/bin/env python3
"""France 360 gap-fill pack 2 — static-ambient Ken Burns clips.

Same delivery path as the 2 October France packs: a genuine daylight 4:5
master, label bar cropped off, 10.0s 864x1080 H.264. Real image-to-video is
not used. The motion is a smooth slow Ken Burns pan-zoom on that still.
Night-only scenes are not read. A scene that fails once is HOLD and is not
retried. Three HOLDs in a row stop the pack.
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
MIN_TOP_V = 90.0
# A move smaller than this reads as a locked hold.
MIN_ZOOM = 1.018
MIN_TRAVEL = 8.0

# Next 12 daylight scenes after pack 1 (FR-01-001–012), lowest id first.
# Night-only plates are not in this range. Subject boxes are on the cropped
# 864x1080 photo, inclusive. They are the landmark that must stay inside
# every frame.
SCENES = (
    # Openwork spire meets the top of the plate. Keep that edge pinned.
    {"entry_id": "FR-01-013", "caption": "Strasbourg Cathedral, Strasbourg", "anchor": "primary", "subject": (160, 0, 780, 1020), "zoom": 1.045, "pin_top": True},
    # Crest of the dune sits under the sky. The ridge is the subject.
    {"entry_id": "FR-01-014", "caption": "Dune du Pilat, La Teste-de-Buch", "anchor": "primary", "subject": (30, 340, 830, 1040), "zoom": 1.04},
    # Rim overlook. The canyon walls start below the sky.
    {"entry_id": "FR-01-015", "caption": "Gorges du Verdon, La Palud-sur-Verdon", "anchor": "primary", "subject": (20, 220, 840, 1040), "zoom": 1.035},
    # Canal façades, with the alpine ridge entering from the upper right.
    {"entry_id": "FR-01-016", "caption": "Annecy old town canals, Annecy", "anchor": "primary", "subject": (40, 90, 830, 1020), "zoom": 1.04},
    # Flèche tip is near the top center of the courtyard view.
    {"entry_id": "FR-01-017", "caption": "Sainte-Chapelle, Paris", "anchor": "primary", "subject": (250, 30, 800, 1000), "zoom": 1.05, "max_top": 12.0},
    # Luxor Obelisk tip sits just under the sky, fountains below.
    {"entry_id": "FR-01-018", "caption": "Place de la Concorde, Paris", "anchor": "primary", "subject": (120, 90, 760, 1000), "zoom": 1.045},
    # Clock pavilion on the left, river façade running the quay.
    {"entry_id": "FR-01-019", "caption": "Musée d'Orsay, Paris", "anchor": "primary", "subject": (40, 180, 830, 1020), "zoom": 1.04},
    # Gilded dome tip is the high point on the esplanade axis.
    {"entry_id": "FR-01-020", "caption": "Hôtel des Invalides, Paris", "anchor": "primary", "subject": (80, 110, 800, 1000), "zoom": 1.045},
    # Crown sculpture is right of center and close to the top.
    {"entry_id": "FR-01-021", "caption": "Opéra Garnier, Paris", "anchor": "primary", "subject": (80, 40, 840, 1000), "zoom": 1.04, "max_top": 20.0},
    # Gilded pylons stand near both edges of the bridge.
    {"entry_id": "FR-01-022", "caption": "Pont Alexandre III, Paris", "anchor": "primary", "subject": (40, 280, 840, 1020), "zoom": 1.04},
    # Lantern is high and to the right; the portico spreads left.
    {"entry_id": "FR-01-023", "caption": "Panthéon, Paris", "anchor": "primary", "subject": (80, 20, 850, 1000), "zoom": 1.04, "max_top": 8.0},
    # Tour de l'Horloge rises at the right edge of the river front.
    {"entry_id": "FR-01-024", "caption": "Conciergerie, Paris", "anchor": "primary", "subject": (40, 100, 850, 1000), "zoom": 1.04, "max_top": 40.0},
)


def anchor_path(scene: dict) -> Path:
    n = scene["entry_id"].lower()
    if scene["anchor"] == "daylight":
        return ROOT / "assets" / f"{n}-daylight-4x5.png"
    return ROOT / "assets" / f"{n}-4x5.png"


def clip_path(entry_id: str) -> Path:
    return ROOT / "assets" / f"{entry_id.lower()}-motion-10s-4x5.mp4"


def crop_plate(path: Path) -> np.ndarray:
    im = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if im is None:
        raise RuntimeError(f"missing anchor {path}")
    if im.shape[1] != PHOTO_W or im.shape[0] < PHOTO_H + 2:
        raise RuntimeError(f"{path.name} is {im.shape[1]}x{im.shape[0]}, expected {PHOTO_W}x>={PHOTO_H + 2}")
    bar = im[PHOTO_H]
    photo_bottom = im[PHOTO_H - 1]
    gap = float(np.abs(photo_bottom.astype(np.int16) - bar.astype(np.int16)).mean())
    if gap < 3.0 and float(photo_bottom.std()) < 4:
        raise RuntimeError(f"{path.name} bottom photo row looks like the label bar")
    return im[:PHOTO_H].copy()


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
            # Aim the window at the subject center, then clamp so the
            # subject stays inside and the window stays on the plate.
            lo, hi = _feasible(x0, x1, vw, PHOTO_W)
            if lo > hi + 1e-3:
                raise RuntimeError("subject wider than the window")
            top_lo, top_hi = _feasible(y0, y1, vh, PHOTO_H)
            if top_lo > top_hi + 1e-3:
                raise RuntimeError("subject taller than the window")
            # Ease from the full frame toward a left-to-right origin inside
            # the slack, short of the edge that would put the subject on
            # the frame border.
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
            windows = windows(z_end)
        except RuntimeError as exc:
            last_err = str(exc)
            z_end = round(z_end - 0.005, 3)
            continue
        lefts = [w[0] for w in windows]
        tops = [w[1] for w in windows]
        zs = [w[2] for w in windows]
        # One direction, no reversal, no jump.
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
                "windows": windows,
            }
    raise RuntimeError(last_err)


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
    return frame


def encode(plate: np.ndarray, windows: list[tuple[float, float, float]], dest: Path) -> float:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{PHOTO_W}x{PHOTO_H}",
        "-r", str(FPS), "-i", "-",
        "-frames:v", str(FRAMES),
        "-an", "-c:v", "libx264", "-profile:v", "high", "-level:v", "3.2",
        "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "medium",
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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def top_v(plate: np.ndarray) -> float:
    hsv = cv2.cvtColor(plate[: PHOTO_H // 5], cv2.COLOR_BGR2HSV)
    return float(hsv[:, :, 2].mean())


def mean_v(plate: np.ndarray) -> float:
    hsv = cv2.cvtColor(plate, cv2.COLOR_BGR2HSV)
    return float(hsv[:, :, 2].mean())


def bake(scene: dict, encode_file: bool) -> dict:
    entry_id = scene["entry_id"]
    anchor = anchor_path(scene)
    row = {
        "entry_id": entry_id,
        "caption": scene["caption"],
        "method": "static-ambient",
        "variant": "ken-burns",
        "anchor": str(anchor.relative_to(ROOT)),
        "crop": "864:1080:0:0",
        "subject": list(scene["subject"]),
        "approval_status": "unchanged",
        "attempts": 1,
        "status": "HOLD",
    }
    dest = clip_path(entry_id)
    partial = dest.with_suffix(".partial.mp4")
    try:
        plate = crop_plate(anchor)
        row["mean_v"] = round(mean_v(plate), 2)
        row["top_v"] = round(top_v(plate), 2)
        if row["top_v"] < MIN_TOP_V:
            row["hold_reason"] = f"cropped plate top-fifth V {row['top_v']} is below {MIN_TOP_V}; not a daylight plate"
            return row
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
        partial.replace(dest)
        info["sha256"] = sha256(dest)
        info["bytes"] = dest.stat().st_size
        row["probe"] = info
        row["ends_mae"] = round(mae, 3)
        row["status"] = "shipped"
        row["file"] = str(dest.relative_to(ROOT))
    except Exception as exc:
        partial.unlink(missing_ok=True)
        dest.unlink(missing_ok=True)
        row["error"] = str(exc)
        row["hold_reason"] = str(exc)
        row["status"] = "HOLD"
    return row


def main() -> None:
    encode_file = "--encode" in sys.argv
    if not encode_file and "--plan" not in sys.argv:
        raise SystemExit("pass --plan or --encode")
    streak = 0
    rows = []
    stopped = False
    for scene in SCENES:
        if stopped:
            rows.append({
                "entry_id": scene["entry_id"],
                "caption": scene["caption"],
                "method": "static-ambient",
                "status": "not-attempted",
                "hold_reason": "stopped after 3 HOLDs in a row",
            })
            continue
        row = bake(scene, encode_file)
        rows.append(row)
        print(json.dumps({k: v for k, v in row.items() if k != "probe"} | ({"probe": row.get("probe")} if "probe" in row else {})), flush=True)
        if row["status"] == "HOLD":
            streak += 1
            if streak >= 3:
                stopped = True
        elif row["status"] == "shipped":
            streak = 0
    if encode_file:
        out = ROOT / "evidence" / "motion" / "FR-360-gapfill-pack2-2026-10-05.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "work_order": "wo-france-360-gapfill-2026-10-05",
            "pack": "gapfill-pack2",
            "method": "static-ambient",
            "i2v": "not used; Ken Burns pan-zoom on the daylight still",
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
            "escalated": stopped,
            "night_only_excluded": 17,
            "daylight_gap_before": 276,
            "daylight_gap_after": 276 - len([r for r in rows if r["status"] == "shipped"]),
            "next_entry_id": "FR-01-025",
            "scenes": rows,
            "holds": [r["entry_id"] for r in rows if r["status"] == "HOLD"],
            "shipped": [r["entry_id"] for r in rows if r["status"] == "shipped"],
        }
        out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {out.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    main()
