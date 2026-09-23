# Career Quest

FastAPI backend and connected React/Vite frontend for the Career Quest employee
development project. The backend implements the four steps in
`Person1_Backend_Prompts.md`; `frontend/` provides employee profiles,
recommendations, activity completion, HR dashboards, and data imports. The
original three task documents are unchanged.

The supplied dataset is bundled in `data/`: **200 employees, 60 skills, 32 role
profiles, 40 activities, and 2,743 history records**. It is synthetic, as documented
in its README. The smaller `sample_data/` directory contains separate invented
fixtures for isolated tests. `/health` reports `synthetic_data: true` for both.

## Run on Windows / PowerShell

Clone the repository and start the backend from its root (tested with Python 3.14):

```powershell
git clone https://github.com/BAITC-Hacks/hack-7168a80e-nuvexa.git
cd hack-7168a80e-nuvexa
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

If you already cloned the repository, open a terminal in its root and skip the
clone commands. No PowerShell activation script is needed. If `.venv` already
exists, skip its creation. For runtime dependencies alone, use `requirements.txt`
instead.

Open [interactive API docs](http://127.0.0.1:8000/docs) or
[health](http://127.0.0.1:8000/health). The machine-readable contract is
`http://127.0.0.1:8000/openapi.json`. Use **one worker**: all data is intentionally
held in memory, and imports/completions reset when the process restarts.

On macOS/Linux use `.venv/bin/python` in place of `.\.venv\Scripts\python.exe`.

## Run the frontend

Keep the backend terminal running. Open a second PowerShell terminal in the
repository root:

```powershell
cd frontend
Copy-Item .env.example .env
npm ci
npm run dev
```

Open [Career Quest](http://127.0.0.1:5173). The frontend was tested with Node.js 24
and npm 11. The copied `.env` configures the local backend:

```dotenv
VITE_USE_MOCK_DATA=false
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Skip `Copy-Item` if you already have a configured `frontend/.env`.
Restart Vite after changing these values. The home page opens employee `E0001`;
`/employee/E0002` opens another employee. Optionally set
`VITE_DEFAULT_EMPLOYEE_ID` to change the home-page employee.

Development and preview both bind to `127.0.0.1:5173`, which matches the backend's
default CORS configuration. If that port is occupied, Vite stops instead of
silently choosing another port. Stop the existing frontend before starting a
second development or preview server.

The frontend loads live profiles, recommendations, the skill catalog, and HR
data. Completing an activity refreshes the profile and recommendations. Imports
send employee JSON or history JSON/CSV to the same backend. Backend changes are
held in memory and reset when it restarts; they do not rewrite the dataset files.
The supplied dataset is synthetic, but this is still live API mode. For the
separate standalone mock demo, set `VITE_USE_MOCK_DATA=true`; its default employee
is `EMP_001`. See [frontend setup](frontend/README.md).

## Dataset and configuration

The committed `data/` directory contains the four supplied synthetic data files:

- `employees.json`: object with `meta` and `employees`.
- `skills.json`: object with `meta`, `proficiency_scale`, `skills`, and `role_profiles`.
- `events.json`: object with `meta` and `events`.
- `activity_history.csv`: the ten columns specified in the task documents.

The three supplied READMEs (`README.md`, `README.ru.md`, and `README.kz.md`) are
committed alongside them, for seven bundled files in total. The original source
files were preserved separately before adding `meta.synthetic: true` to the
working JSON copies. Employee, skill, event, and history records are preserved.
A fresh clone includes this dataset and needs no separate download.

The default is `data/` when that directory exists, otherwise `sample_data/`.
An incomplete `data/` directory fails startup with a missing-file error instead of
silently replacing real data with samples. To choose another directory, copy
`.env.example` to `.env` and set `DATA_DIR`. Relative paths resolve from the project
root. Existing environment variables take precedence over `.env`.

The evaluation date is deliberately fixed at **2026-10-01** in
`backend/config.py`, as required by the task. Both session eligibility and recorded
completion dates use it. Employee file skills are the assessment baseline at
`last_review_date`. The backend derives current skills by applying gains from
completed history dated after that review and on or before the evaluation date,
respecting each activity's skill caps. Reimporting a record rebuilds these values
from the baseline without applying the same gain twice.

The history schema has no completion timestamp: `date` means enrollment or
assignment for self-paced activities. Completed self-paced records dated after
the review establish that learning happened after the assessment; those dated on
or before it remain ambiguous and are left unapplied. History for employees
without a known review date is also left unapplied. Explicit API completions still
apply their gains once, including when the employee has no review date.
The supplied history repeats some
mandatory compliance activities although its README names only `EV_036` as
repeatable. These records are preserved; the API's repeatable-completion exception
remains `EV_036`.

## Optional NVIDIA explanations

The complete workflow runs without an API key, using deterministic explanations
in each employee's preferred language (`en`, `ru`, or `kk`). To enable NVIDIA:

1. Copy `.env.example` to `.env` if it does not exist.
2. Set `NVIDIA_API_KEY` to your inference API key locally. Keep it out of source control.
3. Keep `LLM_BASE_URL=https://integrate.api.nvidia.com/v1/` and select an available
   `LLM_MODEL` (default `meta/llama-3.1-8b-instruct`). Restart the server.

Live NVIDIA inference has not been tested with credentials. The integration uses
NVIDIA's documented
[chat-completions endpoint](https://docs.api.nvidia.com/nim/reference/llm-apis).
Another compatible provider can be configured using `LLM_BASE_URL`, `LLM_MODEL`,
and `LLM_API_KEY`; `LLM_API_KEY` takes precedence over `NVIDIA_API_KEY`.

The provider receives only activity/skill facts, numeric gaps, duration, and a
negative-participation count. Employee names and identifiers are not sent.
The LLM never selects activities, scores them, or changes employee skills. Three
explanations run concurrently with a hard timeout of at most six seconds each,
leaving room within the ten-second request budget. No retries are made. Errors,
empty responses, unsupported numeric literals, or insufficient explanation factors
fall back to templates. These checks are heuristics, not a proof of factual accuracy.
Leave the key empty when strictly deterministic wording is required.

## API handoff for the frontend

Set the frontend's `VITE_USE_MOCK_DATA=false` and
`VITE_API_BASE_URL=http://127.0.0.1:8000`. The default CORS
origins are `http://localhost:5173` and `http://127.0.0.1:5173`; change the
comma-separated `CORS_ORIGINS` environment variable for another local origin.
There is no `/api` prefix.

- `GET /employees/{id}` returns all employee fields plus `next_grade`,
  `skill_gaps` (`skill_id`, current/required levels, raw/weighted gap, `critical`),
  and `activity_history` with an `event_title` on each row.
- `GET /employees/{id}/recommendations` returns `{employee_id, recommendations}`.
  Each card has `event_id`, `title`, `rationale`, `score`, `closes_skills`,
  `critical`, `duration_hours`, and `format`. Optional `top_n` accepts 1–3.
- `POST /employees/{id}/activities/{event_id}/complete` requires no body. Returns
  `{employee_id, event_id, skills, recommendations}` with updated skills and fresh
  recommendation cards. Repeating a nonrecurring completion returns **409**;
  `EV_036` can be completed repeatedly. Completion records an existing activity;
  it does not restrict manual completion to the current recommendation list.
  The frontend refetches the profile after completion to update derived gaps and
  activity history as well as skills and recommendations.
- `GET /hr/skill-gaps` returns up to 15 rows of
  `{skill_id, skill_name, total_gap, employees_affected}`.
- `GET /hr/employees-without-recommendation` returns unranked
  `{employee_id, full_name, role, grade}` rows, ordered by identifier.
- `GET /hr/participation-stats` returns rows with `event_id`, `title`, all six
  status counts (`completed`, `declined`, `no_show`, `dropped`, `in_progress`,
  `overdue`), and `total`, ordered by total records descending.
- `GET /skills` returns catalog entries to resolve skill IDs into display names.
- `POST /data/import` accepts the forms described below.

Unknown employee/event IDs return **404**. Invalid input returns **422**. Error
responses include a readable `message` and `detail` (text or validation issues).
The frontend should display `message` first. An empty recommendation array is
normal for Lead employees, fully covered skills, missing next-grade profiles, or
employees with no useful eligible activity.

## Imports

Canonical JSON request (each item must contain the complete record schema):

```json
{"employees": [], "history": []}
```

At least one list must be nonempty. IDs are upsert keys: reimporting the same
employee or `record_id` replaces that record, without duplicates. Repeated IDs
inside one submitted batch are rejected. History must reference existing events
and either existing employees or employees in the same request. Unknown skill IDs
are rejected. A failed batch leaves all data unchanged. Employee imports replace
complete assessment snapshots; they are not partial patches. Imported employee
`skills` must represent the assessment at `last_review_date`, before later history
gains. Do not round-trip the API's derived `skills` as an assessment baseline,
because that would count the same learning again.

The connected frontend's upload/paste screen sends this envelope:

```json
{"type": "employees", "data": {"employees": []}}
```

Here `data` can be an employee array, a parsed dataset object with optional `meta`,
or the corresponding JSON string. For history, send a parsed record array using
`{"type":"history","data":[...]}`, or put the raw CSV text in `data`:

```json
{"type":"history","data":"record_id,employee_id,event_id,date,due_date,status,completion_pct,score,feedback_rating,assigned_by\nIMPORT_001,E0002,EV_009,2026-09-30,,in_progress,25,,,self\n"}
```

This is a JSON endpoint, not a multipart upload: the frontend reads the selected
file and sends its contents. CSV headers must match the exact order shown.
Blank due dates, scores, and feedback ratings become null. Fractional completion
percentages are supported. Importing eligible completed history updates derived
skills, gaps, and recommendations. Replacing a history record or assessment
recalculates them from the stored assessment baseline.

Success returns `employees_imported`, `history_imported`, and `message`. Counts
are accepted rows including replacements. Inputs are validated before either
employees or history changes.

## Recommendation rules

The target is the **next grade in the current role**, following
Junior → Middle → Senior → Lead. `career_goal` is retained as profile data but does
not override this rule. A gap is `max(0, required - current)`, with absent skills
treated as zero. Critical gaps count twice.

Eligibility requires matching role and grade, satisfied prerequisites, a
skill-building nonmandatory activity, no prior completion (except `EV_036`), and
a current/future session unless self-paced. Events that cannot close any gap are
excluded even if otherwise eligible.

Scoring sums actual capped gap reductions (critical gains count twice), subtracts
`1.5 × participation_penalty`, and adds a single `1.0` bonus when any critical gap
is fully resolved. The penalty counts each declined/no-show/dropped record on
**other** activities developing overlapping skills as `1.0`, plus `0.5` for each
low feedback rating (≤2) in those records. The factual negative-status count is
kept separate from low ratings in explanations. Useful activities may have
negative scores; these are relative rankings, not probabilities or ratings.
Ties use `event_id` for reproducibility. Completion applies the same skill caps
without ever reducing an employee's existing level.

## Verify and demo

Backend checks from the project root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check backend tests
```

Frontend checks from `frontend/`:

```powershell
npm test
npm run build
```

`npm test` uses Node's built-in test runner for the API/data adapter. To view the
production build locally, stop the Vite development server and run
`npm run preview`. Keep the backend running for live API mode.

Optional frontend-to-backend integration tests require
`CAREER_QUEST_TEST_API_URL` and mutate the selected backend's in-memory data. Use
a separate backend on port 18001; see the [frontend test instructions](frontend/README.md#test-and-build).
They are skipped by default so routine frontend tests leave the active demo alone.

Tests cover scoring/eligibility, schemas, full API flow, HR counts, imports,
duplicate/concurrent completions, malformed CSV, provider failures, language
fallbacks, and the concurrent explanation deadline. Provider tests use mocks and
do not consume API credits. `tests/test_history_reconciliation.py` checks derived
skills and safe reimports; `tests/test_supplied_dataset.py` runs regression checks
against the installed `data/` files. To run just those dataset checks:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_history_reconciliation.py tests/test_supplied_dataset.py
```

In `/docs`, read `E0001` (Kazakh) or `E0002` (Russian), then fetch that employee's
recommendations. Complete a returned nonrecurring activity and fetch the profile
and recommendations again to see the skill update. Repeat completion to see 409.
Read `E0050` for a Lead employee with no next grade, or `E0008` for English.

To use the small fixtures instead, set `DATA_DIR=sample_data` and restart. Those
fixtures use `EMP_001` through `EMP_006`; their demo scenarios are documented in
`sample_data/README.md`. They are separate from the supplied `E0001`–`E0200` IDs.

## Implementation and limits

`backend/models.py` defines dataset schemas. `data_store.py` validates and indexes
JSON plus a pandas history DataFrame; mutations are protected by a process-local
lock. `recommendation_engine.py` contains pure scoring functions with no network
calls. `rationale_generator.py` supplies optional HTTP-based explanation text.
`main.py` owns the application lifespan, shared dependencies, and routes;
`api_models.py` defines the public contracts.

This is the requested hackathon backend, with no database persistence,
authentication, employee/HR authorization, production rate limits, or deployed
service. Keep the default loopback binding for local work. Production deployment
requires those controls and a shared transactional datastore. The supplied
dataset loads locally; live inference still needs verification with API credentials.
