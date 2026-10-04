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
    # Pack 3. Measured on the daylight 16:9 photo (top 1080 rows).
    # Cluny. The surviving octagonal tower and the smaller tower beside
    # it, tips included, measure about x 1020–1420. That fits an 18%
    # glide aimed at the pair, so the towers stay inside the 864 frame.
    {
        "entry_id": "FR-01-171",
        "n": 171,
        "held": "Cluny Abbey octagonal tower and the tower beside it",
        "subject_x": 1220.0,
        "subject_span": (1020.0, 1420.0),
    },
    # Aiguilles de Bavella. The high granite needles on the daylight
    # plate run about x 291–938, wider than an 18% glide can hold.
    # This clip eases only across the slack that keeps every needle
    # inside every frame with a 12px pad.
    {
        "entry_id": "FR-01-172",
        "n": 172,
        "held": "Aiguilles de Bavella granite needles",
        "subject_x": 614.5,
        "subject_span": (291.0, 938.0),
        "window_start": 86.0,
        "window_end": 279.0,
    },
    # Château de Falaise. The curtain and far-left tower begin about
    # x 948, the keep rises about x 1152–1311, and the round tower
    # ends about x 1543. The whole castle is wider than an 18% glide
    # can hold. This clip is a short glide centered on that span, so
    # the curtain, the far-left tower, the keep, and the round tower
    # stay inside every frame.
    {
        "entry_id": "FR-01-175",
        "n": 175,
        "held": "Château de Falaise curtain, keep, and round tower",
        "subject_x": 1237.5,
        "subject_span": (910.0, 1565.0),
        "window_start": 765.0,
        "window_end": 845.0,
    },
    # Mamoudzou. The white minaret and the mosque mass under it measure
    # about x 1390–1580, right of plate center. An 18% glide aimed at
    # that mass leaves the plate. This clip eases across the on-plate
    # slack that keeps the minaret inside every frame with a 12px pad.
    {
        "entry_id": "FR-01-185",
        "n": 185,
        "held": "Mamoudzou minaret",
        "subject_x": 1485.0,
        "subject_span": (1390.0, 1580.0),
        "window_start": 728.0,
        "window_end": 1056.0,
    },
    # Tour de Porto. The round tower and the rock it stands on measure
    # about x 560–810. The old window walked past that mass. This clip
    # is a short glide centered on the tower, so the crown and the
    # rock stay inside every frame.
    {
        "entry_id": "FR-01-188",
        "n": 188,
        "held": "Tour de Porto and its rock",
        "subject_x": 685.0,
        "subject_span": (560.0, 810.0),
        "window_start": 223.0,
        "window_end": 283.0,
    },
    # Pack 4. Measured on the daylight 16:9 photo (top 1080 rows).
    # Château de Brissac. The tall block, corner towers included, measures
    # about x 590–1330. That is wider than an 18% glide can hold. This
    # clip eases only across the slack that keeps the château inside
    # every frame with a 12px pad.
    {
        "entry_id": "FR-01-190",
        "n": 190,
        "held": "Château de Brissac",
        "subject_x": 960.0,
        "subject_span": (590.0, 1330.0),
        "window_start": 478.0,
        "window_end": 578.0,
    },
    # Clermont-Ferrand cathedral. The dark stone mass and the spire,
    # whose tip sits near the top of the plate at about x 1217, measure
    # about x 766–1380. Wider than an 18% glide can hold. This clip
    # eases only across the slack that keeps the spire, uncropped past
    # the plate's top edge, and the cathedral mass inside every frame.
    {
        "entry_id": "FR-01-192",
        "n": 192,
        "held": "Clermont-Ferrand Cathedral spire",
        "subject_x": 1073.0,
        "subject_span": (766.0, 1380.0),
        "window_start": 528.0,
        "window_end": 754.0,
    },
    # Notre-Dame-des-Laves. The church and its bell tower measure about
    # x 580–1360. Wider than an 18% glide can hold. This clip eases
    # only across the slack that keeps the church and the bell tower
    # inside every frame with a 12px pad.
    {
        "entry_id": "FR-01-199",
        "n": 199,
        "held": "Notre-Dame-des-Laves and its bell tower",
        "subject_x": 970.0,
        "subject_span": (580.0, 1360.0),
        "window_start": 508.0,
        "window_end": 568.0,
    },
    # Tsingoni. The square minaret and its finial measure about x 440–658,
    # the tip near x 549. A large palm stands to the left, about x 144–304.
    # The mosque roof continues past the minaret and is wider than an 864
    # frame can hold together with that palm. This clip is a short glide
    # centered on the finial, so the minaret, the finial, and the palm
    # stay inside every frame and a further wing does not enter.
    {
        "entry_id": "FR-01-201",
        "n": 201,
        "held": "Tsingoni minaret, finial, and palm",
        "subject_x": 549.0,
        "subject_span": (144.0, 658.0),
        "window_start": 102.0,
        "window_end": 132.0,
    },
    # Bastia old port. The church and its bell tower measure about
    # x 1100–1650, and the quay continues past both sides of that church.
    # The whole harbor is wider than 864. This clip holds the church,
    # bell tower included, and the quay from about x 900 to x 1700.
    {
        "entry_id": "FR-01-204",
        "n": 204,
        "held": "Bastia old-port church and quay",
        "subject_x": 1300.0,
        "subject_span": (900.0, 1700.0),
        "window_start": 848.0,
        "window_end": 888.0,
    },
    # Cap Gris-Nez. The stone house left of the tower measures about
    # x 220–420, and the lighthouse, lantern included, measures about
    # x 480–584. The old window ran from the plate edge to x 456 and
    # walked past the house. This clip is a short glide that keeps the
    # house and the lighthouse inside every frame.
    {
        "entry_id": "FR-01-205",
        "n": 205,
        "held": "Cap Gris-Nez lighthouse and stone house",
        "subject_x": 402.0,
        "subject_span": (220.0, 584.0),
        "window_start": 16.0,
        "window_end": 72.0,
    },
    # Le Croisic. The church and its bell tower measure about x 300–950,
    # and the harbor continues past that church. The whole port is wider
    # than 864. This clip holds the church, bell tower included, and the
    # quay from about x 200 to x 1010.
    {
        "entry_id": "FR-01-206",
        "n": 206,
        "held": "Le Croisic church and harbor",
        "subject_x": 605.0,
        "subject_span": (200.0, 1010.0),
        "window_start": 158.0,
        "window_end": 188.0,
    },
    # Pack 5. Measured on the daylight 16:9 photo (top 1080 rows).
    # Cap Méchant. The basalt shelf runs the full plate, about x 0–1919,
    # and there is no separate tower. Wider than 864. This clip holds
    # the central shelf and eases only across the slack inside that span.
    {
        "entry_id": "FR-01-215",
        "n": 215,
        "held": "Cap Méchant basalt shelf",
        "subject_x": 960.0,
        "subject_span": (564.0, 1356.0),
        "window_start": 506.0,
        "window_end": 550.0,
    },
    # La Pietra. The round Genoese tower measures about x 1090–1300,
    # crown centered near x 1205. A white lighthouse stands to its right,
    # about x 1520–1575. An 18% glide aimed at the Genoese tower traveled
    # onto that lighthouse. Both fit in 864. This clip is a short glide
    # centered on the Genoese tower, so the tower and the lighthouse stay
    # fully inside every frame and the lighthouse does not enter or leave.
    {
        "entry_id": "FR-01-221",
        "n": 221,
        "held": "La Pietra Genoese tower and white lighthouse",
        "subject_x": 1205.0,
        "subject_span": (1090.0, 1588.0),
        "window_start": 749.0,
        "window_end": 797.0,
    },
    # Bergues belfry. The brick shaft measures about x 691–1115, and the
    # spire already touches the top of the plate near x 875–920. Same
    # 18% glide, aimed at the shaft, so the spire is not cropped past
    # the plate's top edge.
    {
        "entry_id": "FR-01-222",
        "n": 222,
        "held": "Bergues belfry",
        "subject_x": 903.0,
        "subject_span": (691.0, 1115.0),
    },
    # Château Gaillard. The left curtain measures about x 430–780, and
    # the keep, crenellations included, measures about x 893–1165. An
    # 18% glide kept the curtain at the start and had lost it by the
    # end, while the river and the town entered on the right. Both the
    # curtain and the keep fit in 864. This clip is a short glide that
    # keeps that curtain and the keep inside every frame and does not
    # travel onto the valley.
    {
        "entry_id": "FR-01-223",
        "n": 223,
        "held": "Château Gaillard left curtain and keep",
        "subject_x": 1029.0,
        "subject_span": (430.0, 1175.0),
        "window_start": 330.0,
        "window_end": 376.0,
    },
    # Cilaos. The church bell tower, two tips included, measures about
    # x 1208–1265, and the trees beside the church stand about x 808–1061.
    # The cirque wall behind them runs wider than 864. This clip eases
    # only across the slack that keeps the church, both tips, and those
    # trees inside every frame.
    {
        "entry_id": "FR-01-231",
        "n": 231,
        "held": "Cilaos church, bell tower, and the trees beside it",
        "subject_x": 1120.0,
        "subject_span": (790.0, 1450.0),
        "window_start": 620.0,
        "window_end": 740.0,
    },
    # Chaumont. The left round tower, cone included, and the right tower
    # measure about x 348–1100, tips near x 534 and x 968. A lower wing
    # and a small chimney continue past x 1165. The whole château is
    # wider than 864. This clip is a short glide that keeps both towers
    # inside every frame and does not travel into that chimney.
    {
        "entry_id": "FR-01-235",
        "n": 235,
        "held": "Chaumont round tower and right tower",
        "subject_x": 724.0,
        "subject_span": (348.0, 1100.0),
        "window_start": 256.0,
        "window_end": 296.0,
    },
    # Douaumont ossuary. The lantern tower measures about x 892–998,
    # tip near x 945. The vault runs about x 40–1860, wider than 864.
    # This clip holds the tower and the vault around it, and eases only
    # across the slack inside that span.
    {
        "entry_id": "FR-01-236",
        "n": 236,
        "held": "Douaumont ossuary lantern tower",
        "subject_x": 945.0,
        "subject_span": (548.0, 1340.0),
        "window_start": 490.0,
        "window_end": 536.0,
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
    {
        "entry_id": "FR-01-167",
        "held": "Maïdo cirque rim",
        "reason": (
            "Two crests on the daylight plate stand at about the same "
            "height: one about x 160–480, highest near x 320, and one "
            "about x 1000–1160, highest near x 1067. The outer span is "
            "about 1000px, wider than 864, so holding both crests would "
            "mean dropping one. Left without a clip."
        ),
    },
    {
        "entry_id": "FR-01-169",
        "held": "Plage de N'Gouja trees",
        "reason": (
            "A tree cluster on the daylight plate stands about x 16–331, "
            "and a large tree stands about x 1461–1919. The outer span "
            "is about 1900px, wider than 864, so holding both trees "
            "would mean dropping one. Left without a clip."
        ),
    },
    {
        "entry_id": "FR-01-173",
        "held": "Beauvais Cathedral pinnacles",
        "reason": (
            "The choir pinnacles on the daylight plate run from about "
            "x 849 to about x 1832. That outer span is 984px, wider "
            "than 864, so holding every pinnacle would mean dropping "
            "one. Left without a clip."
        ),
    },
    {
        "entry_id": "FR-01-174",
        "held": "Château de Montsoreau roof",
        "reason": (
            "The slate roof on the daylight plate, dormers and tower "
            "caps included, runs about x 218–1207. That outer span is "
            "990px, wider than 864, so holding every roof tip would "
            "mean dropping one. Left without a clip."
        ),
    },
    {
        "entry_id": "FR-01-176",
        "held": "Pont d'Arc",
        "reason": (
            "The arch opening on the daylight plate is widest about "
            "x 795–1158, and the stone rims continue past that hole. "
            "The left abutment is still the arch near x 400, and the "
            "right abutment is still the arch past x 1500. The outer "
            "span is wider than 864, so holding both rims would mean "
            "dropping one. Left without a clip."
        ),
    },
    {
        "entry_id": "FR-01-183",
        "held": "Hell-Bourg roofs and cirque wall",
        "reason": (
            "Creole roofs on the daylight plate run from about x 774 "
            "to the right edge, and the cirque wall rises to about "
            "y 71 near x 1560. That span is wider than 864, so holding "
            "every roof and the wall would mean dropping one. Left "
            "without a clip."
        ),
    },
    {
        "entry_id": "FR-01-187",
        "held": "Semur-en-Auxois round towers",
        "reason": (
            "A round tower on the daylight plate stands about x 121–297, "
            "a spire peaks near x 1283, and further towers run about "
            "x 1475–1767. The outer span is about 1646px, wider than "
            "864, so holding every tower would mean dropping one. Left "
            "without a clip."
        ),
    },
    {
        "entry_id": "FR-01-189",
        "held": "Saint-Valery-sur-Somme quay",
        "reason": (
            "The quay roofs on the daylight plate run from the left edge "
            "to about x 1708. That outer span is about 1708px, wider "
            "than 864, so holding every roof would mean dropping one. "
            "Left without a clip."
        ),
    },
    {
        "entry_id": "FR-01-191",
        "held": "Château de Caen ramparts",
        "reason": (
            "The rampart on the daylight plate runs about x 0–1491. "
            "That outer span is about 1491px, wider than 864, so holding "
            "the curtain would mean dropping one end. Left without a clip."
        ),
    },
    {
        "entry_id": "FR-01-203",
        "held": "Baume-les-Messieurs abbey roofs",
        "reason": (
            "The abbey roofs in the valley on the daylight plate run "
            "about x 400–1500. That outer span is about 1100px, wider "
            "than 864, so holding every roof would mean dropping one. "
            "Left without a clip."
        ),
    },
    {
        "entry_id": "FR-01-207",
        "held": "Bourges Cathedral towers",
        "reason": (
            "The north-tower spire on the daylight plate stands about "
            "x 501–743, tip near x 620, and the south tower stands about "
            "x 1196–1426. The outer span is 925px, wider than 864, so "
            "holding both towers would mean dropping one. Left without "
            "a clip."
        ),
    },
    {
        "entry_id": "FR-01-208",
        "held": "Château de Sedan bastions",
        "reason": (
            "The higher curtain on the daylight plate runs about "
            "x 692–1588. That outer span is 896px, wider than 864, and "
            "the bastioned mass continues about x 216–1592. Holding "
            "every bastion would mean dropping one. Left without a clip."
        ),
    },
    {
        "entry_id": "FR-01-217",
        "held": "Rocher de Dzaoudzi and the tree to its left",
        "reason": (
            "A tree on the daylight plate stands about x 0–163, and the "
            "rock stands about x 642–1149. The outer span is about "
            "1149px, wider than 864, so holding the tree and the rock "
            "would mean dropping one. Left without a clip."
        ),
    },
    {
        "entry_id": "FR-01-219",
        "held": "Palais Idéal towers",
        "reason": (
            "The palace towers on the daylight plate, the tallest tip "
            "near x 1603, run about x 860–1851. That outer span is "
            "991px, wider than 864, so holding every tower would mean "
            "dropping one. Left without a clip."
        ),
    },
    {
        "entry_id": "FR-01-220",
        "held": "Auxerre Cathedral west towers",
        "reason": (
            "The north tower on the daylight plate stands about "
            "x 400–701, tip near x 642, and the south tower stands about "
            "x 1214–1472, tip near x 1399. The outer span is 1072px, "
            "wider than 864, so holding both towers would mean dropping "
            "one. Left without a clip."
        ),
    },
    {
        "entry_id": "FR-01-224",
        "held": "Château de Clisson round tower and square keep",
        "reason": (
            "The round tower on the daylight plate stands about "
            "x 343–1046, tip near x 772, and the square keep stands about "
            "x 1229–1502. The outer span is 1159px, wider than 864, so "
            "holding both towers would mean dropping one. Left without "
            "a clip."
        ),
    },
    {
        "entry_id": "FR-01-233",
        "held": "Sakouli palms and islet",
        "reason": (
            "A palm grove on the daylight plate stands about x 0–536, "
            "and the islet stands about x 960–1290. The outer span is "
            "1290px, wider than 864, so holding the palms and the islet "
            "would mean dropping one. Left without a clip."
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
