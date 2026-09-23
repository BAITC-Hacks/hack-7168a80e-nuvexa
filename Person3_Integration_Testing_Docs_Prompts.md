# نفر ۳ — یکپارچه‌سازی، تست، مستندسازی، سابمیت
## پرامپت‌های Codex، قدم‌به‌قدم

> ترتیب مهم است: هر پرامپت روی خروجی پرامپت قبلی (یا روی کد نفر ۱ و ۲) سوار می‌شود.
> پرامپت‌ها را دقیقاً به همین ترتیب (Step 1 → Step 2 → Step 3 → Step 4) در Codex کپی کنید.
> Step 1 و Step 2 را می‌توانید از همان فاز ۳ (زمانی که نفر ۱ و ۲ هنوز در حال کدنویسی هستند) شروع کنید؛ Step 3 و Step 4 برای فاز ۴ و ۶ هستند.

---

## Step 1 — تولید سناریوهای تست از دیتاست واقعی

> این را می‌توانید مستقل از کار نفر ۱ و ۲ همان اول فاز ۳ اجرا کنید — فقط به دیتاست خام نیاز دارد.

```
I have the Career Quest starter dataset in `data/employees.json`, `data/events.json`, 
`data/skills.json`, `data/activity_history.csv` (schemas as described in the dataset's own 
README.md — read that file first).

Write a Python script `scripts/find_test_scenarios.py` that scans the real dataset and prints 
out employee_ids matching these three patterns, so we can use REAL employees (not invented ones) 
as manual test cases before the defense:

1. "Gap-vs-history conflict": an employee whose lowest-level skill (relative to their next 
   grade's requirement) is a soft skill, but who has 2+ declined/no_show/dropped records in 
   activity_history for events developing that same soft skill, AND has a hard, critical skill 
   with a smaller but nonzero gap. Print employee_id, both skill gaps, and the relevant history 
   count.

2. "New hire": tenure_months <= 3, with activity_history containing only EV_004 (or being empty). 
   Print employee_id and their history.

3. "Near grade ceiling": an employee where the sum of remaining gaps to their next grade's 
   required_skills is <= 2 total (i.e. almost ready to be promoted). Print employee_id and 
   the remaining gaps.

For each category, print up to 3 matching employee_ids with their key facts, so the team can 
pick one from each category as a manual smoke test.
```

---

## Step 2 — اسکریپت تست end-to-end

> این پرامپت را وقتی اجرا کنید که نفر ۱ حداقل چند endpoint اصلی را بالا آورده (اواسط فاز ۳). از employee_idهایی که Step 1 پیدا کرد استفاده کنید.

```
Continuing the Career Quest project, write a Python script `scripts/e2e_smoke_test.py` that 
exercises the full flow against the running backend (base URL from an env var, default 
http://localhost:8000) for a given employee_id (passed as a CLI arg — use one of the 
employee_ids found by scripts/find_test_scenarios.py from the previous step):

1. GET /employees/{id} — assert 200 and that the response has role, grade, skills
2. GET /employees/{id}/recommendations — assert 200, response time < 10 seconds (print the 
   actual time), and for each recommendation:
   - assert `rationale` is non-empty
   - assert the rationale text is at least 40 characters (sanity check it's not a placeholder)
   - print a simple heuristic count of how many distinct factor types are mentioned (look for 
     keywords like grade-level numbers, "critical"/"important", history-related words like 
     "before"/"previously"/"declined") — print a WARNING if fewer than 2 are detected
3. If recommendations is non-empty, POST /employees/{id}/activities/{first_event_id}/complete 
   — assert 200, and assert the returned skill level for at least one closed skill increased 
   (or stayed at max_level if already capped)
4. GET /employees/{id}/recommendations again — print whether the completed event has disappeared 
   from the new recommendation list (expected, unless it's EV_036)
5. GET /hr/skill-gaps, /hr/employees-without-recommendation, /hr/participation-stats — assert 
   all return 200 with non-empty/well-formed JSON

Print a clear PASS/FAIL summary line per step, and exit with a non-zero code if anything fails, 
so it can be run right before the final push as a last sanity check.
```

---

## Step 3 — README نهایی

> اجرای این پرامپت را تا فاز ۶ (وقتی بک‌اند و فرانت‌اند merge شدند و Step 2 پاس شد) نگه دارید — چون این پرامپت کل ریپو را آنالیز می‌کند و باید محتوای واقعی و نهایی موجود باشد.

```
Analyze the current project and create a complete README.md file in English.
The README should be clear and easy for the hackathon judges to understand and
should include:
1. Project name
2. Short description — what problem the project solves and who it is designed for.
3. What has been implemented — the main features and capabilities of the solution.
4. How the solution works — briefly describe the main user flow from input data to the
final result.
5. Technologies — programming languages, frameworks, libraries, AI models, APIs, and
external services used.
6. Project architecture — the main components and how they interact with each other.
7. Installation and launch — step-by-step setup instructions with the required commands.
8. How to test the solution — provide an example scenario that the judges can reproduce 
   (mention scripts/e2e_smoke_test.py from the previous step as a way to verify the flow 
   end-to-end).
9. Data and integrations — specify the data sources, APIs, and external services used.
10. Limitations — explain what has not been implemented or what limitations the current
version has.
11. Link to the deployed version, if available.
Use only information that can be verified from the current repository. Do not invent
features, technologies, or results that are not actually present in the project. Format the
README cleanly in Markdown.
```

---

## Step 4 — چک نهایی قبل از push

> آخرین پرامپت، در ۱۵-۲۰ دقیقه‌ی پایانی، بعد از Step 3. فقط گزارش می‌گیرد، تغییری در کد نمی‌دهد — تیم بر اساس گزارش تصمیم می‌گیرد چه چیزی را در وقت باقی‌مانده رفع کند.

```
Review the entire Career Quest repository (including the README.md just generated in the 
previous step) and report, without making any code changes yet:

1. Search for any hardcoded API keys, tokens, or secrets in tracked files (not .env.example) 
   and list every file/line found
2. Confirm a `.gitignore` exists and excludes `.env`, `node_modules`, `__pycache__`, and any 
   local data/export files
3. Confirm `.env.example` exists and lists every environment variable actually used in the 
   code (cross-check against real usages of os.environ / import.meta.env), with placeholder 
   values only
4. List any TODO/FIXME comments left in the code, so the team can decide what to fix in the 
   remaining minutes vs. mention as a known limitation in the README
5. Confirm the README's "Installation and launch" commands match what's actually in 
   package.json/requirements.txt (no missing dependencies, no typos in commands)

Output a short prioritized checklist of anything that must be fixed before the final push, 
separated from anything that's just nice-to-have.
```
