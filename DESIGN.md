---
name: FoxProfile
description: Self-hosted anti-detect profile manager; every profile reads as a passport data page with an entry stamp for its state.
colors:
  paper: "#F3F4EF"
  paper-raised: "#FBFBF8"
  paper-sunk: "#E9ECE4"
  rule: "#D5DACF"
  rule-strong: "#BCC3B6"
  ink: "#1E2422"
  ink-2: "#48514C"
  ink-3: "#66706A"
  cover: "#17332E"
  cover-deep: "#102622"
  cover-line: "#21433C"
  cover-ink: "#E8EFEA"
  cover-muted: "#A3BAB0"
  act: "#C2510F"
  act-hover: "#A84408"
  live: "#5B3FA8"
  live-tint: "#EFECF6"
  ok: "#1F7A50"
  err: "#B42330"
  err-hover: "#951C27"
  err-tint: "#F7E7E8"
  warn: "#8A5A00"
  warn-tint: "#F6EEDB"
  row-selected: "#E4EBE2"
typography:
  headline:
    fontFamily: "Be Vietnam Pro, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "26px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Be Vietnam Pro, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "19px"
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Be Vietnam Pro, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  body-strong:
    fontFamily: "Be Vietnam Pro, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "14.5px"
    fontWeight: 600
    lineHeight: 1.35
  label:
    fontFamily: "Be Vietnam Pro, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "12px"
    fontWeight: 600
    lineHeight: 1.35
  data:
    fontFamily: "JetBrains Mono, ui-monospace, SF Mono, Consolas, monospace"
    fontSize: "12.5px"
    fontWeight: 400
    lineHeight: 1.35
    letterSpacing: "-0.01em"
    fontFeature: "tnum"
  data-minor:
    fontFamily: "JetBrains Mono, ui-monospace, SF Mono, Consolas, monospace"
    fontSize: "11.5px"
    fontWeight: 400
    lineHeight: 1.35
  stamp:
    fontFamily: "JetBrains Mono, ui-monospace, SF Mono, Consolas, monospace"
    fontSize: "10.5px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "0.08em"
rounded:
  badge: "4px"
  tag: "5px"
  stamp: "6px"
  nav: "7px"
  control: "8px"
  sheet: "10px"
  dialog: "12px"
spacing:
  row-height: "58px"
  header-row-height: "40px"
  row-padding-x: "14px"
  column-gap: "16px"
  field-gap: "12px"
  field-stack: "14px"
  main-padding: "26px 32px 40px"
  rail-padding: "22px 16px 18px"
  rail-width: "252px"
components:
  button-act:
    backgroundColor: "{colors.act}"
    textColor: "#FFFFFF"
    typography: "{typography.body-strong}"
    rounded: "{rounded.control}"
    padding: "0 16px"
    height: "38px"
  button-act-hover:
    backgroundColor: "{colors.act-hover}"
  button-ink:
    backgroundColor: "{colors.ink}"
    textColor: "#FFFFFF"
    rounded: "{rounded.control}"
    padding: "0 16px"
    height: "38px"
  button-ink-hover:
    backgroundColor: "#000000"
  button-line:
    backgroundColor: "{colors.paper-raised}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "0 16px"
    height: "38px"
  button-danger:
    backgroundColor: "{colors.err}"
    textColor: "#FFFFFF"
    rounded: "{rounded.control}"
    padding: "0 16px"
    height: "38px"
  button-danger-hover:
    backgroundColor: "{colors.err-hover}"
  button-row-main:
    rounded: "{rounded.control}"
    width: "96px"
    height: "36px"
  input:
    backgroundColor: "{colors.paper-raised}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "0 12px"
    height: "40px"
  nav-item:
    textColor: "{colors.cover-ink}"
    rounded: "{rounded.nav}"
    padding: "0 10px"
    height: "36px"
  nav-item-hover:
    backgroundColor: "{colors.cover-deep}"
  nav-item-active:
    backgroundColor: "{colors.cover-ink}"
    textColor: "{colors.cover}"
  sheet:
    backgroundColor: "{colors.paper-raised}"
    rounded: "{rounded.sheet}"
  row:
    backgroundColor: "{colors.paper-raised}"
    padding: "0 14px"
    height: "{spacing.row-height}"
  row-live:
    backgroundColor: "{colors.live-tint}"
  row-selected:
    backgroundColor: "{colors.row-selected}"
  bulk-bar:
    backgroundColor: "{colors.paper-sunk}"
    padding: "10px 14px"
  os-badge:
    textColor: "{colors.ink}"
    typography: "{typography.data-minor}"
    rounded: "{rounded.badge}"
    width: "38px"
    height: "22px"
  stamp-live:
    textColor: "{colors.live}"
    typography: "{typography.stamp}"
    rounded: "{rounded.stamp}"
    padding: "3px 9px 2px"
  stamp-starting:
    textColor: "{colors.ink-2}"
    typography: "{typography.stamp}"
    rounded: "{rounded.stamp}"
    padding: "3px 9px 2px"
  stamp-failed:
    textColor: "{colors.err}"
    typography: "{typography.stamp}"
    rounded: "{rounded.stamp}"
    padding: "3px 9px 2px"
  dialog:
    backgroundColor: "{colors.paper-raised}"
    rounded: "{rounded.dialog}"
    width: "500px"
---

# Design System: FoxProfile

## Overview

**Creative North Star: "The Passport Data Page"**

Every profile is one identity with one device, set down like the data page of a passport: security paper, hairline rules, ink text, fixed fields that line up the same way on every page. A running profile gets an entry stamp. The deep green passport cover forms the left rail. It carries a fine guilloché line pattern, the one ornament in the system. Everything else is paper and ink.

The system is dense and made for scanning. Operators keep tens to hundreds of profiles open all day, so the profile list is a ruled table rather than a grid of cards. Every row has the same columns, height and baseline. Colour carries meaning. Fox orange marks things you can press. Stamp inks mark state: violet for live, green for ok, red for error and amber for warnings. Paper and ink cover everything else. The world explicitly refuses the category's dark card dashboard with coloured OS tiles and orange-on-black.

Two surfaces share this one system. The web panel (`src/web/index.html`, CSS custom properties on `:root`) is the token source. The Flet desktop app (`src/ui/theme/colors.py`, `styles.py`) mirrors the same values under its own key names. Where Flet cannot match the web, the differences are recorded below.

**Key Characteristics:**
- Light security-paper ground with hairline rules. A passport-cover green rail carries the guilloché.
- Flat colour throughout: no gradient fills, no glass, no glow.
- Fox orange appears only on pressable things.
- State is encoded by form (rule count, rotation, strike) as well as by ink colour.
- A dual typeface system: Be Vietnam Pro for UI language, JetBrains Mono for machine values (proxy, IP, timezone, locale, screen, fingerprint, counts).
- One column grid and one row height for the header and every row.

## Colors

The palette is paper and ink with a deep green cover. One warm action colour sits on top, and four stamp inks are reserved for state.

### Primary
- **Fox Orange** (act): the only action colour. It fills the Launch button (`Mở`), Create profile (`Tạo profile`), Save, the bulk Launch and the dialog confirm. It is also the focus outline and the text caret. Hover deepens it to **Burnt Fox** (act-hover).

### Secondary
- **Passport Cover Green** (cover): the rail ground, the viewer bar, active chips, checked checkboxes, the focused-field border, text selection, and the Chrome engine label and tag. **Cover Deep** (cover-deep) is the rail hover, the segmented-control well, the activity log and code blocks. **Cover Line** (cover-line) draws the guilloché strokes and the rail-side outlines. **Cover Ink** (cover-ink) is text on the cover and the active nav pill. **Cover Muted** (cover-muted) is secondary text on the cover.

### Tertiary (stamp inks)
- **Entry Violet** (live): the live stamp and the running count in the page head. **Violet Wash** (live-tint) is the background of a running row.
- **Visa Green** (ok): success messages and confirmed Check IP lines.
- **Refusal Red** (err): the failed stamp, error text, destructive confirm buttons and error toasts. **Refusal Red Deep** (err-hover) is the hover state. **Red Wash** (err-tint) is the hover behind a delete icon.
- **Customs Amber** (warn): warning icons. **Amber Wash** (warn-tint) is the background of a warning note or Check IP warning line. Text on amber wash uses darker amber inks (`#5E3E00`, `#6B4500`) for contrast.

### Neutral
- **Security Paper** (paper): the page ground, the table header row and the dialog footer.
- **Raised Paper** (paper-raised): the profile sheet, inputs, line buttons and dialogs.
- **Sunk Paper** (paper-sunk): the bulk bar, ghost and icon hover, inline code and the loading launch button.
- **Hairline** (rule): row dividers and sheet and panel borders. **Strong Hairline** (rule-strong): input and line-button borders, tags, scrollbar thumb and disabled icon ink on desktop.
- **Ink** (ink): primary text and the Stop button. **Ink 2** (ink-2): secondary text and icon buttons. **Ink 3** (ink-3): column headers, placeholders, minor second lines and the idle status.
- **Selected Sheet** (row-selected): background of a checked row.

### Named Rules
**The Pressable Orange Rule.** Fox orange appears only on things you can press. It is never used for a heading, a status, a badge or decoration. If an element is orange and nothing happens when you click it, it is wrong.

**The Stamp Ink Rule.** Violet, green, red and amber mean state and nothing else. Violet in particular is never used as an accent.

**The Ink Stop Rule.** Stop is an ink button, not red. Stopping a browser is routine, not destructive. Red is reserved for failure and for confirming deletion.

## Typography

**UI Font:** Be Vietnam Pro (with system-ui, -apple-system, Segoe UI, sans-serif), bundled locally at 400/500/600/700.
**Data Font:** JetBrains Mono (with ui-monospace, SF Mono, Consolas, monospace), bundled as a variable font.

**Character:** Be Vietnam Pro is a clean geometric sans that renders Vietnamese diacritics properly, and it carries all the human language. JetBrains Mono sets anything a machine produced, the way a passport sets its machine-readable zone: proxy host:port, scheme, timezone, locale, screen and CPU, OS badge, nav counts, stamp text and code.

### Hierarchy
- **Headline** (700, 26px, 1.2, -0.02em): the page title (`Profile`) and the login heading (24px).
- **Title** (700, 19px, -0.01em): dialog titles. Empty-state titles use 18px.
- **Body** (400, 14px, 1.5): default UI text, inputs and buttons. Secondary lines and subtitles use 13 to 13.5px.
- **Body Strong** (600, 14.5px web / 14px desktop): the profile name in a row. Button labels use 600 weight at body size.
- **Label** (600, 12px, ink-3): table column headers and the rail nav title. Field labels use 12.5px/600 in ink-2.
- **Data** (JetBrains Mono 400, 12.5px, tabular figures, -0.01em): the first line of proxy and timezone cells, and inline code.
- **Data Minor** (JetBrains Mono, 11.5px, ink-3): the second line of a cell (scheme, locale, screen and CPU). The OS badge uses 11px/600.
- **Stamp** (JetBrains Mono 700, 10.5px, 0.08em, uppercase): stamp text. The launch time beneath it uses 10px/500.

### Named Rules
**The Machine Zone Rule.** Values a machine reads (proxy, IP, timezone, locale, screen, fingerprint, counts) are set in JetBrains Mono. Words a person reads are set in Be Vietnam Pro. Never set a sentence in mono, and never set an IP in the sans.

**The Two-Line Cell Rule.** Every data cell in a profile row has exactly two lines: a primary line, plus a minor line in ink-3. When there is no value, the minor line is filled with honest copy (`không proxy`, `Theo IP`, `chưa có fingerprint`). That keeps row heights and baselines identical.

## Layout

The shell has two columns. On the left is the cover rail (252px on web, 240px on desktop), which is sticky and full height. On the right is the main area (padding 26px 32px 40px). The main area holds a head row with the headline and counts on the left, the search field (up to 340px) on the right, and then a single ruled sheet holding the profile table.

**The One Grid Rule.** The header row and every profile row share one column template: select (32px), profile name, device, proxy, timezone and locale, stamp (112px web / 100px desktop), and actions (232px). Each row is 58px tall with a 14px side padding. The header row is 40px on paper. Column gap is 16px on web and 12px on desktop. Nothing in a row may change the row height.

Responsive behaviour (web only):
- **At 1180px and below:** the timezone and locale column drops out. Geo moves inline into the row, and the stamp and action columns narrow (108px and 218px).
- **At 860px and below:** the rail becomes a top band. The brand and Create button share a line, the filters become a horizontally scrolling row, and the footer controls wrap. The header row hides, and each profile becomes a stacked block: name and stamp on the first line, then device, then proxy, then a full-width action line with Launch up to 200px. Main padding is 18px 14px.

The desktop window opens at 1400×860 and its minimum size is 1180×680, so it never needs the stacked layout.

Spacing rhythm: fields stack at 14px with 12px between paired fields. Rail sections are separated by 22px. Rail buttons are 36px tall with a 2px gap.

## Elevation & Depth

The system is flat. Depth comes from tone: paper, raised paper, sunk paper and the darker cover, with hairline rules between them. The profile sheet, rows, rail, buttons and inputs have no shadow. Only surfaces that float above the page cast a shadow. Every shadow is soft, tinted with cover green and never offset hard.

### Shadow Vocabulary
- **Dialog lift** (`0 24px 60px -12px rgba(16,38,34,.45), 0 2px 8px rgba(16,38,34,.12)`): modal dialogs, over a cover-deep scrim (`rgba(16,38,34,.42)`).
- **Toast lift** (`0 12px 30px -8px rgba(0,0,0,.4)`): the bottom-right toast.
- **Screen lift** (`0 10px 30px -10px rgba(16,38,34,.35)`): the remote screen image in the viewer.
- **Segment nub** (`0 1px 2px rgba(0,0,0,.25)`): the active language segment inside its cover-deep well.
- **Focus halo** (`0 0 0 3px rgba(23,51,46,.14)`): a focused input, together with its cover-green border.

### Named Rules
**The Flat Paper Rule.** Anything that sits on the page is flat. Only things that float above the page (dialog, toast, remote screen) may cast a shadow. Gradient fills, glassy blur and glow are never used.

## Shapes

Corners are gently rounded and grow with the size of the surface. The OS badge is 4px, the tag 5px, the stamp 6px, nav pills and chips 7px, buttons and inputs 8px, the sheet 10px and dialogs 12px. Borders are hairlines: 1px rule for dividers, and 1px rule-strong for controls. The only heavier strokes are the OS badge (1px ink-2 outline) and the stamp (1.5px).

The guilloché is a repeating 160×44 tile of three interlaced sine-wave strokes (0.7px, cover-line on cover). The web draws it as an inline SVG data URI. The desktop draws `src/assets/rail-guilloche.png`, a 2× raster rendered from that same SVG and painted at scale 2. The guilloché appears only on cover surfaces: the rail, and the login screen's cover side, which reuses the rail.

## Components

### Buttons
Buttons are solid and quiet. The fill colour says what kind of action it is.
- **Shape:** gently rounded (8px). Height is 38px by default. Row Launch/Stop is 36px (96px wide on web, 100px on desktop). Rail Create is 42px. Bulk and inline buttons are 32 to 34px.
- **Act (orange):** white 600 label with an optional 16 to 18px stroke icon. It covers Launch, Create, Save and the bulk Launch. Hover deepens it to act-hover.
- **Ink:** a filled ink button with hover to black. It is used for Stop only.
- **Line:** raised paper with a 1px strong-hairline border and a 500 label. It covers Cancel, Close, Import/Export and the bulk Stop and Delete. Hover darkens the border to ink-2. On the cover, line buttons are transparent with a cover-line border.
- **Danger:** a filled err button. It appears only as the confirm in a destructive dialog.
- **Ghost / Icon:** a transparent button in ink-2. Hover fills it with sunk paper. Icon buttons are 34px on web and 40px on desktop. The delete icon hovers to err-tint with err ink.
- **Focus:** a 2px act outline at 2px offset (web). Disabled buttons drop to 45% opacity, or 35% for icons.

### Profile Sheet and Rows
- **Sheet:** raised paper with a 1px rule border and 10px corners. There is no shadow.
- **Rows:** 58px tall with a 1px rule divider and no zebra striping. Hover is a barely darker paper (`#F6F7F2`, web only). A running row is filled with live-tint. A selected row is filled with row-selected.
- **Bulk bar:** when rows are selected, a sunk-paper band sits at the top of the sheet. It shows the count (600), then Launch (act), Stop and Delete (line), and a ghost Clear pushed to the far right.

### OS Badge and Tags
- **OS badge:** a 38×22 outlined box with a 1px ink-2 border and 4px corners, holding WIN, MAC or LIN in 11px/600 mono. Every OS gets the same monochrome badge, with no coloured OS tiles.
- **Engine:** Camoufox is set in plain ink. Chrome is set in cover green at 600 weight. On web, its tag uses a soft green-grey fill.

### Inputs / Fields
- **Style:** raised paper with a 1px rule-strong border, 8px corners and 40px height on web. Labels sit above the field at 12.5px/600 in ink-2. Hints are 12px in ink-3. Selects use a drawn chevron.
- **Focus:** the border turns cover green, with a 3px cover-tinted halo on web. The caret is fox orange.
- **Disabled:** sunk paper with ink-3 text. Example: the engine field, which is fixed after creation.
- **Desktop difference:** Flet dropdowns cannot go below 48px, so desktop text fields keep Material's 48px height to stay aligned with them. Desktop labels sit above the fields as separate text rather than floating.

### Navigation (the cover rail)
- From top to bottom: brand (fox mark, `FoxProfile` at 18px/700, subtitle in cover-muted), a full-width orange Create button, the filter list (`Tất cả`, `Đang chạy`, `Có proxy`, `Không proxy`, `Engine Chrome`), MCP and API links, and the language segment (`Tiếng Việt` / `English`).
- Filter items are 36px tall with 7px corners, in cover-ink at 500. Hover fills them with cover-deep. The active item is a cover-ink pill with cover-coloured 600 text. Counts are right-aligned in mono.
- On desktop, the rail also holds a collapsible activity log (`Nhật ký hoạt động`) on cover-deep.

### Dialogs
- Raised paper, 12px corners and the dialog-lift shadow. Width is 500px, or 740px for wide dialogs. The title is 19px/700 with a 13.5px ink-2 subtitle. On web, the footer is a paper band with a hairline top border, and buttons are right-aligned with Cancel (line) before Confirm (act or danger).
- Notes: warnings sit on amber wash with an amber icon. Calm notes sit on sunk paper. Check IP results are a ruled list: lead line on paper, ok lines in green, warn lines on amber wash.

### The Entry Stamp (signature)
The entry stamp is the profile's state, marked like a rubber stamp on a passport page.
- **Live:** violet ink with a double rule (a 1.5px frame plus a 1px outer ring 2px out), rotated -4°. It reads `ĐANG CHẠY` / `RUNNING` with the launch time (HH:MM) beneath. A 35% white wash sits under the ink.
- **Starting / Stopping:** ink-2 on a single thin rule with no outer ring, reading `ĐANG MỞ` / `ĐANG DỪNG`. The web panel uses a dashed 1.5px rule tilted -2°. The desktop uses a solid 1px rule set straight, because Flet borders cannot be dashed.
- **Failed:** red ink on a single 1.5px rule, rotated -4°, with the text struck through (`LỖI` / `FAILED`). Hovering it on web shows the error.
- **Idle:** no stamp. It shows plain `Đã dừng` in ink-3 at 13px.
- **Motion:** on web, a stamp that has just gone live lands once (0.34s, `cubic-bezier(.16,1,.3,1)`). It scales from 1.55× at -11° down to 1× at -4°, fading in from 25%. It never loops. The animation is removed under `prefers-reduced-motion`. The desktop stamp is static.

**The Form-Before-Hue Rule.** You can tell every state apart without colour: a double rule means live, a single plain rule means in transition, a struck rule means failed, and no frame means idle.

## Do's and Don'ts

### Do:
- **Do** keep fox orange (#C2510F) on pressable elements only: Launch, Create, Save, confirm and the focus ring.
- **Do** make Stop an ink button (#1E2422) and keep red for failure and destructive confirmation.
- **Do** put every profile row on the shared column grid at 58px, with two lines in every data cell.
- **Do** set proxy, IP, timezone, locale, screen, fingerprint and counts in JetBrains Mono with tabular figures.
- **Do** encode state by stamp form (double, single, struck, none) as well as ink.
- **Do** separate surfaces with hairline rules and paper tones instead of shadows.
- **Do** keep industry terms in English inside Vietnamese copy (profile, proxy, cookie, engine, fingerprint).

### Don't:
- **Don't** build the dark card dashboard this world refuses: no dark-mode card grid, no coloured OS tiles, no orange-on-black.
- **Don't** use gradient fills, glass or blur, or glow anywhere.
- **Don't** use violet, green, red or amber as decoration or accent. They are stamp inks for state.
- **Don't** put the guilloché on paper surfaces, or add any other pattern.
- **Don't** add shadows to rows, the sheet, buttons or inputs.
- **Don't** let a row grow a third line or collapse to one. Fill empty values with honest minor copy instead.
