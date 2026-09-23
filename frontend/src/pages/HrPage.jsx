import React from 'react';
import { data, normalizeList } from '../lib/data.js';
import { ErrorNotice, PageHeading, Skeleton } from '../components/Shell.jsx';

const participationStatuses = [
  { key: 'completed', label: 'Completed', className: 'legend-completed' },
  { key: 'declined', label: 'Declined', className: 'legend-declined' },
  { key: 'no_show', label: 'No-show', className: 'legend-noshow' },
  { key: 'dropped', label: 'Dropped', className: 'legend-dropped' },
  { key: 'in_progress', label: 'In progress', className: 'legend-inprogress' },
  { key: 'overdue', label: 'Overdue', className: 'legend-overdue' },
];

function useSection(loader, refreshKey) {
  const [value, setValue] = React.useState([]);
  const [error, setError] = React.useState('');
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    let live = true;
    setLoading(true);
    setError('');
    loader()
      .then(result => { if (live) setValue(normalizeList(result)); })
      .catch(err => { if (live) setError(err.message || 'Unable to load this report. Please try again.'); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [loader, refreshKey]);

  return { value, error, loading };
}

function SectionContent({ section, rows = 4, emptyMessage, onRetry, children }) {
  if (section.loading) return <Skeleton rows={rows}/>;
  if (section.error) return <ErrorNotice message={section.error} onRetry={onRetry}/>;
  if (!section.value.length) return <p className="hr-empty" role="status">{emptyMessage}</p>;
  return children;
}

export default function HrPage() {
  const [refreshKey, setRefreshKey] = React.useState(0);
  const refresh = () => setRefreshKey(key => key + 1);
  const loadGaps = React.useCallback(() => data.getHrSkillGaps(), []);
  const loadPeople = React.useCallback(() => data.getHrEmployeesWithoutRecommendation(), []);
  const loadStats = React.useCallback(() => data.getHrParticipationStats(), []);
  const gaps = useSection(loadGaps, refreshKey);
  const people = useSection(loadPeople, refreshKey);
  const stats = useSection(loadStats, refreshKey);
  const loading = gaps.loading || people.loading || stats.loading;
  const maxGap = Math.max(1, ...gaps.value.map(gap => Number(gap.total_gap || 0)));

  return <div className="page-wrap">
    <PageHeading
      eyebrow="PEOPLE INSIGHTS"
      title="Grow the whole team."
      subtitle="Spot development needs across the organization and make the next conversation count."
      action={<button className="button-secondary" onClick={refresh} disabled={loading}><span className="refresh-icon" aria-hidden="true">↻</span> {loading ? 'Refreshing…' : 'Refresh data'}</button>}
    />
    <div className="hr-grid">
      <section className="panel hr-panel gaps-panel" aria-busy={gaps.loading}>
        <div className="section-heading"><div><div className="eyebrow">CAPABILITY OVERVIEW</div><h2>Skill gaps across the company</h2></div><span className="small-count">TOP 15</span></div>
        <p className="muted">Combined gap score and number of people affected.</p>
        <SectionContent section={gaps} rows={5} emptyMessage="No skill gaps to report." onRetry={refresh}>
          <div className="gap-list">
            {gaps.value.slice().sort((a, b) => b.total_gap - a.total_gap).slice(0, 15).map((gap, index) => <div className="gap-row" key={gap.skill_id}>
              <div className="gap-label"><span className="rank-index">{String(index + 1).padStart(2, '0')}</span><strong title={gap.skill_name || gap.skill_id}>{gap.skill_name || gap.skill_id}</strong><small>{gap.employees_affected} people</small></div>
              <div className="gap-meter" aria-hidden="true"><i style={{ width: `${Number(gap.total_gap || 0) / maxGap * 100}%` }}/></div>
              <b className="gap-number">{gap.total_gap}</b>
            </div>)}
          </div>
        </SectionContent>
      </section>
      <section className="panel hr-panel people-panel" aria-busy={people.loading}>
        <div className="section-heading"><div><div className="eyebrow">PERSONALIZED FOLLOW-UP</div><h2>Employees without a next step</h2></div><span className="people-count">{people.loading || people.error ? '—' : people.value.length}</span></div>
        <p className="muted">These employees are either at the top grade or have no eligible activity right now and may need a manual check-in.</p>
        <SectionContent section={people} emptyMessage="Every employee currently has a recommended next step." onRetry={refresh}>
          <div className="people-list">
            {people.value.map(person => <a className="person-row" href={`/employee/${encodeURIComponent(person.employee_id)}`} key={person.employee_id}>
              <span className="person-avatar" aria-hidden="true">{(person.full_name || person.employee_id).split(/\s+/).map(part => part[0]).slice(0, 2).join('')}</span>
              <span className="person-details"><strong>{person.full_name || person.employee_id}</strong><small>{person.role}</small></span>
              <span className="grade-badge">{person.grade}</span><span className="row-arrow" aria-hidden="true">↗</span>
            </a>)}
          </div>
        </SectionContent>
      </section>
    </div>
    <section className="panel hr-panel participation-panel" aria-busy={stats.loading}>
      <div className="section-heading">
        <div><div className="eyebrow">LEARNING ENGAGEMENT</div><h2>Participation by activity</h2></div>
        <div className="legend">{participationStatuses.map(status => <span key={status.key}><i className={status.className}/>{status.label}</span>)}</div>
      </div>
      <SectionContent section={stats} emptyMessage="No participation records to report yet." onRetry={refresh}>
        <div className="participation-scroll" tabIndex={0} role="region" aria-label="Participation by activity, scroll horizontally for all statuses">
          <div className="participation-table" role="table" aria-label="Activity participation counts">
            <div className="participation-header" role="row"><span role="columnheader">Activity</span>{participationStatuses.map(status => <span role="columnheader" key={status.key}>{status.label}</span>)}<span role="columnheader">Total</span></div>
            {stats.value.map(row => {
              // The live API provides total; the sum also supports optional demo fixtures.
              const total = row.total ?? participationStatuses.reduce((sum, status) => sum + Number(row[status.key] || 0), 0);
              return <div className="participation-row" role="row" key={row.event_id}>
                <strong role="rowheader">{row.title || row.event_id}</strong>
                {participationStatuses.map(status => <span role="cell" key={status.key}>{row[status.key] || 0}</span>)}
                <span className="participation-total" role="cell">{total}</span>
                <div className="stacked-bar" aria-hidden="true">
                  {participationStatuses.map(status => <i key={status.key} className={status.className} style={{ width: `${total > 0 ? Number(row[status.key] || 0) / total * 100 : 0}%` }}/>) }
                </div>
              </div>;
            })}
          </div>
        </div>
      </SectionContent>
    </section>
  </div>;
}
