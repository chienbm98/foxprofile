---
version: 1
slug: "src-web-index-html"
primary_target: "src/web/index.html"
related_targets: ["src/ui"]
---

## Scope

Whole app redesign, both surfaces: the web panel (`src/web/index.html`) and the Flet desktop app (`src/ui/`). Visitor mode: Operate.

## Audience and job

MMO/ads operators, agencies and automation users managing 20–100 profiles: find a profile, launch/stop it in one click, read its device, proxy and geo at a glance, act in bulk, move cookies, check IP. Must keep: the big Launch/Stop button on every profile, the left sidebar. Must avoid: gaming/hacker look, generic SaaS look, sparse layouts, hard-to-read state.

## Direction contract

THESIS: Every profile is a passport data page: one identity, one device, and an entry stamp saying it is live. Refuses the category's dark card dashboard with colored OS tiles and orange-on-black.

OWN-WORLD: Light security-paper ground (#F3F4EF) with hairline rules; a deep passport-cover green rail (#17332E) carrying a fine guilloché line pattern; ink text; fox orange only on things you can press; stamp inks (violet live, green ok, red error, amber warning) for state. Be Vietnam Pro for UI, a monospaced data face for proxy, IP, timezone and fingerprint values. Flat colour only: no gradient, glass or glow.

STORY: The operator sees which accounts are live and where they appear to be from, finds one by name or proxy, launches or stops it in one click, and trusts the list because every row reads the same columns.

FIRST VIEWPORT: Left green rail (logo, Tạo profile, filters with counts, MCP, language). Main: title + counts, search, then a dense aligned table of profiles: select, name + engine, device (OS · engine · screen), proxy, timezone/locale, status stamp, Launch/Stop plus icon actions. Bulk bar above the table when rows are selected.

SIGNATURE MOVE: The entry stamp. A running profile's status is a rotated rubber-stamp mark in violet ink with a double rule and the launch time; it lands with one short press animation when the profile starts. Starting is a dashed stamp, failure a struck red stamp; state reads by form as well as colour. Raises kept: one column grid and baseline for every row (botanical folio); orange reserved for actions (warm consumer app); flat colour only (zoo map); state encoded by line form, not hue alone (emission rail).

FORM: Passport data page and entry stamps, position 3 of the grounded list; seed key 795ac146.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
