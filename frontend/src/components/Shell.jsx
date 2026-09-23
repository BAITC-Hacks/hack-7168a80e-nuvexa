import React from 'react';
import { defaultEmployeeId } from '../lib/data.js';

export function Shell({ path, navigate, children }) {
  const [employeeId, setEmployeeId] = React.useState(defaultEmployeeId);
  React.useEffect(() => {
    const match = path.match(/^\/employee\/([^/]+)$/);
    if (match) setEmployeeId(decodeURIComponent(match[1]));
    else if (path === '/') setEmployeeId(defaultEmployeeId);
  }, [path]);
  const current = path.startsWith('/hr') ? 'hr' : path.startsWith('/import') ? 'import' : 'employee';
  const jump = event => { event.preventDefault(); if (employeeId.trim()) navigate(`/employee/${encodeURIComponent(employeeId.trim())}`); };
  return <div className="app-shell">
    <header className="topbar"><a className="brand" href="/" onClick={e => { e.preventDefault(); navigate('/'); }}><span className="brand-mark">cq</span><span>career<span className="brand-light">quest</span><small>PEOPLE DEVELOPMENT</small></span></a>
      <nav className="main-nav" aria-label="Main navigation"><button className={current === 'employee' ? 'nav-link active' : 'nav-link'} onClick={() => navigate('/')}>Employee view</button><button className={current === 'hr' ? 'nav-link active' : 'nav-link'} onClick={() => navigate('/hr')}>HR dashboard</button><button className={current === 'import' ? 'nav-link active' : 'nav-link'} onClick={() => navigate('/import')}>Import data</button></nav>
      <form className="jump-form" onSubmit={jump}><span className="search-icon">⌕</span><input value={employeeId} onChange={e => setEmployeeId(e.target.value)} aria-label="Employee ID" placeholder="Employee ID"/><button type="submit" aria-label="Open employee">↗</button></form>
      <div className="avatar" aria-label="HR workspace">CQ</div>
    </header>
    <main>{children}</main>
    <footer className="footer"><span>CAREER QUEST <span className="dot">•</span> EMPLOYEE DEVELOPMENT</span><span>Build a career with intention.</span></footer>
  </div>;
}

export function PageHeading({ eyebrow, title, subtitle, action }) { return <div className="page-heading"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1>{subtitle && <p>{subtitle}</p>}</div>{action}</div>; }
export function ErrorNotice({ message, onRetry }) { if (!message) return null; return <div className="error-notice" role="alert"><span>{message}</span>{onRetry && <button className="text-button" onClick={onRetry}>Try again</button>}</div>; }
export function Skeleton({ rows = 3 }) { return <div className="skeleton-stack" aria-label="Loading">{Array.from({ length: rows }, (_, i) => <div key={i} className="skeleton-row"><i/><span><b/><em/></span><b/></div>)}</div>; }
