# Synthetic demo data

These files are invented fixtures for isolated tests and small demonstrations.
The supplied synthetic dataset is installed separately in `data/`, which the
application loads by default. Select `DATA_DIR=sample_data` to use these fixtures.
They are **not** the Halyk Bank hackathon
starter dataset, real employee records, official promotion requirements, or real
event bookings. Every JSON file declares `meta.synthetic: true` and the snapshot
date `2026-10-01`. The CSV uses the exact activity header and cannot carry metadata;
it belongs to this same synthetic fixture set.

The files contain six fictional employees, five skills, four Data Analyst grade
profiles in Junior → Middle → Senior → Lead order, twelve activities, and fourteen
history records. Profile skill values represent each employee's assessment at
`last_review_date`. Loading the fixtures applies gains from completed history
after that review through the fixed snapshot date. Earlier or same-day records
are already covered by the assessment and are not added again.

## Demo scenarios

- `EMP_001` (English, Middle): communication has a gap of two to Senior after the
  September 17 `EV_036` completion raises its assessed level from one to two, with
  declined, no-show, and dropped history for similar communication activities.
  SQL and Python each have a smaller, critical gap of one. SQL activity `EV_001`
  and Python activity `EV_002` can improve this profile. Completing a recommended
  nonrecurring activity changes the skills and subsequent recommendations.
- `EMP_002` (Kazakh, Junior): hired one month before the snapshot, with only
  mandatory `EV_004` in history. Useful for checking recommendations without a
  participation penalty.
- `EMP_003` (Russian, Senior): only one leadership point remains before the Lead
  profile. `EV_011` can close it; the existing in-progress record is not a prior
  completion and must not exclude the activity under the supplied eligibility rules.
- `EMP_004` (English, Lead): no next grade and therefore no recommendations.
- `EMP_005` (Russian, Junior): mixed gaps, in-progress learning, and an overdue
  mandatory activity for HR status counts.
- `EMP_006` (Kazakh, Middle): multiple gaps, prior SQL completion, and communication
  participation history for a second non-English demonstration.

## Event edge cases

- `EV_004`: mandatory and has no developed skills; never a recommendation.
- `EV_005`: requires Python level four, which `EMP_001` has not reached.
- `EV_006`: SQL gain is capped at level two; cannot close `EMP_001`'s SQL gap or
  lower their existing level three proficiency.
- `EV_007`: only a past session (`2026-09-15`); expired at the snapshot.
- `EV_008`: already completed by `EMP_001`; excluded from their recommendations.
- `EV_036`: repeatable club, already completed by `EMP_001`; remains eligible
  despite that completion if all other filters pass. Its participation penalty
  can still affect ranking. Its first session is exactly on the snapshot date.
- `EV_002`, `EV_006`, `EV_011`: self-paced activities with no session dates.

Future dated activities use October/November 2026. History dates may predate the
currently listed sessions because events may have had earlier runs. CSV blank
`due_date`, `score`, and `feedback_rating` cells represent absent optional values.

Use this directory only for local demonstrations and tests. Keep its fixture IDs
and provenance separate from the supplied dataset in `data/`.
