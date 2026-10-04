#!/usr/bin/env python3
"""France sideways sweep.

Port of the Netherlands ``--sweep`` path only. A slow left-to-right glide
across one genuine daylight 16:9 plate. The label bar under the photo is
cropped off. An 864-wide window then eases across that plate. No locked
hold, orbit, zoom, roll, vertical move, or generated frames.

The default glide is center-anchored and travels 18% of the 1920-wide
plate. An off-center subject may pass ``subject_x`` and ``subject_span``
so the same 18% glide tracks that subject. ``window_start`` / ``window_end``
are used only when that 18% glide cannot hold the subject without leaving
the plate, or when the subject is wider than the 864 frame. The default
center math is unchanged.
"""

from __future__ import annotations

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
PLATE_W = 1920
# Share of the 1920-wide plate the window travels. Kept inside 15–20%.
SWEEP_TRAVEL_FRAC = 0.18
# These daylight plates compose a centered subject on the default path.
SUBJECT_X = PLATE_W / 2.0

# Pack 1. Spans are measured on the daylight 16:9 photo (top 1080 rows).
# Scenes whose distinct tips cannot all stay inside 864 are listed in
# SKIPPED and are not encoded.
SWEEP_SCENES = (
    # Palais des Ducs roof, including the Tour Philippe le Bon. The roof
    # block measured on the daylight plate is x 558–1377, wider than an
    # 18% glide can hold. This clip eases only across the slack that keeps
    # that roof, tower included, inside every frame with a 12px pad.
    {
        "entry_id": "FR-01-125",
        "n": 125,
        "held": "Palais des Ducs roof and Tour Philippe le Bon",
        "subject_x": 967.5,
        "subject_span": (558.0, 1377.0),
        "window_start": 525.0,
        "window_end": 546.0,
    },
    # Belfry shaft x 1077–1211, right of plate center. Same 18% glide,
    # aimed at the tower, so the shaft stays inside the 864 frame.
    {
        "entry_id": "FR-01-127",
        "n": 127,
        "held": "Belfry of Arras",
        "subject_x": 1144.0,
        "subject_span": (1077.0, 1211.0),
    },
    # Piton de la Fournaise summit on the caldera skyline, measured at
    # about x 1012. The dome is wider than 864. The held portion is
    # x 652–1372: wide enough to keep the summit, and short enough that
    # the glide does not collapse into a locked hold on this smooth plate.
    {
        "entry_id": "FR-01-131",
        "n": 131,
        "held": "Piton de la Fournaise summit",
        "subject_x": 1012.0,
        "subject_span": (652.0, 1372.0),
        "window_start": 520.0,
        "window_end": 640.0,
    },
    # Plage de Moya baobab and the cove it stands in. The canopy on the
    # daylight plate starts near x 588, the trunk sits under that crown,
    # and the inner cliff faces that close the cove run out to about
    # x 1380. Wider than an 18% glide can hold. This clip eases only
    # across the slack that keeps the whole tree and both cove sides
    # inside every frame with a 12px pad.
    {
        "entry_id": "FR-01-133",
        "n": 133,
        "held": "Plage de Moya baobab and cove",
        "subject_x": 977.5,
        "subject_span": (575.0, 1380.0),
        "window_start": 528.0,
        "window_end": 563.0,
    },
    # Grave field wider than 864, with the tall marker mass at about
    # x 540–750 kept inside. This clip eases only across the slack that
    # keeps x 500–1328 inside every frame with a 12px pad.
    {
        "entry_id": "FR-01-135",
        "n": 135,
        "held": "Normandy American Cemetery markers",
        "subject_x": 914.0,
        "subject_span": (500.0, 1328.0),
        "window_start": 476.0,
        "window_end": 488.0,
    },
    # Yvoire château tower. The crenellated crown, clock included, measures
    # about x 570–1348 on the daylight plate. The 18% aim walked the left
    # end off the frame. This clip eases only across the slack that keeps
    # the crown and the clock inside every frame with a 12px pad.
    {
        "entry_id": "FR-01-136",
        "n": 136,
        "held": "Yvoire château tower",
        "subject_x": 959.0,
        "subject_span": (570.0, 1348.0),
        "window_start": 496.0,
        "window_end": 558.0,
    },
    # Mer de Glace tongue in the valley center. The flanking ridges run
    # wider than 864 and are not separate spires of the glacier. This
    # clip eases only across the slack that keeps x 550–1370 inside
    # every frame with a 12px pad.
    {
        "entry_id": "FR-01-137",
        "n": 137,
        "held": "Mer de Glace tongue",
        "subject_x": 960.0,
        "subject_span": (550.0, 1370.0),
        "window_start": 518.0,
        "window_end": 538.0,
    },
    # Église Saint-Jean-Baptiste roof, left of plate center. Same 18%
    # glide, aimed at the roof measured x 589–998, so the church stays
    # inside the 864 frame.
    {
        "entry_id": "FR-01-139",
        "n": 139,
        "held": "Église Saint-Jean-Baptiste roof",
        "subject_x": 793.5,
        "subject_span": (589.0, 998.0),
    },
    # Saline Royale director's house, pediment included, measured
    # x 615–1311 before the wings merge into the full court. Wider
    # than an 18% glide can hold. This clip eases only across the
    # slack that keeps the house inside every frame with a 12px pad.
    {
        "entry_id": "FR-01-140",
        "n": 140,
        "held": "Saline Royale director's house",
        "subject_x": 963.0,
        "subject_span": (615.0, 1311.0),
        "window_start": 459.0,
        "window_end": 603.0,
    },
    # Dover Patrol obelisk stands left of plate center (x 400–488).
    # The 18% glide cannot aim at it without leaving the plate. This
    # clip eases from the plate's left edge across the slack that keeps
    # the shaft inside every frame with a 12px pad.
    {
        "entry_id": "FR-01-141",
        "n": 141,
        "held": "Dover Patrol obelisk",
        "subject_x": 444.0,
        "subject_span": (400.0, 488.0),
        "window_start": 0.0,
        "window_end": 388.0,
    },
    # Pack 2. Measured on the daylight 16:9 photo (top 1080 rows).
    # Calanques pinnacles. The high porphyry, skyline under y 400, runs
    # about x 1157–1900 and is wider than an 18% glide can hold. The
    # right shoulder is near the plate edge, so this clip eases only
    # across the slack that keeps that mass inside every frame.
    {
        "entry_id": "FR-01-143",
        "n": 143,
        "held": "Calanques de Piana pinnacles",
        "subject_x": 1528.5,
        "subject_span": (1157.0, 1900.0),
        "window_start": 1048.0,
        "window_end": 1056.0,
    },
    # Metz Cathedral. Buttress pinnacles rise from about x 600, and the
    # great spire already touches the top of the plate at about x 1056.
    # The nave continues past x 1420, wider than 864. This clip eases
    # only across the slack that keeps the pinnacles and the spire,
    # uncropped past the plate's top edge, inside every frame.
    {
        "entry_id": "FR-01-144",
        "n": 144,
        "held": "Metz Cathedral spire and buttress pinnacles",
        "subject_x": 1010.0,
        "subject_span": (600.0, 1420.0),
        "window_start": 568.0,
        "window_end": 588.0,
    },
    # Royal palms on the Barachois lawn. Crowns that reach above about
    # y 260 run x 141–948, wider than an 18% glide can hold. Some fronds
    # already touch the top of the plate. This clip eases only across
    # the slack that keeps those palms inside every frame.
    {
        "entry_id": "FR-01-150",
        "n": 150,
        "held": "Le Barachois royal palms",
        "subject_x": 544.5,
        "subject_span": (141.0, 948.0),
        "window_start": 96.0,
        "window_end": 129.0,
    },
    # Dziani Dzaha. The green crater water is wider than 864. The held
    # portion is the central lake, x 500–1280, long enough that the
    # crater still reads, and the glide is long enough that this smooth
    # plate does not collapse into a locked hold.
    {
        "entry_id": "FR-01-152",
        "n": 152,
        "held": "Dziani Dzaha crater lake",
        "subject_x": 890.0,
        "subject_span": (500.0, 1280.0),
        "window_start": 428.0,
        "window_end": 488.0,
    },
    # Fontenay church roof, about x 520–1480, wider than 864, with the
    # ridge turret at about x 1152–1276. This clip eases only across
    # the slack that keeps that turret, and the longest church portion
    # around it, inside every frame.
    {
        "entry_id": "FR-01-154",
        "n": 154,
        "held": "Abbaye de Fontenay church and ridge turret",
        "subject_x": 1000.0,
        "subject_span": (590.0, 1410.0),
        "window_start": 558.0,
        "window_end": 578.0,
    },
    # Tour Paoline, left of plate center but near it. The shaft on the
    # daylight plate is about x 886–986. Same 18% glide, aimed at the
    # tower, so the shaft stays inside the 864 frame.
    {
        "entry_id": "FR-01-155",
        "n": 155,
        "held": "Tour de Nonza",
        "subject_x": 936.0,
        "subject_span": (886.0, 986.0),
    },
    # Laon west towers. The two crowns and their shafts, from the left
    # wall at about x 703 to the right wall at about x 1535, are wider
    # than an 18% glide can hold. This clip eases only across the slack
    # that keeps both towers inside every frame with a 12px pad.
    {
        "entry_id": "FR-01-156",
        "n": 156,
        "held": "Laon Cathedral west towers",
        "subject_x": 1119.0,
        "subject_span": (703.0, 1535.0),
        "window_start": 683.0,
        "window_end": 691.0,
    },
    # Erbalunga. The Genoese tower crown is about x 844–969, and the
    # harbor houses continue to the right edge of the plate. Wider than
    # 864. This clip eases only across the slack that keeps the tower
    # and the houses through about x 1650 inside every frame.
    {
        "entry_id": "FR-01-160",
        "n": 160,
        "held": "Erbalunga tower and harbor houses",
        "subject_x": 1240.0,
        "subject_span": (830.0, 1650.0),
        "window_start": 798.0,
        "window_end": 818.0,
    },
)

# Not encoded. Distinct tips cannot all stay in one 864 frame while the
# window still moves.
SKIPPED = (
    {
        "entry_id": "FR-01-126",
        "held": "Château d'Angers banded towers",
        "reason": (
            "Conical tower tips on the daylight plate stand at about "
            "x 576, 718, 905, 1162, 1482, and 1538, and the shafts run "
            "about x 553–1666. That is wider than 864, so holding every "
            "tower would mean dropping one. Left without a clip."
        ),
    },
    {
        "entry_id": "FR-01-138",
        "held": "Château de Cheverny lanterns",
        "reason": (
            "Stone finials on the daylight plate reach about x 801–823 "
            "and x 1645–1659, with the central roof crest between them. "
            "The outer span is 858px. An 864 frame cannot keep both "
            "finials inside while the window still moves. Left without "
            "a clip."
        ),
    },
    {
        "entry_id": "FR-01-142",
        "held": "Porte Saint-Michel twin towers",
        "reason": (
            "Conical slate roofs on the daylight plate run from about "
            "x 448 on the left tower to about x 1446 on the right tower. "
            "That outer span is 998px, wider than 864, so holding both "
            "towers would mean dropping one. Left without a clip."
        ),
    },
    {
        "entry_id": "FR-01-157",
        "held": "Le Mans Cathedral chevet pinnacles",
        "reason": (
            "A stone pinnacle on the daylight plate peaks at about x 864, "
            "and the chevet crown's last high pinnacle ends near x 1740. "
            "The outer span is about 880px, wider than 864, so holding "
            "every pinnacle would mean dropping one. Left without a clip."
        ),
    },
    {
        "entry_id": "FR-01-158",
        "held": "Mulberry harbour caissons",
        "reason": (
            "The caisson line on the daylight plate runs from about "
            "x 400 to about x 1600. That is wider than 864, so holding "
            "every block would mean dropping one. Left without a clip."
        ),
    },
    {
        "entry_id": "FR-01-159",
        "held": "Lion de Belfort",
        "reason": (
            "The lion's head on the daylight plate is near x 400–700 and "
            "the body runs to about x 1600. The sculpture is wider than "
            "864. A window that holds the head cuts the hindquarters. "
            "Left without a clip."
        ),
    },
)


def sweep_paths(scene: dict) -> tuple[Path, Path]:
    n = int(scene["n"])
    anchor = ROOT / "assets" / f"fr-01-{n:03d}-daylight-16x9.png"
    dest = ROOT / "assets" / f"fr-01-{n:03d}-motion-10s-4x5.mp4"
    return anchor, dest


def load_sweep_plate(path: Path) -> np.ndarray:
    """Daylight 16:9 master with the label bar removed, as a 1920×1080 plate.

    The photo rows are already 1920×1080. They are not resampled. A plate that
    is not already that size is scaled to it. No new picture is generated.
    """
    im = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if im is None:
        raise SystemExit(f"missing daylight master {path}")
    if im.shape[0] < PHOTO_H:
        raise SystemExit(f"{path} is {im.shape[1]}x{im.shape[0]}")
    plate = im[:PHOTO_H]
    if plate.shape[1] != PLATE_W or plate.shape[0] != PHOTO_H:
        plate = cv2.resize(plate, (PLATE_W, PHOTO_H), interpolation=cv2.INTER_LANCZOS4)
    if plate.shape != (PHOTO_H, PLATE_W, 3):
        raise SystemExit(f"sweep plate {path} is {plate.shape}")
    return plate


def sweep_x(
    n: int,
    subject_x: float = SUBJECT_X,
    bounds: tuple[float, float] | None = None,
) -> float:
    """Origin of the 864-wide window. Left to right, ease in and out, no vertical.

    ``subject_x`` defaults to the plate center. Passing the same center leaves
    the glide identical. An off-center landmark passes its own center.

    ``bounds`` is an explicit (start, end) pair for one scene whose subject
    cannot be held by that centered 18% glide without leaving the plate.
    The default path does not use it.
    """
    u = n / (FRAMES - 1)
    ease = 0.5 - 0.5 * math.cos(math.pi * u)
    if bounds is not None:
        start, end = bounds
        return start + (end - start) * ease
    travel = PLATE_W * SWEEP_TRAVEL_FRAC
    # Mid-glide puts the subject on the center of the 864 frame.
    mid = subject_x - (PHOTO_W / 2.0)
    return (mid - travel / 2.0) + travel * ease


def assert_sweep_path(subject_x: float = SUBJECT_X) -> None:
    xs = [sweep_x(n, subject_x) for n in range(FRAMES)]
    travel = xs[-1] - xs[0]
    frac = travel / PLATE_W
    if not (0.15 - 1e-9 <= frac <= 0.20 + 1e-9):
        raise SystemExit(f"sweep travel {frac:.3f} of plate width is outside 15–20%")
    if xs[0] >= xs[-1]:
        raise SystemExit("sweep does not move left to right")
    for i in range(1, FRAMES):
        if xs[i] + 1e-6 < xs[i - 1]:
            raise SystemExit("sweep reversed direction")
    half = PHOTO_W / 2.0
    for x in xs:
        if x < -1e-3 or x + PHOTO_W > PLATE_W + 1e-3:
            raise SystemExit(f"window {x:.2f} leaves the plate")
        subject_in_frame = subject_x - x
        if not (0.0 <= subject_in_frame <= PHOTO_W):
            raise SystemExit("subject left the frame")
        # Middle half of the frame. The glide is symmetric about the subject,
        # so the window never runs past it to the edge of the plate.
        if not (PHOTO_W * 0.25 <= subject_in_frame <= PHOTO_W * 0.75):
            raise SystemExit(f"subject left the middle half at window {x:.2f}")
        if abs((x + half) - subject_x) - (travel / 2.0) > 0.05:
            raise SystemExit("window traveled past the subject")


def assert_span_in_frame(
    subject_x: float,
    span: tuple[float, float],
    bounds: tuple[float, float] | None = None,
) -> None:
    """The whole subject, not only its center, stays inside every frame."""
    left, right = span
    if not (left < subject_x < right):
        raise SystemExit("subject center is outside its span")
    pad = 12.0
    for n in range(FRAMES):
        x = sweep_x(n, subject_x, bounds)
        if left < x + pad or right > x + PHOTO_W - pad:
            raise SystemExit(
                f"subject {left:.1f}-{right:.1f} leaves the frame at {n} window {x:.1f}"
            )


def assert_held_glide(bounds: tuple[float, float]) -> None:
    """A shorter left-to-right glide that stays on the plate.

    Used only when the centered 18% path cannot hold the subject. The default
    center sweep is not checked here.
    """
    start, end = bounds
    if not end > start:
        raise SystemExit("held glide does not move left to right")
    xs = [sweep_x(n, bounds=bounds) for n in range(FRAMES)]
    if abs(xs[0] - start) > 1e-6 or abs(xs[-1] - end) > 1e-6:
        raise SystemExit("held glide did not ease across its window")
    for i in range(1, FRAMES):
        if xs[i] + 1e-6 < xs[i - 1]:
            raise SystemExit("held glide reversed direction")
    for x in xs:
        if x < -1e-3 or x + PHOTO_W > PLATE_W + 1e-3:
            raise SystemExit(f"held glide window {x:.2f} leaves the plate")


def render_sweep_frame(
    plate: np.ndarray,
    n: int,
    subject_x: float = SUBJECT_X,
    bounds: tuple[float, float] | None = None,
) -> np.ndarray:
    x = np.float32(sweep_x(n, subject_x, bounds))
    map_x = np.broadcast_to(np.arange(PHOTO_W, dtype=np.float32) + x, (PHOTO_H, PHOTO_W)).copy()
    map_y = np.broadcast_to(np.arange(PHOTO_H, dtype=np.float32)[:, None], (PHOTO_H, PHOTO_W)).copy()
    # One source pixel per output pixel, and the row index never changes.
    # A window origin past 1024 is not an exact float32, so the first step
    # can be off by one ulp. That is not a scale change. The default glide
    # stays under that origin and still uses the tighter check. An aimed
    # origin below 1024 can miss the same way; one ulp there is still not
    # a scale change, and the default center math is untouched.
    step = float(map_x[0, 1] - map_x[0, 0])
    limit = 2e-4 if bounds is not None else 1e-5
    if bounds is None and subject_x != SUBJECT_X:
        limit = max(limit, 6.2e-5)
    if abs(step - 1.0) > limit:
        raise SystemExit("sweep changed scale")
    if float(map_y[0, 0]) != 0.0 or float(map_y[-1, 0]) != float(PHOTO_H - 1):
        raise SystemExit("sweep moved vertically")
    frame = cv2.remap(
        plate,
        map_x,
        map_y,
        interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0),
    )
    if frame.shape != (PHOTO_H, PHOTO_W, 3):
        raise SystemExit(f"sweep frame is {frame.shape}")
    return frame


def encode_sweep(
    plate: np.ndarray,
    dest: Path,
    subject_x: float = SUBJECT_X,
    bounds: tuple[float, float] | None = None,
) -> float:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-s",
        f"{PHOTO_W}x{PHOTO_H}",
        "-r",
        str(FPS),
        "-i",
        "-",
        "-frames:v",
        str(FRAMES),
        "-an",
        "-c:v",
        "libx264",
        "-profile:v",
        "high",
        "-level:v",
        "3.2",
        "-pix_fmt",
        "yuv420p",
        "-crf",
        "18",
        "-preset",
        "medium",
        "-movflags",
        "+faststart",
        str(dest),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    assert proc.stdin is not None
    first = last = None
    try:
        for n in range(FRAMES):
            frame = render_sweep_frame(plate, n, subject_x, bounds)
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
        raise SystemExit(f"ffmpeg failed for {dest}\n{err[-2000:]}")
    if first is None or last is None:
        raise SystemExit(f"sweep did not render {dest}")
    mae = float(np.mean(np.abs(first.astype(np.int16) - last.astype(np.int16))))
    if mae < 8.0:
        raise SystemExit(f"{dest} sweep MAE {mae:.2f} is a locked hold")
    return mae


def probe_sweep(path: Path) -> dict:
    raw = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,nb_frames,codec_name,pix_fmt,avg_frame_rate",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ]
    )
    return json.loads(raw)


def scene_bounds(scene: dict) -> tuple[float, tuple[float, float] | None, tuple[float, float] | None]:
    subject_x = float(scene.get("subject_x", SUBJECT_X))
    span = scene.get("subject_span")
    bounds = None
    if "window_start" in scene:
        bounds = (float(scene["window_start"]), float(scene["window_end"]))
        assert_held_glide(bounds)
    elif subject_x != SUBJECT_X or span is not None:
        assert_sweep_path(subject_x)
    if span is not None:
        span = (float(span[0]), float(span[1]))
        assert_span_in_frame(subject_x, span, bounds)
    return subject_x, span, bounds


def run_sweep(only: list[str], encode: bool) -> None:
    assert_sweep_path()
    known = {s["entry_id"] for s in SWEEP_SCENES}
    if only and any(item not in known for item in only):
        raise SystemExit("refusing ids outside the sideways-sweep pack")
    scenes = [s for s in SWEEP_SCENES if not only or s["entry_id"] in only]
    for scene in scenes:
        anchor, dest = sweep_paths(scene)
        if not anchor.is_file():
            raise SystemExit(f"missing daylight master {anchor}")
        subject_x, span, bounds = scene_bounds(scene)
        if not encode:
            print(
                json.dumps(
                    {
                        "entry_id": scene["entry_id"],
                        "held": scene["held"],
                        "subject_x": subject_x,
                        "subject_span": span,
                        "window": bounds,
                        "anchor": str(anchor.relative_to(ROOT)),
                    }
                )
            )
            continue
        plate = load_sweep_plate(anchor)
        mae = encode_sweep(plate, dest, subject_x, bounds)
        info = probe_sweep(dest)
        stream = info["streams"][0]
        duration = float(info["format"]["duration"])
        if int(stream["width"]) != PHOTO_W or int(stream["height"]) != PHOTO_H:
            raise SystemExit(f"{dest} is {stream['width']}x{stream['height']}")
        if abs(duration - 10.0) > 0.05:
            raise SystemExit(f"{dest} duration {duration}")
        if stream["codec_name"] != "h264" or stream["pix_fmt"] != "yuv420p":
            raise SystemExit(f"{dest} codec {stream['codec_name']} {stream['pix_fmt']}")
        if stream.get("avg_frame_rate") != f"{FPS}/1":
            raise SystemExit(f"{dest} frame rate {stream.get('avg_frame_rate')}")
        if str(stream.get("nb_frames")) != str(FRAMES):
            raise SystemExit(f"{dest} frames {stream.get('nb_frames')}")
        print(
            json.dumps(
                {
                    "entry_id": scene["entry_id"],
                    "method": "sideways-sweep",
                    "held": scene["held"],
                    "subject_span": span,
                    "window": bounds if bounds is not None else [sweep_x(0, subject_x), sweep_x(FRAMES - 1, subject_x)],
                    "anchor": str(anchor.relative_to(ROOT)),
                    "out": str(dest.relative_to(ROOT)),
                    "travel_frac": (
                        round((bounds[1] - bounds[0]) / PLATE_W, 4)
                        if bounds is not None
                        else SWEEP_TRAVEL_FRAC
                    ),
                    "ends_mae": round(mae, 3),
                    "width": int(stream["width"]),
                    "height": int(stream["height"]),
                    "nb_frames": stream.get("nb_frames"),
                    "duration_s": duration,
                    "codec": stream["codec_name"],
                    "pix_fmt": stream["pix_fmt"],
                    "fps": stream["avg_frame_rate"],
                }
            )
        )
    if not only:
        for skipped in SKIPPED:
            print(json.dumps({"entry_id": skipped["entry_id"], "skipped": True, "held": skipped["held"], "reason": skipped["reason"]}))


def main() -> None:
    if "--sweep" not in sys.argv and "--plan" not in sys.argv:
        raise SystemExit("pass --sweep to encode, or --plan to print geometry")
    only = [a for a in sys.argv[1:] if a.startswith("FR-")]
    run_sweep(only, encode="--sweep" in sys.argv)


if __name__ == "__main__":
    main()
