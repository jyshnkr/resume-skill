# Fit check and score

The model fills one row per requirement; `scripts/fit_score.py` does the arithmetic, so the same rows always give the same score.

## Rows

Read the posting (`references/workflow.md`), then write `ROWS.json`: `{"kind": "posting", "rows": [{"requirement": "Java 11+", "tier": "required", "status": "met", "evidence": "b005"}], "flags": [], "axes": {"skills": 0.8, "level": 1, "domain": 0.5, "location": 1, "rate": null}}`.
`tier` is required or preferred. `status` is met (a bank bullet or the profile shows it), partly (adjacent or years not stated) or not. Evidence is a bank id or a profile line, never a guess.
Run `python3 scripts/fit_score.py ROWS.json --slug SLUG --write`. It prints the result and writes `fit.json` and the fit card `fit.html` to `out/SLUG/`; `save.py` moves them into the job folder after the user's OK.
Reply with its text line, at most 3 flags, then the table. A recruiter introduction, or fewer than 3 rows: no score, say why.

## Arithmetic (settings `fit` hold the numbers)

- tier percent = (met + 0.5 x partly) / rows in the tier x 100
- score percent = 0.7 x required + 0.3 x preferred; with only one tier, that tier's percent
- score 5 at 90 or more, 4 at 75, 3 at 60, 2 at 40, otherwise 1 (an edge counts in the higher score)
- lean: 5 or 4 apply, 3 your call, 2 or 1 skip. A lean is advice; the user decides.

## Worked examples (worked by hand; the tests read these blocks)

```json fit-example
{"name":"A all met","work":"required 4/4 = 100, preferred 2/2 = 100; 100","rows":[["required","met"],["required","met"],["required","met"],["required","met"],["preferred","met"],["preferred","met"]],"expect":{"pct":100.0,"score":5,"lean":"apply","required":{"met":4,"partly":0,"total":4},"preferred":{"met":2,"partly":0,"total":2}}}
```
```json fit-example
{"name":"B mixed","work":"required (3 + 0.5)/4 = 87.5, preferred 1/2 = 50; 0.7 x 87.5 + 0.3 x 50 = 76.25","rows":[["required","met"],["required","met"],["required","met"],["required","partly"],["preferred","met"],["preferred","not"]],"expect":{"pct":76.25,"score":4,"lean":"apply","required":{"met":3,"partly":1,"total":4},"preferred":{"met":1,"partly":0,"total":2}}}
```
```json fit-example
{"name":"C edge 90","work":"required only: (8 + 1)/10 = 90.0","rows":[["required","met"],["required","met"],["required","met"],["required","met"],["required","met"],["required","met"],["required","met"],["required","met"],["required","partly"],["required","partly"]],"expect":{"pct":90.0,"score":5,"lean":"apply","required":{"met":8,"partly":2,"total":10},"preferred":{"met":0,"partly":0,"total":0}}}
```
```json fit-example
{"name":"D edge 75","work":"required only: (2 + 1)/4 = 75.0","rows":[["required","met"],["required","met"],["required","partly"],["required","partly"]],"expect":{"pct":75.0,"score":4,"lean":"apply","required":{"met":2,"partly":2,"total":4},"preferred":{"met":0,"partly":0,"total":0}}}
```
```json fit-example
{"name":"E edge 60","work":"required only: 3/5 = 60.0","rows":[["required","met"],["required","met"],["required","met"],["required","not"],["required","not"]],"expect":{"pct":60.0,"score":3,"lean":"your call","required":{"met":3,"partly":0,"total":5},"preferred":{"met":0,"partly":0,"total":0}}}
```
```json fit-example
{"name":"F under 60","work":"required only: 4/7 = 57.14","rows":[["required","met"],["required","met"],["required","met"],["required","met"],["required","not"],["required","not"],["required","not"]],"expect":{"pct":57.14,"score":2,"lean":"skip","required":{"met":4,"partly":0,"total":7},"preferred":{"met":0,"partly":0,"total":0}}}
```
```json fit-example
{"name":"G edge 40","work":"required only: 2/5 = 40.0","rows":[["required","met"],["required","met"],["required","not"],["required","not"],["required","not"]],"expect":{"pct":40.0,"score":2,"lean":"skip","required":{"met":2,"partly":0,"total":5},"preferred":{"met":0,"partly":0,"total":0}}}
```
```json fit-example
{"name":"H poor","work":"required 1/5 = 20, preferred 0/1 = 0; 0.7 x 20 + 0.3 x 0 = 14.0","rows":[["required","met"],["required","not"],["required","not"],["required","not"],["required","not"],["preferred","not"]],"expect":{"pct":14.0,"score":1,"lean":"skip","required":{"met":1,"partly":0,"total":5},"preferred":{"met":0,"partly":0,"total":1}}}
```
```json fit-example
{"name":"I preferred only","work":"preferred only: 3/3 = 100.0","rows":[["preferred","met"],["preferred","met"],["preferred","met"]],"expect":{"pct":100.0,"score":5,"lean":"apply","required":{"met":0,"partly":0,"total":0},"preferred":{"met":3,"partly":0,"total":3}}}
```
```json fit-example
{"name":"J too few rows","work":"2 rows: no score","rows":[["required","met"],["required","met"]],"expect":{"score":null}}
```
