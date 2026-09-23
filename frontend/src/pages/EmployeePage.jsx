import React from 'react';
import { data, getSkillName, normalizeList } from '../lib/data.js';
import { ErrorNotice, PageHeading, Skeleton } from '../components/Shell.jsx';

function useEmployee(employeeId) {
  const [employee, setEmployee] = React.useState(null); const [recommendations, setRecommendations] = React.useState([]); const [loadingEmployee, setLoadingEmployee] = React.useState(true); const [loadingRecs, setLoadingRecs] = React.useState(true); const [error, setError] = React.useState(''); const [recError, setRecError] = React.useState(''); const [version, setVersion] = React.useState(0);
  const refresh = () => setVersion(v => v + 1);
  React.useEffect(() => {
    let live = true; setLoadingEmployee(true); setLoadingRecs(true); setError(''); setRecError('');
    data.getEmployee(employeeId).then(value => { if (live) setEmployee(value); }).catch(err => { if (live) { setError(err.message); setEmployee(null); } }).finally(() => { if (live) setLoadingEmployee(false); });
    data.getRecommendations(employeeId).then(value => { if (live) setRecommendations(normalizeList(value?.recommendations ?? value)); }).catch(err => { if (live) setRecError(err.message); }).finally(() => { if (live) setLoadingRecs(false); });
    return () => { live = false; };
  }, [employeeId, version]);
  return { employee, recommendations, loadingEmployee, loadingRecs, error, recError, refresh, setEmployee, setRecommendations, setRecError };
}

export default function EmployeePage({ employeeId }) {
  const state = useEmployee(employeeId); const [completing, setCompleting] = React.useState(''); const [changed, setChanged] = React.useState([]);
  const [skillNames, setSkillNames] = React.useState({});
  React.useEffect(() => {
    let live = true;
    data.getSkills().then(skills => {
      if (live) setSkillNames(Object.fromEntries(skills.map(skill => [skill.skill_id, skill.name])));
    }).catch(() => { /* Readable IDs remain available if the catalog cannot load. */ });
    return () => { live = false; };
  }, []);
  const skillName = id => getSkillName(id, skillNames);
  const complete = async rec => {
    setCompleting(rec.event_id); state.setRecError(''); const before = state.employee?.skills || {};
    let saved = false;
    try {
      const result = await data.completeActivity(employeeId, rec.event_id);
      saved = true;
      // The completion response already contains fresh recommendations and skills.
      // Apply it before refreshing history so a failed read cannot offer the old activity again.
      state.setEmployee(previous => ({ ...previous, skills: result.skills }));
      state.setRecommendations(normalizeList(result.recommendations));
      setChanged(Object.keys(result.skills).filter(skill => result.skills[skill] !== (before[skill] || 0)));
      const freshEmployee = await data.getEmployee(employeeId);
      state.setEmployee(freshEmployee);
    } catch (err) {
      state.setRecError(saved
        ? `Activity completed. Your skills and recommendations are updated, but the history could not refresh. ${err.message}`
        : `${err.message} Your profile and other recommendations are still available.`);
    }
    finally { setCompleting(''); }
  };
  if (state.loadingEmployee) return <div className="page-wrap"><Skeleton rows={5}/></div>;
  if (state.error || !state.employee) return <div className="page-wrap"><PageHeading eyebrow="EMPLOYEE PROFILE" title="Profile unavailable"/><ErrorNotice message={state.error || 'Employee not found.'} onRetry={state.refresh}/></div>;
  const employee = state.employee;
  const gaps = employee.skill_gaps || [];
  const gapLevels = Object.fromEntries(gaps.map(gap => [gap.skill_id, gap.current_level]));
  const skills = Object.entries({ ...gapLevels, ...employee.skills });
  // Event-level critical means at least one developed skill is critical, not all.
  const criticalSet = new Set(Array.isArray(employee.skill_gaps)
    ? gaps.filter(gap => gap.critical).map(gap => gap.skill_id)
    : state.recommendations.filter(r => r.critical).flatMap(r => r.closes_skills || []));
  const gapSet = new Set(gaps.map(gap => gap.skill_id));
  skills.sort(([a], [b]) => Number(criticalSet.has(b)) - Number(criticalSet.has(a)) || Number(gapSet.has(b)) - Number(gapSet.has(a)) || skillName(a).localeCompare(skillName(b)));
  const history = employee.activity_history || [];
  return <div className="page-wrap">
    <PageHeading eyebrow="YOUR DEVELOPMENT" title="Your career, in motion." subtitle="A clear view of where you are and the next steps that can move you forward." action={<span className="snapshot-pill"><i/> DEVELOPMENT PLAN</span>}/>
    <section className="profile-card panel"><div className="profile-monogram">{employee.full_name?.split(/\s+/).map(s => s[0]).slice(0, 2).join('')}</div><div className="profile-main"><div className="eyebrow">EMPLOYEE PROFILE <span className="dot">•</span> {employee.employee_id}</div><h2>{employee.full_name}</h2><div className="profile-meta"><span>{employee.role}</span><span>{employee.department}</span><span>{employee.tenure_months} months here</span></div></div><div className="profile-side"><span className="grade-badge">{employee.grade}</span><span className="language-label"><span className="language-icon">文</span> {({ en: 'English', ru: 'Русский', kk: 'Қазақша' })[employee.preferred_language] || employee.preferred_language || 'English'}</span></div></section>
    <div className="employee-grid">
      <section className="panel skills-panel"><div className="section-heading"><div><div className="eyebrow">YOUR FOUNDATION</div><h2>Skills snapshot</h2></div><span className="small-count">{skills.length} SKILLS</span></div><p className="muted">Your current capability, mapped against your growth path.</p>
        <div className="skill-list">{skills.map(([id, level]) => { const critical = criticalSet.has(id); const filled = Math.max(0, Math.min(5, Number(level) || 0)); return <div className={`skill-row ${changed.includes(id) ? 'skill-changed' : ''}`} key={id}><div className="skill-label"><span>{skillName(id)}{critical && <span className="critical-tag">Priority skill</span>}</span><b>{filled}<small> / 5</small></b></div><div className="progress-track"><i className={critical ? 'critical-fill' : ''} style={{ width: `${filled * 20}%` }}/></div></div>; })}{!skills.length && <p className="muted">No skill data available yet.</p>}</div>
        <div className="scale-note"><span>LEVEL 0</span><span>DEVELOPING</span><span>LEVEL 5</span></div>
      </section>
      <section className="recommendations-section"><div className="section-heading"><div><div className="eyebrow">CURATED FOR YOUR GROWTH</div><h2>Recommended next steps</h2></div><span className="rec-count">{state.recommendations.length} <span>steps</span></span></div>
        <ErrorNotice message={state.recError} onRetry={state.refresh}/>
        {state.loadingRecs ? <div className="panel recommendation-loading"><div className="loading-orbit"/><div><strong>Finding your next steps</strong><p>Matching learning opportunities to your growth path…</p></div></div> : !state.recommendations.length ? (state.recError ? null : <div className="panel caught-up"><div className="caught-icon">✓</div><h3>You're all caught up!</h3><p>No new steps right now. Check back as your development plan evolves.</p></div>) : <div className="recommendation-list">{state.recommendations.map((rec, index) => <article className="panel recommendation-card" key={rec.event_id}><div className="card-index">0{index + 1}</div><div className="recommendation-content"><div className="rec-topline"><span className="format-badge">{rec.format || 'Learning'}</span><span>{rec.duration_hours} HRS</span></div><h3>{rec.title || rec.event_title}</h3><div className="rec-tags">{rec.critical && <span className="critical-tag">Critical for next grade</span>}{(rec.closes_skills || []).map(id => <span className="skill-chip" key={id}>{skillName(id)}</span>)}</div><p className="rationale">{rec.rationale || 'A learning opportunity matched to your development plan.'}</p><button className="button-primary complete-button" disabled={!!completing} onClick={() => complete(rec)}>{completing === rec.event_id ? <><span className="button-spinner"/> Saving progress…</> : <>Mark as completed <span>→</span></>}</button></div></article>)}</div>}
      </section>
    </div>
    <section className="panel history-panel"><div className="section-heading"><div><div className="eyebrow">YOUR LEARNING JOURNEY</div><h2>Activity history</h2></div><span className="small-count">{history.length} ACTIVITIES</span></div>
      {!history.length ? <p className="muted empty-history">Your completed and ongoing activities will appear here.</p> : <div className="table-scroll"><table><thead><tr><th>ACTIVITY</th><th>DATE</th><th>STATUS</th><th>SCORE</th><th>FEEDBACK</th></tr></thead><tbody>{history.map((item, index) => { const status = (item.status || 'in_progress').toLowerCase(); const tone = status === 'completed' ? 'green' : ['declined', 'no_show'].includes(status) ? 'red' : 'yellow'; return <tr key={item.record_id || `${item.event_id}-${index}`}><td><strong>{item.event_title || item.title || item.event_id}</strong></td><td>{item.date || '—'}</td><td><span className={`status-badge ${tone}`}>{status.replaceAll('_', ' ')}</span></td><td>{item.score ?? '—'}</td><td className="stars">{item.feedback_rating ? '★'.repeat(Math.min(5, item.feedback_rating)) + '☆'.repeat(5 - Math.min(5, item.feedback_rating)) : '—'}</td></tr>; })}</tbody></table></div>}
    </section>
  </div>;
}
