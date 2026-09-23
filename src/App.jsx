import React from 'react';
import { Shell } from './components/Shell.jsx';
import EmployeePage from './pages/EmployeePage.jsx';
import HrPage from './pages/HrPage.jsx';
import ImportPage from './pages/ImportPage.jsx';

function readPath() { return window.location.pathname.replace(/\/$/, '') || '/'; }
export default function App() {
  const [path, setPath] = React.useState(readPath);
  React.useEffect(() => { const listener = () => setPath(readPath()); window.addEventListener('popstate', listener); return () => window.removeEventListener('popstate', listener); }, []);
  const navigate = next => { if (next !== readPath()) { window.history.pushState({}, '', next); setPath(readPath()); window.scrollTo({ top: 0, behavior: 'smooth' }); } };
  const match = path.match(/^\/employee\/([^/]+)$/); let page;
  if (path === '/hr') page = <HrPage/>;
  else if (path === '/import') page = <ImportPage navigate={navigate}/>;
  else if (match) page = <EmployeePage key={decodeURIComponent(match[1])} employeeId={decodeURIComponent(match[1])}/>;
  else page = <EmployeePage key="EMP_001" employeeId="EMP_001"/>;
  return <Shell path={path} navigate={navigate}>{page}</Shell>;
}
