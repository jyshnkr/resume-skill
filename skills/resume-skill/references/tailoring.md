# Tailoring

## Choose
Start from the version and change only what the posting needs (rule 33). Swap in a better-matching bank bullet; never one held back in `out/preflight.json`. Swaps and edits come only from approved rows: a `"status": "candidate"` row is a draft waiting for the user's pick and never goes into a resume without the user's OK; approving one is a `save.py` plan that sets it approved (remove `status` or set "approved") and places it. Put the best match first in each role (rule 35). Reorder skills lines; add an item only from another version or `profile.md` (rules 26, 27). Keep job titles and dates as in the version (rule 47).

## Summary
Three sentences; every claim traces to a bullet in the same resume (rules 23 to 25). Check it with `python3 scripts/check.py --summary "text"`.

## Reword (rare)
Keep at least half of the bank bullet's words; less is a new bullet, which this skill does not write. Show before and after and one line on why it stays accurate (rule 48). A platform bracket only per `references/brackets.md`.

## Check loop
For each bullet: `python3 scripts/check.py --leads "Cut Ended Reduced" "bullet text"`, where the leads are the first words of the other bullets in the same resume. Use `--json` to read the result. FAIL: fix, then re-run. WARN and NOTE: name them in the reply. Then `python3 scripts/check.py --stack tailoring:SLUG` for the stack note (rule 67); it never fails.

## Write the draft
The draft is a tailoring file with full bullet text: `{"slug","base","status":"draft","posting","client","summary","roles":[{"title","location","dates","sub","bullets":[{"id","text","override":false}]}],"education","skills","projects","doubts":[]}`. Write it to `DATA/out/SLUG/tailoring.json` (DATA is the path `where.py` printed; copy the shape of `jobs/acme-backend/tailoring.json` in the example data). `override` is true only for a reworded bullet, which also carries `"why"`: one line on why it stays accurate (a platform bracket alone needs none).

## Build
`python3 scripts/export.py file:DATA/out/SLUG/tailoring.json DATA/out/SLUG --label SLUG` (after saving, the target is `tailoring:SLUG`). OUTDIR must be outside the skill folder. Exit 0 within the page cap, 1 over it, 2 pages not checked: say so and never call the count checked.

## Sent copies
A tailoring with status submitted is frozen: no edit, and no bank change flows into it. Make a new tailoring (rule 34).
