const employees = {
  EMP_001: { employee_id: 'EMP_001', full_name: 'Aigerim Sadykova', department: 'Retail Banking', role: 'Relationship Manager', grade: 'Junior', tenure_months: 18, preferred_language: 'en', skills: { communication: 2, 'customer-advisory': 2, 'risk-awareness': 3, 'data-literacy': 1 }, activity_history: [
    { record_id: 'ACT_1001', event_id: 'EV_014', event_title: 'Customer Conversations That Build Trust', date: '2026-08-14', status: 'completed', score: 88, feedback_rating: 5 },
    { record_id: 'ACT_1002', event_id: 'EV_006', event_title: 'Foundations of Risk Awareness', date: '2026-07-20', status: 'in_progress', completion_pct: 60 },
  ] },
  EMP_002: { employee_id: 'EMP_002', full_name: 'Timur Bekov', department: 'Digital Products', role: 'Product Analyst', grade: 'Middle', tenure_months: 42, preferred_language: 'ru', skills: { 'data-literacy': 4, communication: 3, 'risk-awareness': 3, collaboration: 2 }, activity_history: [] },
};
const recs = {
  EMP_001: [
    { event_id: 'EV_021', title: 'Data Stories for Better Decisions', rationale: 'Your data literacy is currently at level 1, while the next grade expects level 3. This self-paced activity can close two levels of that gap and strengthen a skill needed for your progression.', score: 7.8, closes_skills: ['data-literacy'], critical: true, duration_hours: 3, format: 'self-paced' },
    { event_id: 'EV_018', title: 'Advisory Skills Workshop', rationale: 'You have a two-level gap in customer advisory. This practical workshop builds the skill through guided client scenarios and helps prepare you for the expectations of the next grade.', score: 6.4, closes_skills: ['customer-advisory'], critical: false, duration_hours: 4, format: 'offline' },
    { event_id: 'EV_027', title: 'Communicate with Confidence', rationale: 'Communication is an important next-grade skill, and your current level leaves room to grow. This online course provides focused practice in clear, confident conversations.', score: 5.9, closes_skills: ['communication'], critical: true, duration_hours: 2, format: 'online' },
  ],
  EMP_002: [
    { event_id: 'EV_031', title: 'Collaborative Product Discovery', rationale: 'Your collaboration skill is at level 2, below the next-grade expectation of level 3. This workshop builds practical habits for working across teams and closes part of the gap.', score: 5.2, closes_skills: ['collaboration'], critical: false, duration_hours: 3, format: 'offline' },
  ],
};
const skillNames = { communication: 'Communication', 'customer-advisory': 'Customer advisory', 'risk-awareness': 'Risk awareness', 'data-literacy': 'Data literacy', collaboration: 'Collaboration' };

export const mockGetEmployee = async id => { await delay(250); const value = employees[id]; if (!value) throw new Error(`Employee ${id} was not found in demo data. Try EMP_001 or EMP_002.`); return structuredClone(value); };
export const mockGetRecommendations = async id => { await delay(750); if (!employees[id]) throw new Error('Employee not found.'); return { employee_id: id, recommendations: structuredClone(recs[id] || []) }; };
export const mockCompleteActivity = async (id, eventId) => {
  await delay(500); const employee = employees[id]; const recommendation = (recs[id] || []).find(item => item.event_id === eventId);
  if (!employee || !recommendation) throw new Error('That activity is no longer available. Refresh and try again.');
  for (const skill of recommendation.closes_skills) employee.skills[skill] = Math.min(5, (employee.skills[skill] || 0) + (skill === 'data-literacy' ? 2 : 1));
  employee.activity_history.unshift({ record_id: `ACT_${Date.now()}`, event_id: eventId, event_title: recommendation.title, date: new Date().toISOString().slice(0, 10), status: 'completed', score: 100, feedback_rating: 5 });
  recs[id] = recs[id].filter(item => item.event_id !== eventId);
  return { employee, recommendations: { employee_id: id, recommendations: structuredClone(recs[id]) } };
};
export const mockGetHrSkillGaps = async () => { await delay(450); return [
  { skill_id: 'data-literacy', skill_name: 'Data literacy', total_gap: 84, employees_affected: 31 }, { skill_id: 'customer-advisory', skill_name: 'Customer advisory', total_gap: 69, employees_affected: 28 }, { skill_id: 'communication', skill_name: 'Communication', total_gap: 55, employees_affected: 24 }, { skill_id: 'risk-awareness', skill_name: 'Risk awareness', total_gap: 42, employees_affected: 19 }, { skill_id: 'collaboration', skill_name: 'Collaboration', total_gap: 34, employees_affected: 16 },
]; };
export const mockGetHrEmployeesWithoutRecommendation = async () => { await delay(350); return [{ employee_id: 'EMP_014', full_name: 'Daniyar Omarov', role: 'Branch Manager', grade: 'Lead' }, { employee_id: 'EMP_026', full_name: 'Madina Tulegen', role: 'Risk Specialist', grade: 'Senior' }]; };
export const mockGetHrParticipationStats = async () => { await delay(550); return [
  { event_id: 'EV_014', title: 'Customer Conversations That Build Trust', completed: 46, declined: 4, no_show: 3, dropped: 5, in_progress: 12 }, { event_id: 'EV_021', title: 'Data Stories for Better Decisions', completed: 38, declined: 7, no_show: 4, dropped: 3, in_progress: 16 }, { event_id: 'EV_006', title: 'Foundations of Risk Awareness', completed: 52, declined: 2, no_show: 1, dropped: 2, in_progress: 8 }, { event_id: 'EV_018', title: 'Advisory Skills Workshop', completed: 29, declined: 9, no_show: 6, dropped: 8, in_progress: 7 },
]; };
export const mockImportData = async payload => {
  await delay(500);
  const isEmployees = payload.type === 'employees' || Array.isArray(payload.employees);
  const rows = isEmployees ? (payload.employees || payload.records || []) : (payload.activity_history || payload.records || []);
  if (isEmployees) {
    for (const row of rows) {
      employees[row.employee_id] = { ...structuredClone(row), activity_history: row.activity_history || [] };
      recs[row.employee_id] = [];
    }
  } else {
    for (const row of rows) {
      const employee = employees[row.employee_id];
      if (employee) employee.activity_history.unshift({ ...row, event_title: row.event_title || row.event_id });
    }
  }
  return { imported: rows.length, count: rows.length };
};
export const getSkillName = id => skillNames[id] || id.replaceAll('-', ' ').replace(/\b\w/g, c => c.toUpperCase());
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
