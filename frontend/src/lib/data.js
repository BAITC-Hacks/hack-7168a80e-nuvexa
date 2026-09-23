import * as api from './api.js';
import * as mock from './MockData.js';

export const useMocks = import.meta.env.VITE_USE_MOCK_DATA === 'true';
export const defaultEmployeeId = import.meta.env.VITE_DEFAULT_EMPLOYEE_ID || (useMocks ? 'EMP_001' : 'E0001');
const source = useMocks ? {
  getSkills: mock.mockGetSkills,
  getEmployee: mock.mockGetEmployee, getRecommendations: mock.mockGetRecommendations, completeActivity: mock.mockCompleteActivity,
  getHrSkillGaps: mock.mockGetHrSkillGaps, getHrEmployeesWithoutRecommendation: mock.mockGetHrEmployeesWithoutRecommendation,
  getHrParticipationStats: mock.mockGetHrParticipationStats, importData: mock.mockImportData,
} : api;
export const data = source;
export const getSkillName = (id, names = {}) => names[id] || id.replace(/^SK_/, '').replaceAll('_', ' ').replaceAll('-', ' ').replace(/\b\w/g, c => c.toUpperCase());
export const normalizeList = result => Array.isArray(result) ? result : result?.items || result?.results || result?.data || [];
