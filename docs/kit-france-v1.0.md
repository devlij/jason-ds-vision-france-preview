# Jason D's Vision — Build Instruction Kit for Grok Bot (France)

A self-contained kit for a Grok-based agent to produce location scenes for the **Jason D's Vision** library: **France**. Follow it exactly. When in doubt, choose the option that is more honest about what is verified versus what is generated.

---

## 1. Mission

Jason D's Vision is a commercial library of **original photorealistic artistic interpretations** of real places — what a tourist would see at a real location on a particular day. Images are **AI-generated artistic interpretations, not photographs**. Every image is **free to use — personal or commercial — with no credit required**. Optional credit to "Jason D's Vision" is appreciated but never required.

## 2. Scope for this agent

- **Your territory: France only** — metropolitan France, Corsica, and the overseas departments, regions and collectivities. A Grok agent completed Italy (paused at 365 scenes); a ChatGPT agent is working Spain; a separate pipeline handles Germany. Do not duplicate their work.
- Produce scenes in the order given in Section 11 (or an updated order supplied later by Jason). Do not invent your own catalogue.
- Each scene = **two finished master images**: one **16:9** (1920×1080) and one **4:5** (864×1080 portrait).

## 3. Non-negotiable brand standards (every image)

Every finished master must carry, baked into the image:

1. **Exact caption** — plain `<site>, <City>`, no descriptor suffix, e.g. "Eiffel Tower, Paris". Bottom-left.
2. **Scenario timestamp** — format exactly: `Scenario: 23 September 2026 · 14:30 Europe/Paris`. Full month name, always — never mix short and long date formats. This labels the *depicted scenario*; it must never imply a verified on-site capture. Bottom-left, below the caption.
3. **AI disclosure** — bottom-left, smallest text, e.g. "AI-generated artistic interpretation · Not a photograph."
4. **Signature** — the exact string **Jason D's Vision** (curly apostrophe: `Jason D\u2019s Vision`). Bottom-right.

### On-image text format (mandatory)

- Text sits at the **bottom of the image** over a **gradient scrim** (fading upward), never a solid bar.
- Text must be **small and subordinate** — it must not interfere with the beauty of the image.
- Layout: caption, scenario, disclosure stacked bottom-left; signature bottom-right.
- Width-scaled font sizes (fraction of image width): caption **.016**, scenario **.012**, disclosure **.010**, signature **.018**.
- Keep preview-page buttons and overlays clear of the baked-in signature area.

## 4. Evidence card (required before generating each scene)

Do not generate until the evidence card is complete. Record:

- **Location/site + exact caption** to be baked into the image.
- **Camera viewpoint**: a verified tourist viewpoint (map link or named overlook/street position). If the exact camera point can't be verified, say so — a research gap is not a defect, but it must be labeled.
- **2 reference links**: independent sources (official tourism page, reputable photo reference, encyclopedia) describing or showing the view.
- **3 geometry anchors**: concrete spatial relationships.
- **Weather (model data only)**: provider (Open-Meteo), retrieval timestamp, valid time, conditions. Wording: "Model data from Open-Meteo, retrieved <time>, valid <time> — not a verified on-site observation." Never write "real-time conditions" or "observed".
- **Solar direction / time of day** for the scenario.
- **Independent description** of the view in your own words.
- **Source-use notes**: which sources were consulted, generation lineage (text-prompt-only unless stated), licensing notes for any reference material, commercial-terms notes.

## 5. Generation rules

- **Real-time scenarios (Jason directive).** Every scene depicts the *actual current conditions* in France at build time — the same convention as the Italy and Germany lines. Scenario timestamp = the real Europe/Paris time when you build the scene; weather = current model data valid for that time. Paris landmarks (Eiffel Tower, Louvre Pyramid, Sacré-Cœur) are floodlit at night, so night builds are night scenes of illuminated monuments — that is expected and welcome, not a problem to avoid. The scenario label still never implies a verified on-site capture; it labels the depicted real-time scenario.
- **Official illumination rule.** When an official schedule confirms lights are off at the scenario hour, never invent floodlighting — build an honestly labelled daytime (or unlit) interpretation instead.
- **Quality bar ("80% editorial target")**: at a glance, no identifiable architectural deviations from the reference, correct scenario/time-of-day handling, clean framing, no artifacts. This is a qualitative editorial target — **never present it as a measured statistic or percentage score**.
- **Text-prompt-only lineage by default.** If you image-anchor on any reference, **QC the starting image first** — anchoring preserves errors as reliably as correct details.
- Do not invent rankings, accuracy percentages, or "verified" claims about things you only researched.
- Do not depict identifiable real people prominently; avoid legible brand logos and copyrighted artwork as focal subjects.
- Never regenerate a finished scene solely to satisfy a stylistic preference once it meets the bar.

## 6. Honest terminology (mandatory)

| Never write | Write instead |
|---|---|
| "Real-time conditions" | "Model data from Open-Meteo, retrieved X, valid Y" |
| "Photograph of…" / "captured" | "Artistic interpretation · Scenario: …" |
| "80%+ recognizability (measured)" | "Editorial quality target met (review-based)" |
| "Verified on-site" (unless truly verified) | "Reported / modelled / reference-based" |
| "Worldwide library" (for a France-only page) | "Jason D's Vision — France" |

Scenario labels and weather data must never imply someone stood on the pavement with a camera.

## 7. Approval gates (internal checklist per scene)

Before marking a scene done, confirm all five:

1. **Visual/location** — matches reference arrangement; no major configuration errors.
2. **Technical** — both masters at correct dimensions and aspect ratios; text format per Section 3.
3. **Originality/provenance** — lineage recorded; no photographic inputs unless QC'd and logged.
4. **Commercial/IP** — no blocking people/logo/artwork issues; notes recorded (internal review, not legal certification).
5. **Publication readiness** — caption, scenario, signature, disclosure all present and legible.

Keep the preview page's approval status in sync: a scene the page calls a candidate must not be reported as approved, and vice versa.

## 8. File naming and organization

- Entry IDs: `FR-01-001`, `FR-01-002`, … (fixed sequence — one scheme, used everywhere, no regional prefixes mixed in). Keep a running log so IDs are never reused and no sequence gaps go unexplained.
- Paths: `library/world/France/<City>/fr-01-001-16x9.png` and `fr-01-001-4x5.png` (lowercase filenames).
- Keep an `approvals/` log per scene: `approvals/FR-01-001.md` with the five gates and the evidence card.

## 9. Report format (per scene, compact)

Report in batches of 3–4 scenes per message, one line each.

## 10. Hard boundaries

- **No credit requirement** on images, ever. No watermarks beyond the Jason D's Vision signature.
- **No narrative film/video work.** Still images only.
- Do not touch Italy, Spain, or Germany scenes.
- Do not present internal review as legal certification.
- Research and QC are your job — do not ask Jason or Julia to run checks you can perform.

## 11. France starter sequence

1. Paris — Eiffel Tower
2. Paris — Louvre (pyramid courtyard)
3. Paris — Notre-Dame Cathedral
4. Paris — Arc de Triomphe
5. Paris — Sacré-Cœur, Montmartre
6. Versailles — Palace of Versailles
7. Normandy — Mont Saint-Michel
8. Nice — Promenade des Anglais
9. Provence — Valensole lavender fields
10. Chamonix — Mont Blanc / Aiguille du Midi
11. Carcassonne — medieval citadel
12. Loire Valley — Château de Chambord
13. Strasbourg — Strasbourg Cathedral
14. Gironde — Dune du Pilat
15. Provence — Gorges du Verdon
16. Annecy — old town canals and lake

Scenario times: use the actual current Europe/Paris time at each build step (real-time convention — day or night as it really is).

### 11b. Full France coverage directive (standing)

After FR-01-016, continue systematically through every French region. See issued kit in chat for full regional anchor table and island coverage rules. Islands are not optional.

## 12. Gallery compatibility spec

Linked country galleries. Hub: https://muse.ai/s/jason-d-s-vision-gallery-bv6lxwcfmixal (Germany). Italy: https://devlij.github.io/jason-ds-vision-italy-preview/. France is the third page — do not edit the other galleries.

### 12a. Per-scene manifest (required)

`manifests/FR-01-001.json` with country exactly "France".

### 12b. Preview page (required)

- Top pointer, promise, license exact copy per issued kit.
- Country switcher: `France | Germany | Italy` (Germany → muse.ai hub; Italy → Italy preview URL).
- Title: "Jason D's Vision — France".
- Publish via GitHub Pages; stable URL; push every newly approved scene.
- Keep: entry ID, caption, scenario label, composition, approval status, license section and badge, footer, search, country switcher.

**Standing rule — Germany size presentation (Jason directive 2026-09-23):** Match the Germany main gallery card format exactly.

1. Each card shows ONE image: the 16:9 master as the thumbnail, linked to the full-size 16:9 file (opens in a new tab).
2. Remove from every card: the 4:5 portrait preview, Download 16:9 / Download 4:5 buttons, any lightbox/viewer, 16:9–4:5 toggle buttons, View image overlays, and Open original links.
3. Do NOT delete the 4:5 master files from the repo — only the card presentation changes. Still generate and store both 16:9 and 4:5 masters for every scene.
4. Keep everything else untouched as listed above.

---

*Kit version 1.0 — 2026-09-23. Issued for the Grok France agent. Full regional table and island list are in the issued chat kit; follow those anchors exactly.*
