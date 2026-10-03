#!/usr/bin/env python3
"""Durable France gallery publisher.

Rewrites index.html from the current scene catalogue and this generator.
Phase-1 (search + region, day/night, mood, live count, clear all, four
related thumbnails, copy-link feedback, entry-id deep links, and the
missing-master guard) is emitted here. A later rebuild that starts from
this script keeps Phase-1. Hand-patches to index.html do not.

    python3 tools/build_index.py
    python3 tools/build_index.py --prove

Scene copy stays in index.html (the published catalogue). Verbose tourist
descriptions in tools/scene_descriptions.json replace those scenes'
description fields on every publish, so a rebuild rewrites them into
index.html. Scenes absent from that file keep their existing copy.
Day/night and mood tags stay in tools/phase1_scene_meta.json. Image
files are only read, never written.

A 9:16 path is copied into the catalogue only when that master file is on
disk. The published page does not probe for it, and it does not remove a
tab after the card has rendered.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
META_PATH = Path(__file__).resolve().parent / "phase1_scene_meta.json"
DESCRIPTIONS_PATH = Path(__file__).resolve().parent / "scene_descriptions.json"

FILE_KEYS = (
    "file_16x9",
    "file_4x5",
    "file_9x16",
    "file_16x9_day",
    "file_4x5_day",
    "file_9x16_day",
    "file_16x9_postcard",
    "file_4x5_postcard",
    "file_9x16_postcard",
    "audio",
)
# Portrait controls are a disk gate, same as Greece and Switzerland.
# A remote URL is not a master and is not emitted.
PORTRAIT_KEYS = ("file_9x16", "file_9x16_day", "file_9x16_postcard")

MOODS = ("coastal", "mountain", "urban", "historic")
MOOD_WORDS = {
    "coastal": (
        "coast", "harbor", "harbour", "beach", "bay", "sea", "port", "cliff",
        "island", "plage", "anse", "lagon", "cape", "phare", "calanque",
    ),
    "mountain": (
        "mountain", "mont", "peak", "gorge", "glacier", "alp", "volcano",
        "piton", "cascade", "aiguille", "cirque", "puy",
    ),
    "urban": (
        "old town", "square", "place ", "street", "quartier", "skyline",
        "promenade", "waterfront",
    ),
    "historic": (
        "cathedral", "château", "chateau", "abbey", "abbaye", "castle",
        "citadel", "citadelle", "fort", "church", "basilica", "basilique",
        "palace", "palais", "roman", "medieval", "rampart", "monaster",
    ),
}

P1_CSS = """
/* P1-CSS-START */
/* Phase 1 France: day/night + mood filters, related scenes, copy link.
   Emitted by tools/build_index.py. Spain pilot behavior, France palette. */
.related{border-top:1px solid var(--line);margin-top:20px;padding-top:14px}
.related-h{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin:0 0 10px}
.related-row{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.related-link{display:block;text-decoration:none}
.related-link img{width:100%;aspect-ratio:16/9;object-fit:cover;display:block;border:1px solid var(--line);border-radius:6px}
.related-link span{display:block;font-size:12px;color:var(--muted);padding:6px 0}
.related-link:hover span{color:var(--text)}
.copy-link{display:inline-block;background:#243049;color:var(--text);border:1px solid var(--line);border-radius:8px;padding:0.4rem 0.7rem;font-size:0.85rem;cursor:pointer;font:inherit}
.copy-link:hover{border-color:var(--accent)}
@media(max-width:760px){.related-row{grid-template-columns:repeat(2,1fr)}}
/* P1-CSS-END */
"""

P1_FILTERS = """<!-- P1-FILTERS-START -->
      <select id="f-daynight" aria-label="Filter by time of day">
        <option value="">Day or night</option><option value="day">Day</option><option value="night">Night</option>
      </select>
      <select id="f-mood" aria-label="Filter by scene mood">
        <option value="">All moods</option><option value="coastal">Coastal</option><option value="mountain">Mountain</option><option value="urban">Urban</option><option value="historic">Historic</option>
      </select>
<!-- P1-FILTERS-END -->
"""

P1_FILTER_JS = """      /* P1-FILTER-START */
      var p1dnEl = document.getElementById('f-daynight');
      var p1moodEl = document.getElementById('f-mood');
      var p1dnv = p1dnEl ? p1dnEl.value : '';
      var p1moodv = p1moodEl ? p1moodEl.value : '';
      var p1meta = (typeof FRANCE_META !== 'undefined') ? FRANCE_META : null;
      /* P1-FILTER-END */
"""

P1_MATCH_JS = """        /* P1-MATCH-START */
        if (p1meta) {
          var mm = p1meta[s.entry_id];
          if (mm) {
            if (p1dnv && mm[1] !== p1dnv) return false;
            if (p1moodv && (mm[2] + ',').indexOf(p1moodv + ',') < 0) return false;
          }
        }
        /* P1-MATCH-END */
"""

P1_LISTENERS = """    /* P1-LISTENERS-START */
    (function(){ var a = document.getElementById('f-daynight'); if (a) a.addEventListener('change', render); var b = document.getElementById('f-mood'); if (b) b.addEventListener('change', render); })();
    clearBtn.addEventListener('click', () => { q.value = ''; region.value = ''; var d1 = document.getElementById('f-daynight'); if (d1) d1.value = ''; var m1 = document.getElementById('f-mood'); if (m1) m1.value = ''; render(); });
    /* P1-LISTENERS-END */
"""

P1_ENHANCE_CALL = """      /* P1-ENHANCE-CALL-START */
      if (typeof window.__phase1Enhance === 'function') { window.__phase1Enhance(); }
      /* P1-ENHANCE-CALL-END */
"""

# Card builder. Controls and the thumb are omitted when that master is absent.
P1_CARD = r"""        card.className = 'card';
        card.id = s.entry_id;
        const file16 = s.file_16x9 || "";
        const file45 = s.file_4x5 || "";
        /* file_9x16 is present only when the generator found that file on disk. */
        const file916 = s.file_9x16 || "";
        const day16 = s.file_16x9_day || "";
        const day45 = s.file_4x5_day || "";
        const day916 = s.file_9x16_day || "";
        const pc16 = s.file_16x9_postcard || "";
        const pc45 = s.file_4x5_postcard || "";
        const pc916 = s.file_9x16_postcard || "";
        const hasPc = !!(pc16 || pc45 || pc916);
        const audioSrc = (typeof s.audio === "string" && /^audio\/[^/?#]+\.mp3(?:\?.*)?$/.test(s.audio)) ? s.audio : "";
        const sceneHero = file16 || file45 || file916;
        const hero = hasPc ? (pc16 || pc45 || pc916) : sceneHero;
        const show16 = !!(file16 || pc16);
        const show45 = !!(file45 || pc45);
        const show916 = !!(file916 || pc916);
        const dl16 = (hasPc && pc16) ? pc16 : file16;
        const dl45 = (hasPc && pc45) ? pc45 : file45;
        const dl916 = (hasPc && pc916) ? pc916 : file916;
        card.innerHTML = `
          ${hero ? `<div class="preview">
            <a class="thumb" href="${esc(hero)}" target="_blank" rel="noopener">
              <img src="${esc(hero)}" alt="${esc(sceneAlt(s))}" loading="lazy"${file16 ? ` data-src-16="${esc(file16)}"` : ""}${file45 ? ` data-src-45="${esc(file45)}"` : ""}${day16 ? ` data-src-16-day="${esc(day16)}"` : ""}${day45 ? ` data-src-45-day="${esc(day45)}"` : ""}${file916 ? ` data-src-916="${esc(file916)}"` : ""}${day916 ? ` data-src-916-day="${esc(day916)}"` : ""}${pc16 ? ` data-src-16-pc="${esc(pc16)}"` : ""}${pc45 ? ` data-src-45-pc="${esc(pc45)}"` : ""}${pc916 ? ` data-src-916-pc="${esc(pc916)}"` : ""} />
            </a>
          </div>` : ""}
          ${(show16 || show45 || show916) ? `<div class="fmt-tabs" role="group" aria-label="Image size">
              ${show16 ? `<button type="button" class="fmt-tab is-active" data-format="16x9" aria-pressed="true">16:9</button>` : ""}
              ${show45 ? `<button type="button" class="fmt-tab${show16 ? "" : " is-active"}" data-format="4x5" aria-pressed="${show16 ? "false" : "true"}">4:5</button>` : ""}
              ${show916 ? `<button type="button" class="fmt-tab${(!show16 && !show45) ? " is-active" : ""}" data-format="9x16" aria-pressed="${(!show16 && !show45) ? "true" : "false"}">9:16</button>` : ""}
            </div>` : ""}
          ${(day16 || day45 || hasPc) ? `<div class="day-row">${(day16 || day45) ? `<button type="button" class="day-tab" data-daynight="night" aria-pressed="false" title="Toggle the daylight variant">\u2600 Daylight</button>` : ""}${hasPc ? `<button type="button" class="day-tab pc-tab is-active" data-postcard="on" aria-pressed="true" title="Postcard collection">\u{1F4E9} Postcard</button>` : ""}</div>` : ""}
          <div class="card-body">
            <div class="status-row">
              <div class="entry-id">${esc(s.entry_id)}</div>
              <span class="status ${esc((s.approval_status || 'Candidate').toLowerCase())}">${esc(s.approval_status || 'Candidate')}</span>
            </div>
            <h3 class="caption">${esc(s.caption)}</h3>
            <p class="scenario" data-scenario="${esc(s.scenario_label)}">${hasPc ? "Postcard collection" : `Scenario: ${esc(s.scenario_label)}`}</p>
            <p class="composition">${esc(s.composition)}</p>
            ${s.description ? `<p class="detail">${esc(s.description)}</p>` : ""}
            <div class="actions">
              <a class="badge" href="#license">Free · no credit needed</a>
              ${dl16 ? `<a class="download" data-dl="16x9" href="${esc(dl16)}" download="${esc(fileName(dl16))}">Download 16:9</a>` : ""}
              ${dl45 ? `<a class="download" data-dl="4x5" href="${esc(dl45)}" download="${esc(fileName(dl45))}">Download 4:5</a>` : ""}
              ${dl916 ? `<a class="download" data-dl="9x16" href="${esc(dl916)}" download="${esc(fileName(dl916))}">Download 9:16</a>` : ""}
              ${audioSrc ? `<button type="button" class="narrate" data-audio="${esc(audioSrc)}" aria-pressed="false" aria-label="Listen to the scene description">🔊 Listen</button>` : ""}
            </div>
          </div>`;
        grid.appendChild(card);
"""

P1_SCENE_ALT = r"""    /* P1-ALT-START */
    /* Empty or generic alts become "{card description} — {site}, {City}". */
    function sceneAlt(s) {
      var current = String((s && s.alt_text) || "").trim();
      var title = String((s && s.caption) || "").trim();
      var desc = String((s && s.description) || "").trim();
      var generic = !current
        || /^(image|photo|picture|img|scene|thumbnail|placeholder)$/i.test(current)
        || current === title
        || current === String((s && s.entry_id) || "")
        || /^AI-generated artistic interpretation\b/i.test(current);
      var built = desc && title ? desc + " \u2014 " + title : (desc || title);
      return generic ? (built || current) : current;
    }
    /* P1-ALT-END */
"""

P1_ENHANCE = r"""<script>
/* P1-ENHANCE-START */
/* Phase 1 France: four related thumbnails (same region, then shared mood
   tags, entry id) and a per-card copy link. Re-run after every render().
   A missing 16:9 master is an empty thumb string and is not rendered. */
(function(){
  function relatedFor(id){
    if (typeof FRANCE_META === 'undefined') return [];
    var me = FRANCE_META[id];
    if (!me) return [];
    var mm = (me[2] || '').split(',').filter(Boolean);
    var out = [];
    for (var oid in FRANCE_META){
      if (oid === id) continue;
      var o = FRANCE_META[oid];
      if (!o[3]) continue;
      var om = ',' + (o[2] || '') + ',', shared = 0;
      for (var i = 0; i < mm.length; i++){ if (om.indexOf(',' + mm[i] + ',') >= 0) shared++; }
      if (o[0] === me[0] || shared > 0) out.push([(o[0] === me[0] ? 0 : 1), -shared, oid]);
    }
    out.sort(function(a,b){ return a[0]-b[0] || a[1]-b[1] || (a[2]<b[2] ? -1 : 1); });
    return out.slice(0,4).map(function(x){ return x[2]; });
  }
  function enhance(){
    if (typeof FRANCE_META === 'undefined') return;
    document.querySelectorAll('.card').forEach(function(card){
      var id = card.id;
      if (!id || !FRANCE_META[id]) return;
      var acts = card.querySelector('.actions');
      if (acts && !acts.querySelector('.copy-link')){
        var b = document.createElement('button');
        b.type = 'button'; b.className = 'copy-link'; b.textContent = 'Copy link';
        b.setAttribute('aria-label', 'Copy link to this scene');
        b.addEventListener('click', function(){
          var url = location.origin + location.pathname + '#' + id;
          var done = function(){ b.textContent = 'Copied \u2713'; setTimeout(function(){ b.textContent = 'Copy link'; }, 1600); };
          function fb(){
            var ta = document.createElement('textarea'); ta.value = url;
            ta.style.position = 'fixed'; ta.style.opacity = '0';
            document.body.appendChild(ta); ta.select();
            try { document.execCommand('copy'); done(); } catch(e) {}
            ta.remove();
          }
          if (navigator.clipboard && navigator.clipboard.writeText){
            navigator.clipboard.writeText(url).then(done, fb);
          } else { fb(); }
        });
        acts.appendChild(b);
      }
      if (!card.querySelector('.related')){
        var rel = relatedFor(id);
        if (rel.length){
          var box = document.createElement('div'); box.className = 'related';
          var h = document.createElement('p'); h.className = 'related-h'; h.textContent = 'Related scenes';
          box.appendChild(h);
          var grid = document.createElement('div'); grid.className = 'related-row';
          rel.forEach(function(rid){
            var m = FRANCE_META[rid];
            if (!m || !m[3]) return;
            var a = document.createElement('a'); a.className = 'related-link'; a.href = '#' + rid;
            var im = document.createElement('img'); im.loading = 'lazy'; im.src = m[3];
            var relScene = (typeof SCENES !== 'undefined') ? SCENES.filter(function(s){ return s.entry_id === rid; })[0] : null;
            im.alt = relScene ? sceneAlt(relScene) : m[4];
            var sp = document.createElement('span'); sp.textContent = m[4];
            a.appendChild(im); a.appendChild(sp); grid.appendChild(a);
          });
          if (!grid.childNodes.length) return;
          box.appendChild(grid);
          var det = card.querySelector('p.detail');
          if (det && card.contains(det)){ det.parentNode.insertBefore(box, det.nextSibling); }
          else { card.appendChild(box); }
        }
      }
    });
    document.querySelectorAll('.related-link').forEach(function(a){
      if (a.getAttribute('data-p1bound')) return;
      a.setAttribute('data-p1bound', '1');
      a.addEventListener('click', function(){
        var q = document.getElementById('q'); if (q) q.value = '';
        var r = document.getElementById('region'); if (r) r.value = '';
        var d = document.getElementById('f-daynight'); if (d) d.value = '';
        var m = document.getElementById('f-mood'); if (m) m.value = '';
        var c = document.getElementById('clear'); if (c) c.click();
      });
    });
    function jumpToHash(){
      if (!location.hash) return;
      var el = document.getElementById(decodeURIComponent(location.hash.slice(1)));
      if (el && el.classList && el.classList.contains('card')) el.scrollIntoView({block:'center'});
    }
    if (!window.__p1Deep && location.hash) {
      window.__p1Deep = true;
      jumpToHash();
    }
    if (!window.__p1HashLoad) {
      window.__p1HashLoad = true;
      window.addEventListener('load', jumpToHash);
    }
  }
  window.__phase1Enhance = enhance;
  enhance();
})();
/* P1-ENHANCE-END */
</script>
"""


def master_present(url: str, root: Path) -> bool:
    if not url:
        return False
    path = str(url).split("?", 1)[0]
    if path.startswith("http://") or path.startswith("https://"):
        return True
    return (root / path).is_file()


def master_on_disk(url: str, root: Path) -> bool:
    """True when url is a non-empty file inside the repo.

    Remote and absolute paths are missing masters. This is the Greece and
    Switzerland rule for optional portrait files: the catalogue line is
    written only when the file is already on disk.
    """
    if not url or not isinstance(url, str):
        return False
    path = url.split("?", 1)[0].strip()
    if not path or path.startswith(("/", "\\")) or "://" in path:
        return False
    file_path = (root / path).resolve()
    try:
        file_path.relative_to(root.resolve())
    except ValueError:
        return False
    return file_path.is_file() and file_path.stat().st_size > 0


def prune_scene(scene: dict, root: Path) -> dict:
    """Drop file/audio fields that must not be published.

    9:16 fields stay only when that master exists on disk. Other file fields
    keep the previous local-or-remote check.
    """
    kept = dict(scene)
    for key in FILE_KEYS:
        value = kept.get(key)
        if not value:
            continue
        present = (
            master_on_disk(str(value), root)
            if key in PORTRAIT_KEYS
            else master_present(str(value), root)
        )
        if not present:
            kept.pop(key, None)
    return kept


def _js_span(html: str, marker: str, open_ch: str, close_ch: str) -> tuple[int, int]:
    start = html.index(marker)
    i = html.index(open_ch, start)
    depth = 0
    in_str = False
    esc = False
    for j in range(i, len(html)):
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
        elif c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return i, j + 1
    raise ValueError(f"unclosed {open_ch} after {marker}")


def parse_scenes(html: str) -> list[dict]:
    i, j = _js_span(html, "const SCENES = ", "[", "]")
    raw = html[i:j]
    fixed = re.sub(r'(?m)^(\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:', r'\1"\2":', raw)
    fixed = re.sub(r",(\s*\n\s*[}\]])", r"\1", fixed)
    return json.loads(fixed)


def drop_missing_scene_lines(html: str, scenes: list[dict], root: Path) -> tuple[str, list[dict], list[tuple[str, str]]]:
    """Remove JS source lines for masters that are not on disk."""
    drops: list[tuple[str, str]] = []
    pruned: list[dict] = []
    for scene in scenes:
        kept = prune_scene(scene, root)
        pruned.append(kept)
        for key in FILE_KEYS:
            if scene.get(key) and key not in kept:
                drops.append((scene["entry_id"], key))
    if not drops:
        return html, pruned, drops
    i, j = _js_span(html, "const SCENES = ", "[", "]")
    block = html[i:j]
    for entry_id, key in drops:
        pattern = re.compile(
            rf'(entry_id:\s*"{re.escape(entry_id)}"[\s\S]*?)\n[ \t]*{re.escape(key)}:\s*"(?:\\.|[^"\\])*",?'
        )
        updated, n = pattern.subn(r"\1", block, count=1)
        if n != 1:
            raise SystemExit(f"could not drop missing {key} from {entry_id}")
        block = updated
    return html[:i] + block + html[j:], pruned, drops


def load_tags() -> dict[str, list[str]]:
    if not META_PATH.is_file():
        raise SystemExit(f"missing {META_PATH}")
    data = json.loads(META_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("phase1_scene_meta.json must be an object")
    return data


def infer_daynight(scene: dict) -> str:
    label = scene.get("scenario_label") or ""
    match = re.search(r"(\d{1,2}):(\d{2})", label)
    if match:
        hour = int(match.group(1))
        return "day" if 6 <= hour <= 17 else "night"
    text = f"{scene.get('description') or ''} {scene.get('composition') or ''}"
    if re.search(r"\bnight\b", text, re.I):
        return "night"
    return "day"


def infer_moods(scene: dict) -> str:
    text = " ".join(
        str(scene.get(key) or "")
        for key in ("caption", "composition", "description", "city", "region")
    ).lower()
    found = [name for name in MOODS if any(word in text for word in MOOD_WORDS[name])]
    return ",".join(found)


def thumb_for(scene: dict, root: Path) -> str:
    """Page-relative 16:9 thumb, or a remote master. Empty when neither exists."""
    local = f"assets/{scene['entry_id'].lower()}-16x9.png"
    if (root / local).is_file():
        return local
    url = str(scene.get("file_16x9") or "").split("?", 1)[0]
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url and (root / url).is_file():
        return url
    return ""


def build_meta(scenes: list[dict], root: Path, tags: dict[str, list[str]]) -> dict[str, list[str]]:
    meta: dict[str, list[str]] = {}
    new_tags = False
    for scene in scenes:
        entry_id = scene["entry_id"]
        stored = tags.get(entry_id)
        if stored and len(stored) >= 2:
            daynight, moods = stored[0], stored[1]
        else:
            daynight, moods = infer_daynight(scene), infer_moods(scene)
            tags[entry_id] = [daynight, moods]
            new_tags = True
        if daynight not in ("day", "night"):
            raise SystemExit(f"{entry_id} day/night tag must be day or night")
        for mood in filter(None, str(moods).split(",")):
            if mood not in MOODS:
                raise SystemExit(f"{entry_id} has unknown mood {mood}")
        meta[entry_id] = [
            scene.get("region") or "",
            daynight,
            moods or "",
            thumb_for(scene, root),
            scene.get("caption") or entry_id,
        ]
    if new_tags:
        META_PATH.write_text(json.dumps(tags, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return meta


def related_ids(meta: dict[str, list], entry_id: str, limit: int = 4) -> list[str]:
    """Same ordering the page uses: region, shared mood count, then entry id."""
    me = meta[entry_id]
    mine = [m for m in str(me[2] or "").split(",") if m]
    ranked = []
    for other_id, other in meta.items():
        if other_id == entry_id or not other[3]:
            continue
        tags = "," + str(other[2] or "") + ","
        shared = sum(1 for mood in mine if f",{mood}," in tags)
        if other[0] == me[0] or shared:
            ranked.append((0 if other[0] == me[0] else 1, -shared, other_id))
    ranked.sort()
    return [item[2] for item in ranked[:limit]]


def _strip_marked(html: str, start: str, end: str) -> str:
    """Drop one generated block, including the indent on its first line.

    The replacement is a single newline, so the statement above the block
    keeps its own terminator and a second publish lands on the same bytes.
    """
    pattern = re.compile(
        r"\n*[ \t]*" + re.escape(start) + r"[\s\S]*?" + re.escape(end) + r"\n*"
    )
    return pattern.sub("\n", html)


def _strip_script_containing(html: str, needle: str) -> str:
    """Remove the one <script> element whose body contains needle."""
    start = 0
    open_tag = "<script>"
    close_tag = "</script>"
    while True:
        i = html.find(open_tag, start)
        if i < 0:
            return html
        line = html.rfind("\n", 0, i) + 1
        j = html.find(close_tag, i)
        if j < 0:
            return html
        j_end = j + len(close_tag)
        if html[j_end:j_end + 1] == "\n":
            j_end += 1
        if needle in html[i:j]:
            return html[:line] + html[j_end:]
        start = j_end


def strip_phase1(html: str) -> str:
    """Remove a previous Phase-1 emission so the generator can write it again."""
    html = _strip_script_containing(html, "const FRANCE_META=")
    html = _strip_script_containing(html, "window.__phase1Enhance = enhance")
    html = _strip_marked(html, "/* P1-CSS-START */", "/* P1-CSS-END */")
    html = _strip_marked(html, "<!-- P1-FILTERS-START -->", "<!-- P1-FILTERS-END -->")
    html = _strip_marked(html, "/* P1-FILTER-START */", "/* P1-FILTER-END */")
    html = _strip_marked(html, "/* P1-MATCH-START */", "/* P1-MATCH-END */")
    html = _strip_marked(html, "/* P1-LISTENERS-START */", "/* P1-LISTENERS-END */")
    html = _strip_marked(html, "/* P1-ENHANCE-CALL-START */", "/* P1-ENHANCE-CALL-END */")
    html = re.sub(
        r"\n*/\* Phase 1 France \(2026-09-26\): advanced filters[\s\S]*?@media\(max-width:760px\)\{\.related-row\{grid-template-columns:repeat\(2,1fr\)\}\}\n*",
        "\n",
        html,
        count=1,
    )
    html = re.sub(
        r"\s*<select id=\"f-daynight\"[\s\S]*?</select>\s*<select id=\"f-mood\"[\s\S]*?</select>\n",
        "\n",
        html,
        count=1,
    )
    html = html.replace("        card.id = s.entry_id; /* Phase 1 France */\n", "")
    html = re.sub(
        r"\n[ \t]*/\* Phase 1 France: day/night \+ mood filters \(FRANCE_META\)\. \*/\n[ \t]*var p1dnEl = document\.getElementById\('f-daynight'\);\n[ \t]*var p1moodEl = document\.getElementById\('f-mood'\);\n[ \t]*var p1dnv = p1dnEl \? p1dnEl\.value : '';\n[ \t]*var p1moodv = p1moodEl \? p1moodEl\.value : '';\n[ \t]*var p1meta = \(typeof FRANCE_META !== 'undefined'\) \? FRANCE_META : null;\n",
        "\n",
        html,
        count=1,
    )
    html = re.sub(
        r"\n[ \t]*if \(p1meta\) \{\n[ \t]*var mm = p1meta\[s\.entry_id\];\n[ \t]*if \(mm\) \{\n[ \t]*if \(p1dnv && mm\[1\] !== p1dnv\) return false;\n[ \t]*if \(p1moodv && \(mm\[2\] \+ ','\)\.indexOf\(p1moodv \+ ','\) < 0\) return false;\n[ \t]*\}\n[ \t]*\}\n",
        "\n",
        html,
        count=1,
    )
    html = html.replace(
        "      /* Phase 1 France: re-inject related rows + copy links after cards rebuild. */\n"
        "      if (typeof window.__phase1Enhance === 'function') { window.__phase1Enhance(); }\n",
        "",
    )
    html = html.replace(
        "    /* Phase 1 France: day/night + mood selects re-render. */\n"
        "    (function(){ var a = document.getElementById('f-daynight'); if (a) a.addEventListener('change', render); var b = document.getElementById('f-mood'); if (b) b.addEventListener('change', render); })();\n",
        "",
    )
    html = re.sub(
        r"[ \t]*clearBtn\.addEventListener\('click', \(\) => \{.*?\}\);[^\n]*\n",
        "",
        html,
        count=1,
    )
    html = re.sub(r"[ \t]*<script>\s*</script>\n", "", html)
    return html


def _insert_card(html: str) -> str:
    pattern = re.compile(
        r"        card\.className = 'card';\n.*?        grid\.appendChild\(card\);\n",
        re.S,
    )
    updated, n = pattern.subn(lambda _match: P1_CARD, html, count=1)
    if n != 1:
        raise SystemExit("gallery card builder anchor missing; refusing to publish")
    return updated


def _insert_once(html: str, needle: str, anchor: str, block: str, after: bool = True) -> str:
    if needle in html:
        return html
    if anchor not in html:
        raise SystemExit(f"anchor missing: {anchor[:80]!r}")
    if after:
        return html.replace(anchor, anchor + block, 1)
    return html.replace(anchor, block + anchor, 1)


def _insert_css(html: str) -> str:
    if "/* P1-CSS-START */" in html:
        return html
    body = P1_CSS.strip("\n")
    updated, n = re.subn(r"\n*</style>", "\n" + body + "\n</style>", html, count=1)
    if n != 1:
        raise SystemExit("style close anchor missing; refusing to publish")
    return updated


def _insert_meta(html: str, meta_script: str) -> str:
    """Place FRANCE_META in its own script, immediately before the SCENES script."""
    if "const FRANCE_META=" in html:
        raise SystemExit("FRANCE_META survived strip; refusing to publish")
    idx = html.find("const SCENES = ")
    if idx < 0:
        raise SystemExit("SCENES anchor missing; refusing to publish")
    script_open = html.rfind("<script>", 0, idx)
    if script_open < 0:
        raise SystemExit("SCENES script tag missing; refusing to publish")
    line = html.rfind("\n", 0, script_open) + 1
    return html[:line] + meta_script + html[line:]


def _insert_enhance_call(html: str) -> str:
    if "/* P1-ENHANCE-CALL-START */" in html:
        return html
    anchor = "        grid.appendChild(card);\n      }\n    }\n    grid.addEventListener('click', (event) => {\n"
    replacement = (
        "        grid.appendChild(card);\n      }\n"
        + P1_ENHANCE_CALL
        + "    }\n    grid.addEventListener('click', (event) => {\n"
    )
    if anchor not in html:
        raise SystemExit("render() close anchor missing; refusing to publish")
    return html.replace(anchor, replacement, 1)


def _insert_scene_alt(html: str) -> str:
    """Emit sceneAlt once. A later publish leaves the block in place."""
    if "/* P1-ALT-START */" in html:
        return html
    anchor = "    function render() {\n"
    if anchor not in html:
        raise SystemExit("render() anchor missing; refusing to publish")
    return html.replace(anchor, P1_SCENE_ALT + anchor, 1)


def insert_phase1(html: str, meta: dict[str, list[str]]) -> str:
    html = _insert_scene_alt(html)
    html = _insert_css(html)
    html = re.sub(
        r"<button type=\"button\" id=\"clear\">.*?</button>",
        '<button type="button" id="clear">Clear all</button>',
        html,
        count=1,
    )
    html = _insert_once(
        html,
        'id="f-daynight"',
        '      <button type="button" id="clear">Clear all</button>',
        P1_FILTERS,
        after=False,
    )
    payload = json.dumps(meta, ensure_ascii=False, separators=(",", ":"))
    meta_script = (
        "<script>\n"
        "/* P1-META-START */\n"
        "/* Phase 1 France: [region, day|night, mood-tags, 16:9 thumb, name]. "
        "Empty thumb means the master is missing and must not be rendered. */\n"
        f"const FRANCE_META={payload};\n"
        "/* P1-META-END */\n"
        "</script>\n"
    )
    html = _insert_meta(html, meta_script)
    html = _insert_card(html)
    html = _insert_once(
        html,
        "/* P1-FILTER-START */",
        "      const reg = region.value;\n",
        P1_FILTER_JS,
    )
    html = _insert_once(
        html,
        "/* P1-MATCH-START */",
        "        if (reg && s.region !== reg) return false;\n",
        P1_MATCH_JS,
    )
    html = _insert_enhance_call(html)
    html = re.sub(
        r"[ \t]*clearBtn\.addEventListener\('click', \(\) => \{.*?\}\);[^\n]*\n",
        "",
        html,
        count=1,
    )
    html = _insert_once(
        html,
        "/* P1-LISTENERS-START */",
        "    region.addEventListener('change', render);\n",
        P1_LISTENERS,
    )
    if "/* P1-ENHANCE-START */" not in html:
        html = html.replace("</body>", P1_ENHANCE + "</body>", 1)
    return html


_OLD_NORWAY = (
    ".flag-no{background:linear-gradient(#00205B,#00205B) center/100% 20% no-repeat,"
    "linear-gradient(#00205B,#00205B) center/22% 100% no-repeat,"
    "linear-gradient(#fff,#fff) center/100% 38% no-repeat,"
    "linear-gradient(#fff,#fff) center/40% 100% no-repeat,#BA0C2F}"
)
# Spain gallery chip: Nordic cross, not a centered blob. Same rule as spain.jdvision.org.
_SPAIN_NORWAY = (
    ".flag-chip.flag-no{background:linear-gradient(to bottom,transparent 35%,#00205B 35%,#00205B 65%,transparent 65%),"
    "linear-gradient(to bottom,transparent 25%,#fff 25%,#fff 75%,transparent 75%),"
    "linear-gradient(to right,transparent 25%,#00205B 25%,#00205B 45%,transparent 45%),"
    "linear-gradient(to right,transparent 15%,#fff 15%,#fff 55%,transparent 55%),#BA0C2F}"
)

_OLD_FMT_HANDLER = """      const tab = event.target.closest('.fmt-tab');
      if (!tab) return;
      event.preventDefault();
      const card = tab.closest('.card');
      if (!card) return;
      const fmt = tab.dataset.format;
      card.querySelectorAll('.fmt-tab').forEach((item) => {
        const on = item === tab;
        item.classList.toggle('is-active', on);
        item.setAttribute('aria-pressed', on ? 'true' : 'false');
      });
      const link = card.querySelector('a.thumb');
      const img = link && link.querySelector('img');
      if (!img || !link) return;
      const dayOn = card.querySelector('.day-tab.is-active');
      const useDay = dayOn && dayOn.getAttribute('data-daynight') === 'day';
      const next = fmt === '4x5'
        ? (useDay && img.getAttribute('data-src-45-day')) || img.getAttribute('data-src-45')
        : fmt === '9x16'
        ? (useDay && img.getAttribute('data-src-916-day')) || img.getAttribute('data-src-916')
        : (useDay && img.getAttribute('data-src-16-day')) || img.getAttribute('data-src-16');
      if (next) {
        img.src = next;
        link.href = next;
      }
      link.classList.toggle('tall', fmt === '4x5');
      link.classList.toggle('tall916', fmt === '9x16');
"""

_NEW_FMT_HANDLER = """      const tab = event.target.closest('.fmt-tab');
      if (!tab || tab.disabled) return;
      event.preventDefault();
      const card = tab.closest('.card');
      if (!card) return;
      const fmt = tab.getAttribute('data-format');
      card.querySelectorAll('.fmt-tab').forEach((item) => {
        const on = item === tab;
        item.classList.toggle('is-active', on);
        item.setAttribute('aria-pressed', on ? 'true' : 'false');
      });
      const link = card.querySelector('a.thumb');
      const img = link && link.querySelector('img');
      if (!img || !link) return;
      const dayOn = card.querySelector('.day-tab.is-active');
      const useDay = dayOn && dayOn.getAttribute('data-daynight') === 'day';
      const next = fmt === '4x5'
        ? (useDay && img.getAttribute('data-src-45-day')) || img.getAttribute('data-src-45')
        : fmt === '9x16'
        ? (useDay && img.getAttribute('data-src-916-day')) || img.getAttribute('data-src-916')
        : (useDay && img.getAttribute('data-src-16-day')) || img.getAttribute('data-src-16');
      if (next) {
        img.src = next;
        link.href = next;
      }
      link.classList.toggle('tall', fmt === '4x5');
      link.classList.toggle('tall916', fmt === '9x16');
"""

_OLD_DAY_MARK = """        dtab.setAttribute('data-daynight', isDay ? 'day' : 'night');
        const ftab = dcard.querySelector('.fmt-tab.is-active');
        const dfmt = ftab ? ftab.getAttribute('data-format') : '16x9';
        const dlink = dcard.querySelector('a.thumb');
        const dimg = dlink && dlink.querySelector('img');
        if (dimg && dlink) {
"""

_NEW_DAY_MARK = """        dtab.setAttribute('data-daynight', isDay ? 'day' : 'night');
        const dlink = dcard.querySelector('a.thumb');
        const dimg = dlink && dlink.querySelector('img');
        const t916 = dcard.querySelector('.fmt-tab[data-format="9x16"]');
        if (t916) {
          const day916src = dimg && dimg.getAttribute('data-src-916-day');
          const hide916 = isDay && !day916src;
          t916.disabled = hide916;
          t916.classList.toggle('is-disabled', hide916);
          if (hide916 && t916.classList.contains('is-active')) {
            const t16 = dcard.querySelector('.fmt-tab[data-format="16x9"]') || dcard.querySelector('.fmt-tab[data-format="4x5"]');
            if (t16) t16.click();
          }
        }
        const ftab = dcard.querySelector('.fmt-tab.is-active');
        const dfmt = ftab ? ftab.getAttribute('data-format') : '16x9';
        if (dimg && dlink) {
"""

_OLD_COPY = """          b.textContent = 'Copied \\u2713';
          setTimeout(function(){ b.textContent = 'Copy link'; }, 1600);
          function fb(){
            var ta = document.createElement('textarea'); ta.value = url;
            ta.style.position = 'fixed'; ta.style.opacity = '0';
            document.body.appendChild(ta); ta.select();
            try { document.execCommand('copy'); } catch(e) {}
            ta.remove();
          }
          if (navigator.clipboard && navigator.clipboard.writeText){
            navigator.clipboard.writeText(url).then(function(){}, fb);
          } else { fb(); }
"""

_NEW_COPY = """          var done = function(){ b.textContent = 'Copied \\u2713'; setTimeout(function(){ b.textContent = 'Copy link'; }, 1600); };
          function fb(){
            var ta = document.createElement('textarea'); ta.value = url;
            ta.style.position = 'fixed'; ta.style.opacity = '0';
            document.body.appendChild(ta); ta.select();
            try { document.execCommand('copy'); done(); } catch(e) {}
            ta.remove();
          }
          if (navigator.clipboard && navigator.clipboard.writeText){
            navigator.clipboard.writeText(url).then(done, fb);
          } else { fb(); }
"""


def apply_a7(html: str) -> str:
    """Spain-look guards that survive a later publish. Does not touch SCENES."""
    if _OLD_NORWAY in html:
        html = html.replace(_OLD_NORWAY, _SPAIN_NORWAY, 1)
    if ".fmt-tab:disabled" not in html:
        anchor = """    .fmt-tab.is-active {
      background: var(--accent); border-color: var(--accent); color: var(--bg); font-weight: 700;
    }
"""
        insert = anchor + "    .fmt-tab:disabled, .fmt-tab.is-disabled { opacity: 0.4; cursor: default; }\n"
        if anchor not in html:
            raise SystemExit("fmt-tab active rule missing; refusing to publish")
        html = html.replace(anchor, insert, 1)
    if _OLD_FMT_HANDLER in html:
        html = html.replace(_OLD_FMT_HANDLER, _NEW_FMT_HANDLER, 1)
    if "data-src-916-day" in html and _OLD_DAY_MARK in html and "hide916" not in html:
        html = html.replace(_OLD_DAY_MARK, _NEW_DAY_MARK, 1)
    if _OLD_COPY in html:
        html = html.replace(_OLD_COPY, _NEW_COPY, 1)
    return html


def load_descriptions() -> dict[str, str]:
    """Verbatim tourist copy. Values are applied exactly; never edited here."""
    if not DESCRIPTIONS_PATH.is_file():
        raise SystemExit(f"missing {DESCRIPTIONS_PATH}")
    data = json.loads(DESCRIPTIONS_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data:
        raise SystemExit("scene_descriptions.json must be a non-empty object")
    out: dict[str, str] = {}
    for key, value in data.items():
        if not isinstance(key, str) or not isinstance(value, str) or value == "":
            raise SystemExit(f"bad description entry {key!r}")
        out[key] = value
    return out


def apply_descriptions(html: str, descriptions: dict[str, str]) -> str:
    """Replace description string literals for the listed scenes only.

    The rest of each scene object, including scenes not listed, is left
    byte-for-byte. A second publish writes the same literals again.
    """
    i, j = _js_span(html, "const SCENES = ", "[", "]")
    block = html[i:j]
    pattern = re.compile(r'(description:\s*)"(?:\\.|[^"\\])*"')
    for entry_id, text in descriptions.items():
        marker = f'entry_id: "{entry_id}"'
        start = block.find(marker)
        if start < 0:
            raise SystemExit(f"{entry_id} missing from scene catalogue")
        if block.find(marker, start + len(marker)) >= 0:
            raise SystemExit(f"{entry_id} appears more than once in the scene catalogue")
        next_at = block.find('\n        entry_id: "', start + len(marker))
        end = next_at if next_at >= 0 else len(block)
        chunk = block[start:end]
        quoted = json.dumps(text, ensure_ascii=False)
        updated, n = pattern.subn(lambda match, q=quoted: match.group(1) + q, chunk, count=1)
        if n != 1:
            raise SystemExit(f"could not replace description for {entry_id}")
        block = block[:start] + updated + block[end:]
    return html[:i] + block + html[j:]


def assert_descriptions(scenes: list[dict], descriptions: dict[str, str]) -> None:
    """Every listed entry id is present once and its description matches exactly."""
    seen: dict[str, int] = {}
    by_id: dict[str, str] = {}
    for scene in scenes:
        entry_id = scene["entry_id"]
        seen[entry_id] = seen.get(entry_id, 0) + 1
        by_id[entry_id] = scene.get("description") or ""
    dupes = [entry_id for entry_id, count in seen.items() if count != 1]
    if dupes:
        raise SystemExit("duplicate entry ids: " + ", ".join(dupes[:8]))
    missing = [entry_id for entry_id in descriptions if entry_id not in by_id]
    if missing:
        raise SystemExit("descriptions missing from catalogue: " + ", ".join(missing[:8]))
    mismatched = [
        entry_id for entry_id, text in descriptions.items() if by_id[entry_id] != text
    ]
    if mismatched:
        raise SystemExit("description text mismatch: " + ", ".join(mismatched[:8]))


def publish_html(html: str, root: Path | None = None, tags: dict[str, list[str]] | None = None) -> str:
    root = root or ROOT
    tags = dict(tags if tags is not None else load_tags())
    descriptions = load_descriptions()
    html = apply_descriptions(html, descriptions)
    scenes = parse_scenes(html)
    html, scenes, _drops = drop_missing_scene_lines(html, scenes, root)
    html = strip_phase1(html)
    meta = build_meta(scenes, root, tags)
    html = insert_phase1(html, meta)
    html = apply_a7(html)
    assert_phase1(html)
    assert_descriptions(parse_scenes(html), descriptions)
    return html


def assert_phase1(html: str) -> None:
    required = (
        'id="q"',
        'id="region"',
        'id="f-daynight"',
        'id="f-mood"',
        ">Day</option>",
        ">Night</option>",
        ">Coastal</option>",
        ">Mountain</option>",
        ">Urban</option>",
        ">Historic</option>",
        'id="result-count"',
        'id="clear">Clear all</button>',
        "countEl.textContent = filtered.length",
        "card.id = s.entry_id;",
        "function sceneAlt(s)",
        "alt=\"${esc(sceneAlt(s))}\"",
        "const FRANCE_META=",
        "window.__phase1Enhance",
        "Copy link",
        "Copied \\u2713",
        "G-PDJ4WSS725",
        'const file916 = s.file_9x16 || "";',
        "flag-chip.flag-no",
        "getAttribute('data-src-45')",
        "getAttribute('data-format')",
        "^audio\\/",
        "Free · no credit needed",
        "class=\"flag\"",
        "lb-narrate",
        "data-format=\"16x9\"",
        "Download 16:9",
        "if (!o[3]) continue;",
        'const file16 = s.file_16x9 || "";',
        "(day16 || day45)",
    )
    missing = [item for item in required if item not in html]
    if missing:
        raise SystemExit("regenerated index is missing Phase-1 markers: " + ", ".join(missing))
    if html.count('id="f-daynight"') != 1:
        raise SystemExit("day/night filter was duplicated")
    if html.count("const FRANCE_META=") != 1:
        raise SystemExit("FRANCE_META was duplicated")
    if _OLD_NORWAY in html:
        raise SystemExit("old Norway flag chip survived")
    ga_ids = set(re.findall(r"G-[A-Z0-9]+", html))
    if ga_ids != {"G-PDJ4WSS725"}:
        raise SystemExit(f"GA4 measurement ids must be G-PDJ4WSS725 only, found {ga_ids}")
    if "dataset.src45" in html or "dataset.src916" in html or "tab.dataset.format" in html:
        raise SystemExit("tab image sources must use getAttribute, not camelCase dataset")
    banned_probe = (
        "data-916-ok",
        "data-916-missing",
        "probe.onerror",
        "new Image()",
        "format_9x16_approval_status",
        "tab.remove()",
    )
    survived = [item for item in banned_probe if item in html]
    if survived:
        raise SystemExit("9:16 runtime probe survived publish")


def prove(html: str | None = None) -> None:
    """Show a rebuild still emits Phase-1, including after the live patch is removed."""
    current = html if html is not None else INDEX.read_text(encoding="utf-8")
    tags = load_tags()
    published = publish_html(current, ROOT, tags)
    again = publish_html(published, ROOT, load_tags())
    if published != again:
        raise SystemExit("generator is not idempotent")

    parent = subprocess.check_output(
        ["git", "show", "48f7442:index.html"],
        cwd=ROOT,
        text=True,
    )
    if "f-daynight" in parent:
        raise SystemExit("expected 48f7442 index to be the pre-Phase-1 page")
    from_clobber = publish_html(parent, ROOT, load_tags())
    clobber_again = publish_html(from_clobber, ROOT, load_tags())
    if from_clobber != clobber_again:
        raise SystemExit("clobber rebuild is not idempotent")
    assert_phase1(from_clobber)
    if "f-daynight" not in from_clobber or "card.id = s.entry_id;" not in from_clobber:
        raise SystemExit("clobber rebuild dropped Phase-1")

    scenes = parse_scenes(published)
    meta_match = re.search(r"const FRANCE_META=(\{.*?\});", published)
    if not meta_match:
        raise SystemExit("published page has no FRANCE_META")
    meta = json.loads(meta_match.group(1))
    first = related_ids(meta, "FR-01-001")
    if len(first) != 4:
        raise SystemExit(f"FR-01-001 related count is {len(first)}")
    if first != sorted(first):
        raise SystemExit(f"FR-01-001 related order is not deterministic by id: {first}")
    region = meta["FR-01-001"][0]
    if any(meta[item][0] != region for item in first):
        raise SystemExit("same-region scenes did not sort ahead of other moods")
    second = related_ids(meta, "FR-01-001")
    if first != second:
        raise SystemExit("related order changed between calls")

    sample = dict(scenes[0])
    sample["file_16x9_day"] = "assets/does-not-exist-daylight-16x9.png"
    sample["file_4x5_day"] = "assets/does-not-exist-daylight-4x5.png"
    sample["file_9x16"] = "assets/does-not-exist-9x16.png"
    sample["file_9x16_day"] = "https://example.invalid/missing-9x16.png"
    pruned = prune_scene(sample, ROOT)
    if "file_16x9_day" in pruned or "file_4x5_day" in pruned:
        raise SystemExit("missing daylight masters were kept")
    if "file_9x16" in pruned or "file_9x16_day" in pruned:
        raise SystemExit("9:16 master that is not on disk was kept")
    if not pruned.get("file_16x9"):
        raise SystemExit("present master was dropped")

    real_portrait = "assets/fr-01-001-16x9.png"
    if not master_on_disk(real_portrait, ROOT):
        raise SystemExit("expected a local master for the 9:16 disk gate")
    on_disk = dict(scenes[0])
    on_disk["file_9x16"] = real_portrait
    if prune_scene(on_disk, ROOT).get("file_9x16") != real_portrait:
        raise SystemExit("9:16 master on disk was dropped")
    empty_portrait = ROOT / "assets" / "_empty-9x16-gate.png"
    empty_portrait.write_bytes(b"")
    try:
        empty_scene = dict(scenes[0])
        empty_scene["file_9x16"] = "assets/_empty-9x16-gate.png"
        if "file_9x16" in prune_scene(empty_scene, ROOT):
            raise SystemExit("empty 9:16 file was emitted")
    finally:
        empty_portrait.unlink(missing_ok=True)

    def inject_field(html: str, entry_id: str, key: str, value: str) -> str:
        i, j = _js_span(html, "const SCENES = ", "[", "]")
        block = html[i:j]
        marker = f'entry_id: "{entry_id}"'
        start = block.find(marker)
        if start < 0:
            raise SystemExit(f"{entry_id} missing from scene catalogue")
        line_end = block.find("\n", start)
        inserted = f'\n          {key}: "{value}",'
        block = block[:line_end] + inserted + block[line_end:]
        return html[:i] + block + html[j:]

    gated = inject_field(published, "FR-01-001", "file_9x16", "assets/does-not-exist-9x16.png")
    gated = inject_field(gated, "FR-01-002", "file_9x16", "https://example.invalid/fr-9x16.png")
    gated = inject_field(gated, "FR-01-003", "file_9x16", real_portrait)
    gated = inject_field(gated, "FR-01-003", "file_9x16_day", "assets/does-not-exist-9x16-day.png")
    gated_html = publish_html(gated, ROOT, load_tags())
    gated_scenes = {scene["entry_id"]: scene for scene in parse_scenes(gated_html)}
    if "file_9x16" in gated_scenes["FR-01-001"] or "file_9x16" in gated_scenes["FR-01-002"]:
        raise SystemExit("publish emitted a 9:16 path that is not on disk")
    if gated_scenes["FR-01-003"].get("file_9x16") != real_portrait:
        raise SystemExit("publish dropped a 9:16 master that is on disk")
    if "file_9x16_day" in gated_scenes["FR-01-003"]:
        raise SystemExit("publish emitted a missing daylight 9:16 master")
    if "new Image()" in gated_html or "data-916-ok" in gated_html:
        raise SystemExit("publish still contains the 9:16 click probe")

    # Empty thumb is excluded from the four related slots.
    broken = {k: list(v) for k, v in meta.items()}
    victim = first[0]
    broken[victim][3] = ""
    reranked = related_ids(broken, "FR-01-001")
    if victim in reranked:
        raise SystemExit("missing master was still chosen as a related thumb")
    if len(reranked) != 4:
        raise SystemExit("related row did not backfill after a missing thumb")

    descriptions = load_descriptions()
    assert_descriptions(parse_scenes(published), descriptions)
    assert_descriptions(parse_scenes(again), descriptions)
    assert_descriptions(parse_scenes(from_clobber), descriptions)
    print("prove ok")
    print(f"scenes {len(scenes)}")
    print(f"descriptions {len(descriptions)} exact")
    print(f"FR-01-001 related {first}")
    print("clobber rebuild emitted Phase-1")
    print("second regenerate byte-identical")
    print("descriptions survived regenerate and clobber rebuild")
    return published


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish the France gallery index.")
    parser.add_argument("--prove", action="store_true", help="Run regenerate survival checks, then publish.")
    parser.add_argument("--dry-run", action="store_true", help="Check the publish without writing index.html.")
    args = parser.parse_args()
    original = INDEX.read_text(encoding="utf-8")
    if args.prove:
        prove(original)
    published = publish_html(original)
    if args.dry_run:
        print(f"dry-run ok ({len(published)} bytes)")
        return
    INDEX.write_text(published, encoding="utf-8")
    # A second pass must not change the file the generator just wrote.
    second = publish_html(INDEX.read_text(encoding="utf-8"))
    if second != published:
        INDEX.write_text(second, encoding="utf-8")
        raise SystemExit("wrote index.html but a second pass still differed")
    print(f"wrote index.html ({published.count('entry_id:')} scenes)")


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.exit(0)
