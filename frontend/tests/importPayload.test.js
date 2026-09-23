import assert from 'node:assert/strict';
import test from 'node:test';
import { activityColumns, createImportPayload } from '../src/lib/importPayload.js';

const employee = {
  employee_id: 'E9001', full_name: 'Dana Example', department: 'Engineering',
  role: 'Backend Engineer', grade: 'Junior', hire_date: '2026-03-01',
  tenure_months: 6, work_format: 'hybrid', preferred_language: 'en',
  skills: { SK_COMMUNICATION: 2 },
};
const history = {
  record_id: 'IMPORT_DEMO_9001', employee_id: 'E0001', event_id: 'EV_036',
  date: '2026-09-01', status: 'in_progress', completion_pct: 25, assigned_by: 'self',
};

test('employee array produces the backend file-import contract without requiring nullable defaults', () => {
  assert.deepEqual(createImportPayload(JSON.stringify([employee]), 'employees'), {
    payload: { type: 'employees', data: [employee] }, firstEmployeeId: 'E9001',
  });
});

test('employees wrapper accepts dataset metadata and a UTF-8 BOM', () => {
  const result = createImportPayload('\uFEFF' + JSON.stringify({ meta: { synthetic: true }, employees: [employee] }), 'employees');
  assert.deepEqual(result.payload.data, [employee]);
});

test('history array and supported wrappers map to history and retain JSON numeric types', () => {
  const row = { ...history, feedback_rating: 5, score: null };
  const documents = [[row], { history: [row] }, { activity_history: [row] }, { records: [row] }];
  for (const document of documents) {
    assert.deepEqual(createImportPayload(JSON.stringify(document), 'activity_history'), {
      payload: { type: 'history', data: [row] }, firstEmployeeId: null,
    });
  }
});

test('raw CSV reaches backend unchanged including BOM, CRLF, quotes and multiline values', () => {
  const csv = '\uFEFF' + activityColumns.join(',') + '\r\nIMPORT_DEMO_9001,E0001,EV_036,2026-09-01,,in_progress,25,,5,"self,\r\nassigned"\r\n';
  assert.deepEqual(createImportPayload(csv, 'activity_history').payload, { type: 'history', data: csv });
});

test('quoted CSV headers are accepted without transforming the original file', () => {
  const csv = activityColumns.map(column => `"${column}"`).join(',') + '\nIMPORT_DEMO_9001,E0001,EV_036,2026-09-01,,in_progress,25,,,self';
  assert.equal(createImportPayload(csv, 'history').payload.data, csv);
});

test('CSV requires exact header names and order and at least one record', () => {
  const csvRow = '\nIMPORT_DEMO_9001,E0001,EV_036,2026-09-01,,in_progress,25,,,self';
  assert.throws(() => createImportPayload([...activityColumns].reverse().join(',') + csvRow, 'history'), /exact column order/);
  assert.throws(() => createImportPayload(' ' + activityColumns.join(',') + csvRow, 'history'), /exact column order/);
  assert.throws(() => createImportPayload(activityColumns.join(',') + '\r\n\r\n', 'history'), /no records/);
});

test('missing required fields identify the record and field', () => {
  const { skills, ...missingSkills } = employee;
  assert.throws(() => createImportPayload(JSON.stringify([employee, missingSkills]), 'employees'), /Record 2 is missing fields: skills/);
  const { status, ...missingStatus } = history;
  assert.throws(() => createImportPayload(JSON.stringify([missingStatus]), 'history'), /status/);
});

test('empty, invalid, ambiguous and wrong record shapes give readable errors', () => {
  assert.throws(() => createImportPayload(' ', 'employees'), /Choose a file/);
  assert.throws(() => createImportPayload('{', 'employees'), /Invalid JSON/);
  assert.throws(() => createImportPayload('[]', 'employees'), /non-empty array/);
  assert.throws(() => createImportPayload('[null]', 'history'), /Record 1 must be an object/);
  assert.throws(() => createImportPayload(JSON.stringify({ history: [history], records: [history] }), 'history'), /Expected one/);
  assert.throws(() => createImportPayload(JSON.stringify({ history: [history] }), 'employees'), /employees array/);
});
