# Fit check and score

<!-- Slice 6 owns "Worked examples" below: the numbers are worked by hand, and tests/test_fit_score.py reads them from here. -->

## Worked examples

The model fills one row per requirement: `tier` (required or preferred) and `status` (met, partly or not).
The script only does the arithmetic:

- tier percent = (met + 0.5 x partly) / rows in that tier x 100
- score percent = (70 x required percent + 30 x preferred percent) / 100; if only one tier has rows, that tier's percent is the score percent
- score 5 at 90 or more, 4 at 75 or more, 3 at 60 or more, 2 at 40 or more, otherwise 1 (the edges count in the higher score)
- lean: 5 or 4 = apply, 3 = your call, 2 or 1 = skip
- fewer than 3 rows, or a recruiter introduction: no score

Example A. Everything met: 4 of 4 required, 2 of 2 preferred. 100 and 100 give 100 percent: score 5, apply.

```json fit-example
{"name": "A all met", "rows": [["required","met"],["required","met"],["required","met"],["required","met"],["preferred","met"],["preferred","met"]],
 "expect": {"pct": 100.0, "score": 5, "lean": "apply", "required": {"met": 4, "partly": 0, "total": 4}, "preferred": {"met": 2, "partly": 0, "total": 2}}}
```

Example B. Required: 3 met, 1 partly of 4 = (3 + 0.5) / 4 = 87.5. Preferred: 1 met, 1 not of 2 = 50.
Score = 0.7 x 87.5 + 0.3 x 50 = 61.25 + 15 = 76.25: score 4, apply.

```json fit-example
{"name": "B mixed", "rows": [["required","met"],["required","met"],["required","met"],["required","partly"],["preferred","met"],["preferred","not"]],
 "expect": {"pct": 76.25, "score": 4, "lean": "apply", "required": {"met": 3, "partly": 1, "total": 4}, "preferred": {"met": 1, "partly": 0, "total": 2}}}
```

Example C. Edge at 90. Only required rows: 8 met, 2 partly of 10 = (8 + 1) / 10 = 90.0: score 5 (the edge counts in the higher score).

```json fit-example
{"name": "C edge 90", "rows": [["required","met"],["required","met"],["required","met"],["required","met"],["required","met"],["required","met"],["required","met"],["required","met"],["required","partly"],["required","partly"]],
 "expect": {"pct": 90.0, "score": 5, "lean": "apply", "required": {"met": 8, "partly": 2, "total": 10}, "preferred": {"met": 0, "partly": 0, "total": 0}}}
```

Example D. Edge at 75. 4 required rows: 2 met, 2 partly = (2 + 1) / 4 = 75.0: score 4.

```json fit-example
{"name": "D edge 75", "rows": [["required","met"],["required","met"],["required","partly"],["required","partly"]],
 "expect": {"pct": 75.0, "score": 4, "lean": "apply", "required": {"met": 2, "partly": 2, "total": 4}, "preferred": {"met": 0, "partly": 0, "total": 0}}}
```

Example E. Edge at 60. 5 required rows, 3 met, 2 not = 60.0: score 3, your call.

```json fit-example
{"name": "E edge 60", "rows": [["required","met"],["required","met"],["required","met"],["required","not"],["required","not"]],
 "expect": {"pct": 60.0, "score": 3, "lean": "your call", "required": {"met": 3, "partly": 0, "total": 5}, "preferred": {"met": 0, "partly": 0, "total": 0}}}
```

Example F. Just under 60. 7 required rows, 4 met, 3 not = 57.142857...: score 2, skip.

```json fit-example
{"name": "F under 60", "rows": [["required","met"],["required","met"],["required","met"],["required","met"],["required","not"],["required","not"],["required","not"]],
 "expect": {"pct": 57.14, "score": 2, "lean": "skip", "required": {"met": 4, "partly": 0, "total": 7}, "preferred": {"met": 0, "partly": 0, "total": 0}}}
```

Example G. Edge at 40. 5 required rows, 2 met, 3 not = 40.0: score 2. With 1 met of 5 (20.0): score 1.

```json fit-example
{"name": "G edge 40", "rows": [["required","met"],["required","met"],["required","not"],["required","not"],["required","not"]],
 "expect": {"pct": 40.0, "score": 2, "lean": "skip", "required": {"met": 2, "partly": 0, "total": 5}, "preferred": {"met": 0, "partly": 0, "total": 0}}}
```

```json fit-example
{"name": "H poor", "rows": [["required","met"],["required","not"],["required","not"],["required","not"],["required","not"],["preferred","not"]],
 "expect": {"pct": 14.0, "score": 1, "lean": "skip", "required": {"met": 1, "partly": 0, "total": 5}, "preferred": {"met": 0, "partly": 0, "total": 1}}}
```

(Example H: required 1 of 5 = 20, preferred 0 of 1 = 0; 0.7 x 20 + 0.3 x 0 = 14.0.)

Example I. Only preferred rows: 3 met of 3 = 100.0: score 5. Two rows only: no score.

```json fit-example
{"name": "I preferred only", "rows": [["preferred","met"],["preferred","met"],["preferred","met"]],
 "expect": {"pct": 100.0, "score": 5, "lean": "apply", "required": {"met": 0, "partly": 0, "total": 0}, "preferred": {"met": 3, "partly": 0, "total": 3}}}
```

```json fit-example
{"name": "J too few rows", "rows": [["required","met"],["required","met"]],
 "expect": {"score": null}}
```
