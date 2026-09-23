# نفر ۲ — فرانت‌اند / رابط کاربری
## پرامپت‌های Codex، قدم‌به‌قدم

> ترتیب مهم است: هر پرامپت مستقیماً روی کدی که پرامپت قبلی ساخته ادامه می‌دهد.
> پرامپت‌ها را دقیقاً به همین ترتیب (Step 1 → Step 2 → Step 3 → Step 4) در Codex کپی کنید — هرکدام را در یک پیام/تسک جدا بفرستید، نه همه با هم.
> **استک فرض‌شده:** React (Vite). اگر استک دیگری انتخاب کردید، فقط عبارت "React (Vite)" را با استک خودتان جایگزین کنید.
> این پرامپت‌ها از داده‌ی mock استفاده می‌کنند تا منتظر نفر ۱ (بک‌اند) نمانید — در فاز ۴ (یکپارچه‌سازی) فقط منبع داده را با API واقعی عوض می‌کنید.

---

## Step 1 — Setup و data client

```
Set up a React (Vite) frontend for "Career Quest", an employee development platform. 
Create:

1. A minimal API client module `api.js` with typed fetch wrappers for:
   - getEmployee(employeeId)
   - getRecommendations(employeeId)
   - completeActivity(employeeId, eventId)
   - getHrSkillGaps()
   - getHrEmployeesWithoutRecommendation()
   - getHrParticipationStats()
   - importData(payload)
   Base URL from an environment variable (VITE_API_BASE_URL), with a sensible localhost default.
   Every function should handle non-200 responses by throwing a typed error with the response 
   body's message, and support an AbortController-based timeout of ~12 seconds (the backend's 
   own budget is 10s for recommendations).

2. A `MockData.js` file with realistic fake responses matching the exact shape the real API 
   will return (see the shapes below), so I can build every screen without waiting for the 
   backend:
   - Employee: {employee_id, full_name, department, role, grade, tenure_months, 
     preferred_language, skills: {skill_id: level}, activity_history: [...]}
   - Recommendations: {employee_id, recommendations: [{event_id, title, rationale, score, 
     closes_skills: [skill_id], critical: bool, duration_hours, format}]}
   - HR skill gaps: [{skill_id, skill_name, total_gap, employees_affected}]
   - HR no-recommendation: [{employee_id, full_name, role, grade}]
   - HR participation: [{event_id, title, completed, declined, no_show, dropped, in_progress}]

3. A simple router with three routes: `/`, `/employee/:id`, `/hr` and a top nav bar to switch 
   between "Employee view" and "HR view", plus a text input to jump to any employee_id.

Use a clean, professional look — not a default unstyled page. Use plain CSS modules or a 
lightweight utility approach (no heavy component library needed for a hackathon).
```

---

## Step 2 — صفحه‌ی پروفایل کارمند

> این پرامپت مستقیماً روی routing و api.js/MockData.js از Step 1 سوار می‌شود.

```
Continuing the Career Quest React frontend built in the previous step, build the Employee 
Profile page (route `/employee/:id`). It receives an employee_id from the route and should:

1. Header card: full_name, role, grade badge, department, tenure_months, a small language 
   indicator (preferred_language).

2. Skills panel: render every skill the employee has as a compact row with a progress bar 
   (level out of 5). Skills that are `critical` for the employee's next grade (you'll get this 
   flag alongside the gap data, or infer it from which skills appear in the recommendations' 
   `closes_skills` with `critical: true`) should have a visually distinct badge/highlight — 
   e.g. an amber "critical for promotion" tag. Sort critical/gap skills to the top.

3. "Recommended next steps" section: one card per recommendation, showing:
   - Event title, duration_hours, format (badge: online/offline/self-paced)
   - The rationale text (render it as-is, this is the AI-generated explanation — don't truncate it)
   - A "critical for your next grade" badge if applicable
   - A primary "Mark as completed" button
   On click: call completeActivity(employeeId, eventId), show a loading spinner on that 
   specific card (not the whole page), then on success refetch both the employee data and 
   recommendations and animate/highlight the skills that changed level. On error, show an 
   inline error message on the card without losing the rest of the page state.

4. Activity history table below: date, event title, status (colored badge: green=completed, 
   red=declined/no_show, yellow=dropped/in_progress/overdue), score if present, feedback_rating 
   as stars if present.

5. Loading and empty states: 
   - While recommendations are loading (can take up to ~10s per the backend budget), show a 
     skeleton/spinner specifically in that section, not a full-page blocker.
   - If recommendations come back empty (employee already at top grade or fully caught up), 
     show a friendly "You're all caught up! No new steps right now." message instead of an 
     empty gap.

Use the MockData from Step 1 first, structure the component so swapping to real API calls is 
a one-line change (just call the real api.js functions instead of MockData).
```

---

## Step 3 — صفحه‌ی HR

> این پرامپت روی همان routing از Step 1 سوار می‌شود (مستقل از صفحه‌ی پروفایل در Step 2).

```
Continuing the Career Quest React frontend, build the HR Dashboard page (route `/hr`). This is 
for HR specialists, not for comparing/ranking individual employees publicly — do not build any 
leaderboard or ranked list of employees by performance; keep everything aggregate/skill-level 
or a plain unranked list of names needing attention.

Three sections, each fetched independently (so one slow call doesn't block the others):

1. "Skill gaps across the company" — a horizontal bar chart or simple table (skill_name, 
   total_gap, employees_affected), sorted descending, top 15. Use a simple charting approach 
   (e.g. plain CSS bars sized by value, or a lightweight chart lib if already in the project) — 
   don't add a heavy dependency just for this.

2. "Employees without a next step" — a plain list/table of {full_name, role, grade} with a 
   link to each employee's profile page (reuse the routing to `/employee/:id` from Step 2). 
   Add a short explanatory line: "These employees are either at the top grade or have no 
   eligible activity right now — may need a manual check-in."

3. "Participation by activity" — a table: event title, completed, declined, no_show, dropped, 
   in_progress, with a small colored proportion bar per row (like a mini stacked bar showing 
   the ratio of statuses) so HR can spot events with high decline/no-show rates at a glance.

Use the HR mock data functions from Step 1's MockData.js. Add a loading skeleton per section 
and a "Refresh" button that refetches all three.
```

---

## Step 4 — فرم import داده‌ی داور

> این پرامپت به navigation و api.js از Step 1 اضافه می‌شود؛ آخرین قطعه‌ی فرانت‌اند.

```
Continuing the Career Quest React frontend, build a small "Import test data" page/modal, 
accessible from the top nav bar (built in Step 1), used by hackathon judges to upload 
additional employee profiles and activity history at defense time, matching the same JSON/CSV 
schema as the starter dataset.

Requirements:
- A file input (or textarea for pasting raw JSON/CSV) with a dropdown to select "Employees" 
  or "Activity History" as the data type
- Client-side validation: for JSON, confirm it parses and has the expected top-level shape 
  before sending; for CSV, confirm the header row matches the expected columns 
  (record_id, employee_id, event_id, date, due_date, status, completion_pct, score, 
  feedback_rating, assigned_by)
- On submit, POST to importData() from api.js (built in Step 1); show a clear success message 
  with a count of records imported, or a readable validation error if the backend rejects it
- After a successful employee import, show a quick link/button "View imported employee" that 
  jumps straight to /employee/:id (the page from Step 2) using the first imported employee_id
- Keep this simple and functional — it only needs to work reliably during the live defense, 
  not be beautiful

This completes the frontend: after this step, the app should have Employee view, HR view, and 
Import, all wired together via the shared api.js client and routing from Step 1.
```
