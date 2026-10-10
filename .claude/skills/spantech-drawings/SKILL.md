---
name: spantech-drawings
description: Span Tech reinforcement and PT drawings generator (shop drawings and design drawings from a RAM Concept .cpt model, the consultant's structural DXF or the office RFT plan) and the Drawings module of the PT Suite CRM. Use whenever the user (Span Tech, PT design office) asks about لوحات التسليح / shop drawings / design drawings / لوحات الكابلات / cable sheets / تفاصيل / U-bars / drops / punching / beam schedule / submittals / حصر / take-off / cost study, sends a drawing screenshot saying a bar, a leg, a text or a figure is wrong, wants a rule changed in `shopdrawings/` (Node) or `pydrawings/` (Python, the one-file `app.py`), or wants a package generated, checked or delivered. Covers the office drafting convention, the program layout, how to change a rule in both versions, how to verify and how to talk and deliver. Companion of `spantech-pt` (that one covers drawing → RAM model; this one covers RAM model → drawings).
---

# Span Tech — RAM Concept / structural drawing → reinforcement & PT drawings

You work with the Span Tech structural office (post-tensioned slabs, Riyadh). This skill covers the
**drawings side**: turning a RAM Concept model (`.cpt`), the consultant's structural G.A. (DXF) or the
office's own RFT design plan into the office's **design drawings** (`SPAN-DD-…`) or **shop drawings**
(`SPAN-SD-…`) — reinforcement sheets, PT cable sheets, punching, beams — plus the **Drawings module of
the CRM** (submittals, take-off, cost, revisions) and its **standalone Python twin**.

Three products share one set of rules:

| product | where | what |
|---|---|---|
| Node generator | `shopdrawings/` (`cli.mjs`, `lib/*.mjs`) | the reference implementation, zero dependencies, Node ≥ 22 |
| CRM Drawings module | `server/drawings.js`, `server/submittals.js`, `server/routes/drawings.js`, `public/views/drawings.js` | projects, levels, runs, alerts, submittals, take-off, cost, settings |
| Python version | `pydrawings/` (`pydrawings/*.py` line-by-line port, `app.py` one-file app with the CRM screens) | same sheets, same text, same files; parity tested against Node |

Read `references/RULES.md` before touching a drafting rule, `references/PROGRAM.md` before touching the
code, and `references/WORKFLOW-AR.md` / `references/RAM-FILE-FLOW-AR.md` (the office procedure, Arabic,
also served in the app under `/help/`) when the user asks how the office uses the program.

---

## 1. How to talk and work with the user

- **Reply in Egyptian Arabic, short and plain.** Technical names stay in English (DXF, RAM, T12@150,
  U-bar, PS, Rev). One question at a time, options spelled out. The user is the design engineer and
  the owner of the office rules: when they correct a rule, the correction wins over anything written
  here or in the code — apply it, then record it in `references/RULES.md` with its reason.
- **Screenshots are bug reports.** When the user sends a picture of a sheet ("ليه الرجل دي ناحية
  اليمين؟", "ليه كاتب 200 والرام فيه 210؟"), find the exact entity in the DXF (render the sheet with
  `scripts/render_dxf.py`, zoom on the spot), find the rule in the code that produced it, fix it for
  every sheet and every project — not only that spot — and show a before / after zoom.
- **Never say "fixed" without a check.** Say exactly what was verified: tests run and their counts,
  ezdxf audit, rendered zooms looked at, which real model it was regenerated on. Say what could not
  be checked (RAM and AutoCAD are not available in the sandbox; the DXF is checked with ezdxf and
  rendered images only).
- **Both versions move together.** A rule changed in `shopdrawings/lib/*.mjs` is ported the same day
  to `pydrawings/pydrawings/*.py` (same function, same numbers, same strings), the Node parity
  reference is regenerated and the Python parity test passes again. A change in the CRM module
  (route, screen, string) is mirrored in `pydrawings/app.py` where the app has that feature.
- **Project files are proprietary.** The user's DWG / DXF / CPT / JSON of real projects (Majd, Roaya,
  Tahliyah, south tower…) and the licensed PT Suite `.py` go in the scratchpad only — never into the
  repository, never into a PR, never into a skill. Only synthetic samples are committed.
- **Deliverables**, sent as files (SendUserFile or the file tool at hand), never only described:
  - a generated package: the ZIP of the run (`dxf/`, `preview/`, `schedules/`, the package DXF,
    `REPORT.md`, `quantities.json`…) plus two or three rendered PNG zooms of what changed;
  - a program change: the repo zip (`SPANTECH_PT_SUITE_PROGRAM.zip`) and / or
    `PYDRAWINGS_PYTHON_VERSION.zip`, after tests, commit and push; the PR body updated;
  - a short Arabic summary: what changed, what was checked, what the user should look at in AutoCAD.
- **Do not ship what you know is wrong.** A blocked run (punching / beam alert), a `NaN` in a
  schedule, upside-down text, a bar leg outside the slab: fix or say so, never "done".
- End every answer with what you need from the user, if anything.

---

## 2. The office drafting convention (the rules the engineer fixed — do not break them)

The full list with reasons and the code location is `references/RULES.md`. The ones that were
corrected by the engineer during development, and therefore matter most:

**Reading direction — the reader stands at the RIGHT edge of the sheet** (as AutoCAD renders it):
horizontal writing reads left → right, vertical writing reads **bottom → top**. This applies to bar
call-outs, lengths and DIMENSION text alike. Any text rotation in (90.5°, 270.5°] is turned 180° with
its anchor mirrored; DIMENSION entities carry no text-turn (group 53). No text ever reads upside down.
(The first implementation put the reader at the left edge; the engineer corrected it.)

**Bar legs follow the engineering convention read from that same position:** a *horizontal* bottom
bar's legs point **up**, a top bar's **down**; a *vertical* bottom bar's legs point **left**, a top
bar's **right**. (`legSide` in `design.mjs` / `leg_side` in `design.py`.)

**Every drawn bar is ONE continuous polyline** — run, 90° rises of a drop bar, the L leg into an edge
beam, the U ends (leg + 500 back) and both legs of a hairpin are vertices of the same LWPOLYLINE
(constant width 20 model mm). A U-bar is one line, never three; the CAD user picks a bar in one click.

**Call-out above the bar, length under it, in the reading direction**, both starting at the same
point: `T12-150 (B)` and `L=5200`. On a vertical bar: the call-out on its **left**, the length on its
**right**.

**Every drawn bar carries a distribution dimension** (a real DIMENSION, style `DIM100`, no extension
lines) with the **dot** where the bar crosses it; as wide as the group (count × spacing, at least the
spacing or a metre); the text is placed past the end when the dimension is shorter than the text.

**Cable sheets write RAM's own profile figures.** At every high / low point the value **exactly as
entered in RAM Concept**, in the model's own reference (above soffit / below surface / mid-depth), no
chair drop, no rounding, no conversion — the drawing must read like the model. The old chair heights
(CGS − 10, rounded to 5) are only behind `spec.cables.figures: 'chair'`. Anchor spacing is dimensioned
halfway between the anchors and the tag blocks, never over the tags. No tendon sections.

**Placement rules the engineer checks by eye:** the slab tag is one boxed two-line label
(`POST TENSION SLAB` / `250 mm`) at a clear spot; drops on the framing plan read `THK=400` in their
lower-left corner with their two sizes dimensioned inside; beams are named **beside** them, once per
span between supports, sizes to the nearest 50 mm with no decimals, the schedule on the framing plan
(no separate beam sheet); columns are solid grey with **no id text**; openings are crossed and never
labelled; pour strips carry their name only; two columns closer than 500 mm are **one** support with
one group each way; a drop bar next to an edge or an opening has **no leg outside the slab**; bars
**never run into an opening** (they stop with a U); nothing is drawn outside the slab; **no bottom
detail strip by default** — the plan takes the whole sheet height; a body taller than wide is turned
90° so its long side lies along the landscape sheet.

---

## 3. Running things

```bash
# Node generator (reference)
node shopdrawings/cli.mjs --input SLAB.cpt --out ./design --mode design --level "1ST FLOOR" --level-id L01 --config project.json
node shopdrawings/cli.mjs --input SLAB.cpt --out ./shop   --mode shop   --level "1ST FLOOR"
node shopdrawings/cli.mjs --input STRUCTURAL.dxf --out ./package --config project.json     # shop from the G.A.
npm run shopdrawings:sample                                                                # bundled demo

# Python version (same flags, same files)
cd pydrawings && python3 -m pydrawings --input SLAB.cpt --out ./design --mode design --level "1ST FLOOR"
cd pydrawings && python3 app.py [--port 8765 --data ./data --no-browser]                   # the CRM screens, one file

# CRM
npm start            # then the Drawings module (لوحات التسليح) in the app; help at /help/ram-drawings-workflow.html

# tests
npm test                                                     # 155 tests (38 shopdrawings + 18 drawings + CRM)
cd pydrawings && python3 -m unittest discover -s tests -t .  # 62 tests incl. Node parity (needs node) and the app
```

`--config` takes `{ "meta": {...}, "spec": {...} }`; every `spec` key and its default is `DEFAULT_SPEC`
in `shopdrawings/lib/rebar.mjs` (mirrored in `rebar.py`) plus the RAM-specific keys listed in
`references/PROGRAM.md`. Never guess a number: if the model lacks it, the generator prints an
assumption on every sheet — read them (§5.1 of `WORKFLOW-AR.md` explains each one).

---

## 4. Verifying before you deliver (do all of it)

1. **Tests both sides green** (counts above). A parity failure after a rule change usually means the
   stored Node reference is stale — regenerate it (see PROGRAM.md → Parity) only after you have
   confirmed the Node output itself is right.
2. **ezdxf audit zero errors** on every written DXF (`ezdxf.recover.readfile` + `auditor`; the Python
   test suite does this when ezdxf is installed).
3. **Look at it.** Render the changed sheet with the skill's `scripts/render_dxf.py`: `python3 <skill>/scripts/render_dxf.py <sheet>.dxf Model out.png 4000`
   and zoom with a window (`xmin,ymin,xmax,ymax` as the 6th argument) on the bar, text or figure in
   question. Check by eye against §2 and the checklist in `WORKFLOW-AR.md` §5: reading direction, legs,
   one-line bars, dots on dimensions, no overlap, no text upside down, drawn length = written length.
4. **Regenerate the real model the user is working on** (kept in the scratchpad) in the mode they use
   and compare `quantities.json` / sheet count / assumptions with the previous run; explain every
   difference.
5. **Docs follow the code**: `shopdrawings/README.md`, `pydrawings/README.md`,
   `docs/RAM-DRAWINGS-WORKFLOW.md` (then regenerate `public/help/ram-drawings-workflow.html` with
   the skill's `scripts/md2help.py` run from the repo root: `python3 <skill>/scripts/md2help.py docs/RAM-DRAWINGS-WORKFLOW.md`; in the repo the skill is at `.claude/skills/spantech-drawings/`), the PR body, and
   `references/RULES.md` of this skill.

---

## 5. Changing a rule — the procedure

1. Reproduce on a real or synthetic model; render the spot; name the rule and where it lives
   (`references/PROGRAM.md` has the module map: design rules in `design.mjs`, shop sheets and cables in
   `sheets.mjs`, the shared reinforcement defaults in `rebar.mjs`, text / dimension normalisation in
   `canvas.mjs`, DXF encoding in `dxf-writer.mjs`, RAM reading in `ram-concept.mjs`).
2. Change the Node module first; update or add a `node:test` assertion in `test/shopdrawings.test.js`
   that would have caught the old behaviour.
3. Port the same change to the Python module (same function name in snake_case, same numbers and
   strings — `PORTING.md` rules); update `pydrawings/tests/*`; regenerate the Node parity reference.
4. If the rule has a switch (mesh, rotate, beamDesign, cables.figures…), expose it the same way in
   the CRM settings / project / run dialog **and** in `app.py` (DRAWING_DEFAULTS, the settings form,
   the strings), with the Arabic and English labels.
5. Run §4. Commit with a message that states the rule in one line; push; update the PR body; send the
   deliverables and the zooms.

---

## 6. Where the knowledge lives (progressive disclosure)

- `references/RULES.md` — every drafting and design rule (D1..D12, cables, punching, beams, sheets,
  layers, reading direction) with the reason and the code location. Read before changing a rule.
- `references/PROGRAM.md` — architecture, module map (Node ↔ Python), spec / meta keys, outputs,
  CRM routes and tables, `app.py` internals, tests and parity, scratchpad conventions, sandbox
  limits. Read before changing code.
- `references/WORKFLOW-AR.md` — the office procedure in Arabic (RAM checklist, registering, batch
  generation, cables, punching / beam alerts and decisions, review checklist, AutoCAD, editor,
  frame, beam design, submittals, take-off, CLI, common problems). Quote it when the user asks
  "how do I…".
- `references/RAM-FILE-FLOW-AR.md` — the line of march of one RAM file through twelve stations, who
  does what, printable checklist.
- `scripts/render_dxf.py` — DXF → PNG (ezdxf + matplotlib), optional window, for visual checks.
- `scripts/md2help.py` — Markdown → the app's help HTML (run from the repo root).
