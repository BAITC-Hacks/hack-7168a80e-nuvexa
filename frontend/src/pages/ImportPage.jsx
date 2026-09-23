import React from 'react';
import { data } from '../lib/data.js';
import { activityColumns, employeeFields, createImportPayload } from '../lib/importPayload.js';
import { PageHeading } from '../components/Shell.jsx';

export default function ImportPage({ navigate }) {
  const [type, setType] = React.useState('employees'); const [text, setText] = React.useState(''); const [fileName, setFileName] = React.useState(''); const [error, setError] = React.useState(''); const [busy, setBusy] = React.useState(false); const [success, setSuccess] = React.useState(null);
  const onFile = async event => {
    const file = event.target.files?.[0];
    if (!file) return;
    setFileName(file.name); setError(''); setSuccess(null); setText(''); setBusy(true);
    try { setText(await file.text()); }
    catch { setError(`Could not read "${file.name}". Choose the file again or paste its contents below.`); }
    finally { setBusy(false); }
  };
  const submit = async event => {
    event.preventDefault(); setError(''); setSuccess(null);
    let parsed;
    try { parsed = createImportPayload(text, type); }
    catch (err) { setError(err.message); return; }
    setBusy(true);
    try {
      const result = await data.importData(parsed.payload);
      setSuccess({ ...result, firstId: result.employees_imported > 0 ? parsed.firstEmployeeId : null });
    } catch (err) { setError(err.message || 'The import was rejected.'); }
    finally { setBusy(false); }
  };
  const example = type === 'employees' ? JSON.stringify([{
    employee_id: 'E9001', full_name: 'Dana Example', department: 'Engineering',
    role: 'Backend Engineer', grade: 'Junior', hire_date: '2026-03-01',
    tenure_months: 6, work_format: 'hybrid', preferred_language: 'en',
    skills: { SK_COMMUNICATION: 2 },
  }], null, 2) : 'record_id,employee_id,event_id,date,due_date,status,completion_pct,score,feedback_rating,assigned_by\nIMPORT_DEMO_9001,E0001,EV_036,2026-09-01,,in_progress,25,,,self';
  return <div className="page-wrap"><PageHeading eyebrow="DATA WORKSPACE" title="Bring new data in." subtitle="Add employee profiles or activity history to support your live demo."/>
    <div className="import-layout"><form className="panel import-panel" onSubmit={submit}>
      <div className="eyebrow">DEFENSE DAY TOOL</div><h2>Import test data</h2><p className="muted">Select a dataset, upload a file or paste records, then validate and import.</p>
      <label className="field-label" htmlFor="dataType">Data type</label><select id="dataType" className="select-field" value={type} disabled={busy} onChange={e => { setType(e.target.value); setError(''); setSuccess(null); }}><option value="employees">Employees</option><option value="activity_history">Activity history</option></select>
      <label className="field-label" htmlFor="dataFile">Choose file <span>JSON{type === 'activity_history' ? ' or CSV' : ''}</span></label><label className="file-drop" htmlFor="dataFile"><span className="upload-icon">↑</span><strong>{fileName || 'Choose a file to upload'}</strong><small>or paste your data below</small><input id="dataFile" type="file" disabled={busy} accept={type === 'activity_history' ? '.json,.csv,application/json,text/csv' : '.json,application/json'} onChange={onFile}/></label>
      <label className="field-label" htmlFor="dataText">Paste {type === 'activity_history' ? 'JSON or CSV' : 'JSON'} data</label><textarea id="dataText" className="data-textarea" rows="11" value={text} disabled={busy} onChange={e => { setText(e.target.value); setFileName(''); setSuccess(null); }} placeholder={example}/>
      <p className="format-hint">{type === 'employees' ? 'Required on each record: ' + employeeFields.join(', ') : 'CSV header must include: ' + activityColumns.join(', ')}</p>
      {error && <div className="error-notice" role="alert">{error}</div>}{success && <div className="success-notice" role="status"><strong>Import complete</strong><span>{success.employees_imported} employee{success.employees_imported === 1 ? '' : 's'} and {success.history_imported} activity record{success.history_imported === 1 ? '' : 's'} imported.</span>{success.firstId && <button className="text-button" type="button" onClick={() => navigate(`/employee/${encodeURIComponent(success.firstId)}`)}>View imported employee →</button>}</div>}
      <button className="button-primary import-submit" disabled={busy}>{busy ? <><span className="button-spinner"/> Importing…</> : 'Validate and import →'}</button>
    </form><aside className="import-aside"><div className="import-aside-icon">↗</div><div className="eyebrow">SUPPORTED FORMATS</div><h3>Keep your data consistent.</h3><p>Employee profiles use the dataset fields. Activity history supports CSV with the exact header listed here, or JSON records. Optional manager, career goal, review date, due date, score and feedback fields may be omitted from JSON.</p><div className="aside-divider"/><div className="format-row"><span className="format-icon">{'{ }'}</span><span><strong>Employee profiles</strong><small>JSON array or {'{ "employees": [...] }'}</small></span></div><div className="format-row"><span className="format-icon">CSV</span><span><strong>Activity history</strong><small>CSV, JSON array, or history / activity_history / records wrapper</small></span></div><div className="notice-note"><strong>Before importing</strong><span>Check IDs and field names. Invalid records will be rejected with a message from the server.</span></div></aside></div>
  </div>;
}
