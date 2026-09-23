# Jason D’s Vision — France

Preview gallery of original photorealistic AI artistic interpretations of real places in France. Every image is free to use for any purpose, with no credit required. Scenes are labelled **Candidate** until an independent QC pass. Nothing on this page is marked Approved.

The live catalogue this build continues is [Jason D’s Vision — France](https://devlij.github.io/jason-ds-vision-france-preview/). Country switcher on the page: France, [Germany](https://devlij.github.io/jason-ds-vision-germany/), [Italy](https://devlij.github.io/jason-ds-vision-italy-preview/), [Spain](https://devlij.github.io/Spain/).

## What this build adds

- **FR-01-001 through FR-01-124** stay in sequence, with no gaps. Their 16:9 card images still load from the live France gallery. Both master sizes remain linked in the scene data.
- **FR-01-009 Valensole** is a ground-level replacement. The aerial version was rejected. The new masters show harvested lavender stubble rows, the Plateau de Valensole behind them, and the 18:05 late-September scenario. Status stays Candidate.
- **FR-01-125 to FR-01-128** are Candidate scenes: Palais des Ducs in Dijon, Château d’Angers, the Belfry of Arras, and Les Saintes harbor at Terre-de-Haut.
- **FR-01-129 to FR-01-144** are the next Candidate scenes. They start with overseas and thin regions: Pointe des Châteaux, Rocher du Diamant, Piton de la Fournaise (no lava; vigilance bulletin), Île du Diable from Île Royale, Plage de Moya, and Gustavia in a thunderstorm, then Normandy American Cemetery, Yvoire, Mer de Glace, Cheverny, Saint-Jean-de-Luz, the Saline Royale, Cap Blanc-Nez, Porte Saint-Michel, the Calanques de Piana, and Metz Cathedral with dark windows after the published 19:00 close. Each has a 1920×1080 master and an 864×1080 master in `assets/`. Status stays Candidate.
- Region filter: `Brittany` is folded into `Bretagne`, and the two apostrophe spellings of Provence-Alpes-Côte d’Azur are one option.
- Each card has one 16:9 thumbnail that opens the full 16:9 file in a new tab, plus a short descriptive paragraph under the composition line. There is no 4:5 preview, download button, size toggle, or lightbox.

Scenario times and weather come from Open-Meteo model data. They are not verified on-site observations. Evidence cards are in `approvals/`. The build kit is `docs/kit-france-v1.0.md`.

## Run locally

```bash
python3 -m http.server 8741 --bind 0.0.0.0
```

Open `http://127.0.0.1:8741/`. Cards FR-01-001–124, except the replaced Valensole masters, need network access so they can load from the live gallery.
