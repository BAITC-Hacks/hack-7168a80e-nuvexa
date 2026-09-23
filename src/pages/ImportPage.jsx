import React from 'react';
import { data } from '../lib/data.js';
import { PageHeading } from '../components/Shell.jsx';

const activityColumns = ['record_id', 'employee_id', 'event_id', 'date', 'due_date', 'status', 'completion_pct', 'score', 'feedback_rating', 'assigned_by'];
const employeeFields = ['employee_id', 'full_name', 'department', 'role', 'grade', 'manager_id', 'hire_date', 'tenure_months', 'work_format', 'preferred_language', 'career_goal', 'skills', 'last_review_date'];

function parseCsv(text) {
  const lines = text.trim().split(/\r?\n/).filter(Boolean); if (!lines.length) throw new Error('Paste a CSV header and at least one data row.');
  const parseLine = line => { const out = []; let cell = '', quoted = false; for (let i = 0; i < line.length; i++) { const c = line[i]; if (c === '"' && line[i + 1] === '"' && quoted) { cell += '"'; i++; } else if (c === '"') quoted = !quoted; else if (c === ',' && !quoted) { out.push(cell.trim()); cell = ''; } else cell += c; } out.push(cell.trim()); return out; };
  const header = parseLine(lines[0]);
  if (header.length !== activityColumns.length || header.some((column, index) => column !== activityColumns[index])) throw new Error(`CSV header must match this exact column order: ${activityColumns.join(', ')}.`);
  const records = lines.slice(1).map((line, i) => { const cells = parseLine(line); if (cells.length !== header.length) throw new Error(`CSV row ${i + 2} has ${cells.length} values; expected ${header.length}.`); return Object.fromEntries(header.map((key, index) => [key, cells[index] || null])); });
  if (!records.length) throw new Error('CSV has a header but no records.'); return records;
}

function parseInput(text, type) {
  if (!text.trim()) throw new Error('Choose a file or paste data to continue.');
  const looksCsv = type === 'activity_history' && !text.trimStart().startsWith('[') && !text.trimStart().startsWith('{');
  if (looksCsv) return parseCsv(text);
  let parsed; try { parsed = JSON.parse(text); } catch (e) { throw new Error(`Invalid JSON: ${e.message}`); }
  const records = Array.isArray(parsed) ? parsed : type === 'employees' ? parsed?.employees : (parsed?.activity_history || parsed?.records);
  if (!Array.isArray(records) || !records.length) throw new Error(type === 'employees' ? 'Expected an array of employee records, or an object with an employees array.' : 'Expected an array of activity records, or an object with an activity_history array.');
  const fields = type === 'employees' ? employeeFields : activityColumns;
  const invalidIndex = records.findIndex(record => !record || typeof record !== 'object' || Array.isArray(record) || fields.some(field => !(field in record)));
  if (invalidIndex !== -1) {
    const record = records[invalidIndex];
    const missing = !record || typeof record !== 'object' || Array.isArray(record) ? fields : fields.filter(field => !(field in record));
    throw new Error(`Record ${invalidIndex + 1} is invalid or missing fields: ${missing.join(', ')}.`);
  }
  return records;
}

export default function ImportPage({ navigate }) {
  const [type, setType] = React.useState('employees'); const [text, setText] = React.useState(''); const [fileName, setFileName] = React.useState(''); const [error, setError] = React.useState(''); const [busy, setBusy] = React.useState(false); const [success, setSuccess] = React.useState(null);
  const onFile = async event => { const file = event.target.files?.[0]; if (!file) return; setFileName(file.name); setError(''); setSuccess(null); setText(await file.text()); };
  const submit = async event => { event.preventDefault(); setError(''); setSuccess(null); let records; try { records = parseInput(text, type); } catch (err) { setError(err.message); return; }
    setBusy(true); try { const payload = type === 'employees' ? { type: 'employees', employees: records } : { type: 'activity_history', activity_history: records }; const result = await data.importData(payload); setSuccess({ count: result?.imported ?? result?.count ?? records.length, firstId: type === 'employees' ? records[0]?.employee_id : null }); }
    catch (err) { setError(err.message || 'The import was rejected.'); } finally { setBusy(false); }
  };
  const example = type === 'employees' ? '[\n  {\n    "employee_id": "EMP_101",\n    "full_name": "Dana Example",\n    "department": "Retail Banking",\n    "role": "Relationship Manager",\n    "grade": "Junior",\n    "manager_id": null,\n    "hire_date": "2026-03-01",\n    "tenure_months": 6,\n    "work_format": "hybrid",\n    "preferred_language": "en",\n    "career_goal": null,\n    "skills": { "communication": 2 },\n    "last_review_date": null\n  }\n]' : 'record_id,employee_id,event_id,date,due_date,status,completion_pct,score,feedback_rating,assigned_by\nACT_9001,EMP_001,EV_014,2026-09-01,,completed,100,90,5,self';
  return <div className="page-wrap"><PageHeading eyebrow="DATA WORKSPACE" title="Bring new data in." subtitle="Add employee profiles or activity history to support your live demo."/>
    <div className="import-layout"><form className="panel import-panel" onSubmit={submit}>
      <div className="eyebrow">DEFENSE DAY TOOL</div><h2>Import test data</h2><p className="muted">Select a dataset, upload a file or paste records, then validate and import.</p>
      <label className="field-label" htmlFor="dataType">Data type</label><select id="dataType" className="select-field" value={type} onChange={e => { setType(e.target.value); setError(''); setSuccess(null); }}><option value="employees">Employees</option><option value="activity_history">Activity history</option></select>
      <label className="field-label" htmlFor="dataFile">Choose file <span>JSON{type === 'activity_history' ? ' or CSV' : ''}</span></label><label className="file-drop" htmlFor="dataFile"><span className="upload-icon">↑</span><strong>{fileName || 'Choose a file to upload'}</strong><small>or paste your data below</small><input id="dataFile" type="file" accept={type === 'activity_history' ? '.json,.csv,application/json,text/csv' : '.json,application/json'} onChange={onFile}/></label>
      <label className="field-label" htmlFor="dataText">Paste {type === 'activity_history' ? 'JSON or CSV' : 'JSON'} data</label><textarea id="dataText" className="data-textarea" rows="11" value={text} onChange={e => { setText(e.target.value); setFileName(''); setSuccess(null); }} placeholder={example}/>
      <p className="format-hint">{type === 'employees' ? 'Required on each record: ' + employeeFields.join(', ') : 'CSV header must include: ' + activityColumns.join(', ')}</p>
      {error && <div className="error-notice" role="alert">{error}</div>}{success && <div className="success-notice" role="status"><strong>Import complete</strong><span>{success.count} record{success.count === 1 ? '' : 's'} imported.</span>{success.firstId && <button className="text-button" type="button" onClick={() => navigate(`/employee/${encodeURIComponent(success.firstId)}`)}>View imported employee →</button>}</div>}
      <button className="button-primary import-submit" disabled={busy}>{busy ? <><span className="button-spinner"/> Importing…</> : 'Validate and import →'}</button>
    </form><aside className="import-aside"><div className="import-aside-icon">↗</div><div className="eyebrow">SUPPORTED FORMATS</div><h3>Keep your data consistent.</h3><p>Employee profiles use the starter dataset fields. Activity history supports CSV with the exact header listed here, or JSON records with the same fields.</p><div className="aside-divider"/><div className="format-row"><span className="format-icon">{ }</span><span><strong>Employee profiles</strong><small>JSON array or {`{ "employees": [...] }`}</small></span></div><div className="format-row"><span className="format-icon">CSV</span><span><strong>Activity history</strong><small>CSV or JSON records</small></span></div><div className="notice-note"><strong>Before importing</strong><span>Check IDs and field names. Invalid records will be rejected with a message from the server.</span></div></aside></div>
  </div>;
}
