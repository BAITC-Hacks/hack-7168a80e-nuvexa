import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import test from 'node:test';
import { ApiError, createApiClient } from '../src/lib/api.js';
import { activityColumns, createImportPayload } from '../src/lib/importPayload.js';

// This suite mutates an isolated, freshly started backend using the full dataset.
// It never falls back to the developer's API on port 8000.
const baseUrl = process.env.CAREER_QUEST_TEST_API_URL;

test('frontend client completes the real backend workflow', {
  skip: !baseUrl && 'Set CAREER_QUEST_TEST_API_URL to an isolated, fresh backend.',
}, async t => {
  const api = createApiClient(baseUrl);
  const getHealth = async () => {
    const response = await fetch(`${baseUrl.replace(/\/+$/, '')}/health`);
    assert.equal(response.status, 200);
    return response.json();
  };
  const isApiStatus = status => error => error instanceof ApiError && error.status === status;
  const suffix = randomUUID();
  const importedId = `INTEGRATION_${suffix}`;
  const missingId = `INTEGRATION_MISSING_${suffix}`;
  let health, employee, catalog;

  await t.test('health, employee profile, catalog and CORS match the connected frontend', async () => {
    health = await getHealth();
    assert.equal(health.status, 'ok');
    assert.equal(health.rationale_mode, 'template');
    assert.equal(health.employees, 200);
    assert.equal(health.events, 40);
    assert.equal(health.history_records, 2743);
    [employee, catalog] = await Promise.all([api.getEmployee('E0001'), api.getSkills()]);
    assert.equal(employee.employee_id, 'E0001');
    assert.equal(catalog.length, 60);
    const skillIds = new Set(catalog.map(skill => skill.skill_id));
    assert.ok(Object.keys(employee.skills).every(id => skillIds.has(id)));
    assert.ok(employee.skill_gaps.every(gap => skillIds.has(gap.skill_id)));
    assert.ok(catalog.every(skill => skill.name));
    await assert.rejects(api.getEmployee(missingId), isApiStatus(404));

    const preflight = await fetch(`${baseUrl.replace(/\/+$/, '')}/data/import`, {
      method: 'OPTIONS',
      headers: {
        Origin: 'http://127.0.0.1:5173',
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'content-type',
      },
    });
    assert.equal(preflight.status, 200);
    assert.equal(preflight.headers.get('access-control-allow-origin'), 'http://127.0.0.1:5173');
    assert.match(preflight.headers.get('access-control-allow-methods'), /POST/);
  });

  await t.test('completion updates skills, history and recommendations; duplicate is 409', async () => {
    const before = await api.getRecommendations('E0001');
    const activity = before.recommendations.find(item => item.event_id === 'EV_005')
      || before.recommendations.find(item => item.event_id !== 'EV_036');
    assert.ok(activity, 'Fresh E0001 must have a non-recurring recommendation.');
    const result = await api.completeActivity('E0001', activity.event_id);
    assert.equal(result.employee_id, 'E0001');
    assert.equal(result.event_id, activity.event_id);
    assert.ok(Object.entries(result.skills).some(([id, level]) => level > (employee.skills[id] || 0)));
    assert.ok(Object.entries(employee.skills).every(([id, level]) => result.skills[id] >= level));
    assert.ok(result.recommendations.every(item => item.event_id !== activity.event_id));
    const [updated, refreshed] = await Promise.all([api.getEmployee('E0001'), api.getRecommendations('E0001')]);
    assert.deepEqual(updated.skills, result.skills);
    assert.ok(updated.activity_history.some(row => row.event_id === activity.event_id && row.status === 'completed'));
    assert.ok(refreshed.recommendations.every(item => item.event_id !== activity.event_id));
    await assert.rejects(api.completeActivity('E0001', activity.event_id), isApiStatus(409));
  });

  await t.test('HR aggregates include all six statuses and the new completion', async () => {
    const [gaps, withoutRecommendations, stats] = await Promise.all([
      api.getHrSkillGaps(), api.getHrEmployeesWithoutRecommendation(), api.getHrParticipationStats(),
    ]);
    assert.ok(gaps.length > 0);
    assert.ok(gaps.every(row => row.skill_name && row.employees_affected > 0));
    assert.ok(Array.isArray(withoutRecommendations));
    const statuses = ['completed', 'declined', 'no_show', 'dropped', 'in_progress', 'overdue'];
    for (const row of stats) {
      assert.ok(statuses.every(status => Number.isInteger(row[status]) && row[status] >= 0));
      assert.equal(row.total, statuses.reduce((sum, status) => sum + row[status], 0));
    }
    assert.equal(stats.reduce((sum, row) => sum + row.total, 0), 2744);
  });

  let importedEmployee;
  await t.test('employee JSON and raw history CSV import through the frontend helper', async () => {
    const { activity_history, next_grade, skill_gaps, ...profile } = await api.getEmployee('E0002');
    importedEmployee = {
      ...profile, employee_id: importedId, full_name: 'Integration Demo',
      last_review_date: health.snapshot_date,
    };
    const employeePayload = createImportPayload(JSON.stringify({ employees: [importedEmployee] }), 'employees');
    const imported = await api.importData(employeePayload.payload);
    assert.equal(imported.employees_imported, 1);
    assert.equal(imported.history_imported, 0);
    assert.equal((await api.getEmployee(importedId)).full_name, 'Integration Demo');

    const recordId = `INTEGRATION_HISTORY_${suffix}`;
    const csv = '\uFEFF' + activityColumns.join(',') + '\r\n'
      + `${recordId},${importedId},EV_036,${health.snapshot_date},,in_progress,25,,4,self\r\n`;
    const historyPayload = createImportPayload(csv, 'activity_history');
    const importedHistory = await api.importData(historyPayload.payload);
    assert.equal(importedHistory.employees_imported, 0);
    assert.equal(importedHistory.history_imported, 1);
    const saved = await api.getEmployee(importedId);
    const record = saved.activity_history.find(row => row.record_id === recordId);
    assert.ok(record);
    assert.equal(record.feedback_rating, 4);
    assert.equal(record.completion_pct, 25);
    assert.equal(record.score, null);
    assert.equal(record.due_date, null);
    assert.equal(record.status, 'in_progress');
    assert.deepEqual(saved.skills, importedEmployee.skills);
  });

  await t.test('unknown skill rejects the complete import batch without partial changes', async () => {
    const goodId = `INTEGRATION_GOOD_${suffix}`;
    const badId = `INTEGRATION_BAD_${suffix}`;
    const before = await getHealth();
    const payload = createImportPayload(JSON.stringify([
      { ...importedEmployee, employee_id: goodId },
      { ...importedEmployee, employee_id: badId, skills: { SK_INTEGRATION_UNKNOWN: 2 } },
    ]), 'employees').payload;
    await assert.rejects(api.importData(payload), error => isApiStatus(422)(error) && /skill/i.test(error.message));
    await assert.rejects(api.getEmployee(goodId), isApiStatus(404));
    await assert.rejects(api.getEmployee(badId), isApiStatus(404));
    const after = await getHealth();
    assert.equal(after.employees, before.employees);
    assert.equal(after.history_records, before.history_records);
    assert.equal(after.employees, 201);
    assert.equal(after.history_records, 2745);
  });
});
