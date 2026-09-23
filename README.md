# Career Quest frontend

React and Vite frontend for the Career Quest employee development demo. The app includes an employee profile with skill progress and activity recommendations, an aggregate HR dashboard, and an import form for employee and activity data.

## Run locally

```sh
npm install
npm run dev
```

Vite prints the local development URL after startup. Create a `.env` file from `.env.example` to configure the API connection. The app uses the built-in demo data by default. To use the FastAPI service, set `VITE_USE_MOCK_DATA=false` and `VITE_API_BASE_URL` to the backend URL. Restart Vite after changing environment variables.

## Pages

- `/` — employee profile and recommendations (demo employee `EMP_001`)
- `/employee/:id` — open a specific employee profile
- `/hr` — skill gaps, employees without a recommendation, and participation totals
- `/import` — validate and submit employee JSON or activity history JSON/CSV

The import form sends employee data as `{ "type": "employees", "employees": [...] }` and activity data as `{ "type": "activity_history", "activity_history": [...] }` to `POST /data/import`. Confirm that the backend accepts this payload shape before connecting a different API implementation.

## Build

```sh
npm run build
npm run preview
```
