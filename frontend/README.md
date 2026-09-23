# Career Quest frontend

React/Vite frontend connected to the Career Quest FastAPI backend. It includes
employee profiles, skill progress, activity recommendations and completion, HR
dashboards, and employee/history imports.

## Run locally

Open the project folder and start the backend from its root in one PowerShell
terminal (tested with Python 3.14):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Skip any setup already completed. See the [project README](../README.md)
for backend configuration. Keep this terminal running. Open a second terminal in
the repository root:

```powershell
cd frontend
Copy-Item .env.example .env
npm ci
npm run dev
```

Open [Career Quest](http://127.0.0.1:5173). The frontend was tested with Node.js 24
and npm 11. Vite development and preview both use
`127.0.0.1:5173` with a strict port, matching the backend's default CORS origins.
If the port is occupied, stop the existing frontend before starting another.

Skip `Copy-Item` if you already have a configured `.env`. The copied example
configures live API mode:

```dotenv
VITE_USE_MOCK_DATA=false
VITE_API_BASE_URL=http://127.0.0.1:8000
# Optional home-page employee override:
# VITE_DEFAULT_EMPLOYEE_ID=E0001
```

Restart Vite after changing environment variables. The API URL has no `/api`
prefix. [API docs](http://127.0.0.1:8000/docs) describe the available routes.

The supplied synthetic dataset is served by the real backend; it does not require
mock mode. Set `VITE_USE_MOCK_DATA=true` only to run the separate standalone mock
demo without a backend. The default employee is `E0001` in API mode and `EMP_001`
in mock mode. If the backend uses `sample_data/`, set
`VITE_DEFAULT_EMPLOYEE_ID=EMP_001` while keeping mock mode disabled.

## Pages and API behavior

- `/` opens the default employee's profile and recommendations.
- `/employee/:id` opens a specific employee, for example `/employee/E0002`.
- `/hr` shows skill gaps, employees without recommendations, and participation.
- `/import` validates and submits employee JSON or activity history JSON/CSV.

Skill names come from `GET /skills`. Completing an activity posts to
`/employees/{id}/activities/{event_id}/complete`; the response includes updated
skills and recommendations, and the frontend refetches the profile to refresh
gaps and history. Empty recommendation lists are valid.

The import page sends a JSON envelope to `POST /data/import`:

```json
{"type":"employees","data":[...]}
```

History imports use `{"type":"history","data":[...]}` for JSON records, or
`{"type":"history","data":"raw CSV text"}` for CSV files. These examples
show the envelope only; each record must contain the complete backend schema.
Success counts come from `employees_imported` and `history_imported`. The API
upserts complete records by ID and rejects invalid batches without partial writes.
See [import details](../README.md#imports) for schemas and assessment-skill rules.

Completions and imports are held in backend memory and reset when that process
restarts. They do not rewrite the supplied dataset files.

## Test and build

From `frontend/`:

```powershell
npm test
npm run build
```

Tests use Node's built-in test runner. To inspect the production build, stop the
development server and run `npm run preview`, then open
`http://127.0.0.1:5173`. Keep the backend running in API mode.

The optional backend integration test is skipped unless
`CAREER_QUEST_TEST_API_URL` is set. It completes activities and imports records,
so run it against a separate backend process instead of your active demo. In an
additional terminal at the project root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 18001
```

In a test terminal at `frontend/`:

```powershell
$env:CAREER_QUEST_TEST_API_URL = 'http://127.0.0.1:18001'
npm test
Remove-Item Env:CAREER_QUEST_TEST_API_URL
```

Stop the backend on port 18001 after testing. Its in-memory changes are isolated
from the demo server on port 8000.

From the project root, run backend tests with:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

For a manual check, open an employee, complete a recommended activity, and verify
the refreshed skills and recommendations. Visit `/hr` to check that all dashboard
sections load. Importing records changes the current in-memory backend state.
