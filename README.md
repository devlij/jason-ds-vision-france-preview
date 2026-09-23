# Jason D’s Vision — France

Preview gallery of original photorealistic AI artistic interpretations of real places in France. Every image is free to use for any purpose, with no credit required. Scenes are labelled **Candidate** until an independent QC pass. Nothing on this page is marked Approved.

The live catalogue this build continues is [Jason D’s Vision — France](https://devlij.github.io/jason-ds-vision-france-preview/). Country switcher on the page: France, [Germany](https://devlij.github.io/jason-ds-vision-germany/), [Italy](https://devlij.github.io/jason-ds-vision-italy-preview/), [Spain](https://devlij.github.io/Spain/).

## What this build adds

- **FR-01-001 through FR-01-144** stay in sequence, with no gaps. Their earlier card images still load from the live France gallery where this repo does not replace the file. Both master sizes remain linked in the scene data.
- **FR-01-145 to FR-01-160** are the next Candidate scenes. They open four collectivities that had no scene yet: Fort Louis at Marigot, Île aux Marins, Mount Otemanu from Matira, and Baie de Kanuméra. They add a second scene each for Martinique, La Réunion, Guyane, Mayotte, and Saint-Barthélemy, then raise the thinnest metropolitan regions and Corsica: Fontenay, Nonza, Laon Cathedral, Le Mans Cathedral, the Mulberry harbour at Arromanches, the Lion of Belfort, and Erbalunga. Each has a 1920×1080 master and an 864×1080 master in `assets/`. Status stays Candidate.
- Pointe du Hoc was not used. The American Battle Monuments Commission says that site is in restoration until mid-2027.
- Region filter: `Brittany` is folded into `Bretagne`, and the two apostrophe spellings of Provence-Alpes-Côte d’Azur are one option.
- Each card has one 16:9 thumbnail that opens the full 16:9 file in a new tab, plus a short descriptive paragraph under the composition line. There is no 4:5 preview, download button, size toggle, or lightbox.

Scenario times and weather come from Open-Meteo model data. They are not verified on-site observations. Evidence cards are in `approvals/`. The build kit is `docs/kit-france-v1.0.md`.

## Run locally

```bash
python3 -m http.server 8741 --bind 0.0.0.0
```

Open `http://127.0.0.1:8741/`. Cards FR-01-001–124, except the replaced Valensole masters, need network access so they can load from the live gallery.
