# نفر ۱ — Backend + منطق هوش مصنوعی
## پرامپت‌های Codex، قدم‌به‌قدم

> ترتیب مهم است: هر پرامپت مستقیماً روی کدی که پرامپت قبلی ساخته ادامه می‌دهد.
> پرامپت‌ها را دقیقاً به همین ترتیب (Step 1 → Step 2 → Step 3 → Step 4) در Codex کپی کنید — هرکدام را در یک پیام/تسک جدا بفرستید، نه همه با هم.
> **استک فرض‌شده:** Python + FastAPI. اگر استک دیگری انتخاب کردید، فقط عبارت "Use FastAPI" را با استک خودتان جایگزین کنید؛ بقیه‌ی جزئیات دیتاست و منطق ثابت می‌ماند.

---

## Step 1 — Data layer + مدل‌ها

```
You are building the backend for "Career Quest", an AI-powered employee development
recommender for a hackathon (Halyk Bank track). Use Python with FastAPI.

Context: the project has a `data/` folder with:
- employees.json: {"meta": {...}, "employees": [{employee_id, full_name, department, role, 
  grade, manager_id, hire_date, tenure_months, work_format, preferred_language, 
  career_goal: {target_role, target_grade} | null, skills: {skill_id: level 0-5}, 
  last_review_date}]}
- skills.json: {"meta": {...}, "proficiency_scale": {...}, 
  "skills": [{skill_id, name, type, category, description}],
  "role_profiles": [{role, grade, required_skills: {skill_id: min_level}, critical_skills: [skill_id]}]}
- events.json: {"meta": {...}, "events": [{event_id, title, description, type, format, 
  duration_hours, mandatory, target_roles: [], target_grades: [], 
  develops_skills: [{skill_id, gain, max_level}], prerequisites: {skill_id: min_level}, 
  upcoming_sessions: [dates]}]}
- activity_history.csv: record_id, employee_id, event_id, date, due_date, status 
  (completed|in_progress|dropped|no_show|declined|overdue), completion_pct, score, 
  feedback_rating, assigned_by

The grade order for role_profiles is always: Junior -> Middle -> Senior -> Lead.
Treat "2026-10-01" as the current snapshot date (put this in a config constant, not hardcoded 
everywhere).

Build:
1. Pydantic models for Employee, Event, SkillGap, RoleProfile, ActivityRecord matching the 
   schemas above exactly (all fields, correct optional/nullable types).
2. A `DataStore` class that loads all four files at startup into memory (pandas DataFrame 
   for activity_history.csv, dicts/lists for the JSON files), with:
   - `get_employee(employee_id) -> Employee | None`
   - `get_next_grade(role: str, grade: str) -> str | None` (None if already Lead)
   - `get_role_profile(role: str, grade: str) -> RoleProfile | None`
   - `get_employee_history(employee_id) -> list[ActivityRecord]`
   - `import_employees(new_employees: list[dict])` and `import_history(new_records: list[dict])` 
     that validate against the same schema and merge into the in-memory store (for judge-provided 
     test data at defense time)
3. A FastAPI app skeleton with a `/health` endpoint and the DataStore loaded as a singleton 
   dependency.

Write clean, typed, testable code. Add docstrings. Do not implement the recommendation logic 
yet — that's a separate step.
```

---

## Step 2 — موتور توصیه (gap + eligibility + scoring)

> این پرامپت مستقیماً روی کد Step 1 ادامه می‌دهد — همان پروژه، همان DataStore و مدل‌ها.

```
Continuing the Career Quest FastAPI backend (DataStore already built in the previous step), 
implement the core recommendation engine in a new module `recommendation_engine.py`. This is 
the most important and most heavily judged part of the project — it must be fully deterministic 
and explainable, with NO LLM calls in this file.

Implement:

1. `compute_skill_gaps(employee: Employee, role_profile: RoleProfile) -> list[SkillGap]`
   - For each skill_id in role_profile.required_skills: 
     gap = max(0, required_level - employee.skills.get(skill_id, 0))
   - Mark `critical = skill_id in role_profile.critical_skills`
   - Weight: critical gaps count 2x in later scoring (store the raw gap AND the weighted gap)
   - Return sorted by weighted gap descending
   - If employee is already at the top grade (next grade is None), return []

2. `filter_eligible_events(employee: Employee, events: list[Event], 
   history: list[ActivityRecord], today: date) -> list[Event]`
   Keep only events where ALL of these hold:
   - employee.role in event.target_roles AND employee.grade in event.target_grades
   - event.mandatory is False (mandatory events are never a "recommendation", per spec)
   - event.develops_skills is non-empty (compliance events with empty develops_skills are 
     never recommended — they don't build a career skill)
   - No history record for this employee+event_id with status == "completed", 
     UNLESS event_id == "EV_036" (the recurring club, which can be completed repeatedly)
   - prerequisites are met: for every skill_id in event.prerequisites, 
     employee.skills.get(skill_id, 0) >= min_level
   - if event.format != "self_paced": event.upcoming_sessions must contain at least one 
     date >= today

3. `compute_participation_penalty(employee_id: str, event: Event, 
   history: list[ActivityRecord], all_events: dict[str, Event]) -> float`
   - Find this employee's past history records for OTHER events that develop at least one 
     of the same skill_id(s) as `event`
   - Count how many of those have status in {"declined", "no_show", "dropped"}
   - Also add a smaller penalty for any feedback_rating <= 2 found in that same filtered set
   - Return a single float penalty score (document your weighting choice in a comment, e.g. 
     declined/no_show/dropped = 1.0 each, low feedback = 0.5 each)

4. `score_event(employee: Employee, event: Event, gaps: list[SkillGap], 
   penalty: float) -> ScoredEvent`
   - `ScoredEvent` is a new Pydantic model: {event_id, event_title, score, closes_skills: 
     list[str], gap_before: dict[str,int], gap_after: dict[str,int], critical: bool, 
     past_declines_for_similar: int, duration_hours, format}
   - For each skill in event.develops_skills, find the matching gap (if any). The amount this 
     event actually closes = min(existing_gap, develops_skills.gain), capped so the resulting 
     level never exceeds develops_skills.max_level.
   - Sum up the weighted "gap closed" across all skills this event develops (critical skills 
     weighted 2x, as in step 1)
   - `raw_score = weighted_gap_closed - PENALTY_WEIGHT * penalty` 
     (define PENALTY_WEIGHT as a named constant, e.g. 1.5, with a comment explaining the choice)
   - Add a flat CRITICAL_BONUS if the event closes at least one critical-skill gap fully
   - Populate gap_before/gap_after per skill, critical flag, past_declines_for_similar

5. `recommend_next_steps(data_store: DataStore, employee_id: str, top_n: int = 3, 
   today: date = None) -> list[ScoredEvent]`
   - Orchestrates 1-4, sorts by score descending, returns top_n
   - If employee is already at the top grade, or no eligible events remain, return []
   - Must run in well under 1 second (this is pure computation, no I/O)

Write unit-test-friendly pure functions (no global state, no side effects). Add a short comment 
above each weighting constant explaining WHY that number, so it's defensible to a judge asking 
"why does history matter more/less than skill gap".
```

---

## Step 3 — Rationale generation با LLM

> این پرامپت مستقیماً روی خروجی `recommendation_engine.py` از Step 2 سوار می‌شود.

```
Add a new module `rationale_generator.py` to the Career Quest backend (built in the previous 
steps). This module takes the structured `ScoredEvent` objects from `recommendation_engine.py` 
and produces a natural-language explanation using an LLM call — it must NEVER recompute or 
invent any numeric fact itself.

Implement:

1. `build_rationale_prompt(employee: Employee, scored_event: ScoredEvent) -> str`
   Construct a prompt (in English, for the API call) that:
   - Lists ONLY the facts already computed: which skill(s) it closes, gap_before -> gap_after 
     per skill, whether it's critical for the employee's next grade, past_declines_for_similar, 
     duration_hours
   - Instructs the model: "Write a 2-3 sentence explanation in {employee.preferred_language} 
     ('kk', 'ru', or 'en' -> map to Kazakh/Russian/English) for why this activity is recommended. 
     You MUST explicitly reference at least 3 of the following distinct factors: (a) current 
     skill level vs. the level required for the next grade, (b) whether the skill is critical 
     for promotion, (c) the employee's past participation pattern with similar activities, 
     (d) how much this specific activity will close the gap. Do not invent any fact, number, 
     or skill name not given to you above. Do not mention data you were not given. 
     Keep it concise and actionable, addressed directly to the employee ('you')."

2. `explain_recommendation(client, employee: Employee, scored_event: ScoredEvent) -> str`
   - Calls the Anthropic or OpenAI chat completion API (use environment variable for the API 
     key, read model name from an env var too, default to a small/fast model)
   - max_tokens ~150-200, temperature low (~0.3) for consistency
   - Wrap the call in a timeout of ~6 seconds and a try/except: on failure, fall back to a 
     deterministic template-based sentence built directly from the factors (so the app never 
     breaks if the API is slow/down) — write that fallback function too, e.g.:
     "This closes your {skill} gap ({gap_before}->{gap_after}) which is required for {next_grade}."

3. A FastAPI endpoint `GET /employees/{employee_id}/recommendations` that:
   - Calls recommend_next_steps(), then for each ScoredEvent calls explain_recommendation()
   - Returns JSON: {employee_id, recommendations: [{event_id, title, rationale, score, 
     closes_skills, critical, duration_hours, format}]}
   - Must respond within 10 seconds total (per the task's latency requirement) — if the LLM 
     is slow, run the explain_recommendation calls concurrently with asyncio.gather rather 
     than sequentially

Log a warning (not a crash) if the LLM's response fails the "at least 3 factors" check via 
a simple heuristic (e.g. count how many of the given factor keywords appear) — helps debugging 
before the demo.
```

---

## Step 4 — Progress update + HR aggregation endpoints

> این پرامپت مستقیماً روی همه‌ی endpointهایی که تا الان (Step 1-3) ساخته شد اضافه می‌شود.

```
Add two more pieces to the Career Quest FastAPI backend built in the previous steps:

1. `POST /employees/{employee_id}/activities/{event_id}/complete`
   - Validates employee_id and event_id exist
   - Appends a new ActivityRecord to the in-memory history: 
     status="completed", completion_pct=100, date=today, assigned_by="self" 
     (record_id = next sequential ID)
   - For every entry in event.develops_skills, update employee.skills[skill_id] = 
     min(max_level, current_level + gain) — create the skill at `gain` if the employee didn't 
     have it before
   - Returns the updated employee skills AND a fresh call to recommend_next_steps() so the 
     frontend can immediately show the new recommendation list
   - Idempotency: if event_id == "EV_036" allow repeated completion; for any other event, if 
     already completed, return a 409 with a clear error message

2. Three HR endpoints, each reading across ALL employees in the DataStore:
   - `GET /hr/skill-gaps`: for every employee, compute gaps to their next grade (reuse 
     compute_skill_gaps), aggregate by skill_id (sum of gaps, count of employees with gap>0), 
     sort descending, return top 15
   - `GET /hr/employees-without-recommendation`: run recommend_next_steps for every employee, 
     return the list of {employee_id, full_name, role, grade} where the result is empty
   - `GET /hr/participation-stats`: group activity_history by event_id, count records per 
     status (completed/declined/no_show/dropped/in_progress/overdue), join with event title, 
     return sorted by total records descending

3. Finally, add `POST /data/import` (schema-validated bulk import of extra employees/history 
   using the `DataStore.import_employees` / `import_history` methods from Step 1, per the 
   task's "must be able to load additional profiles" requirement).

These are read-heavy aggregation queries over ~200 employees and ~2700 history records — keep 
them simple with plain Python loops/pandas groupby, no need for caching given the small data size, 
but note in a comment where you'd add caching if this were production scale.

Add basic input validation and 404s for unknown IDs. This completes the backend — after this 
step, the API should support the full flow: get employee -> get recommendations -> complete 
activity -> see updated skills/recommendations -> HR views -> import extra data.
```
