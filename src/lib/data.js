import * as api from './api.js';
import * as mock from './MockData.js';

export const useMocks = import.meta.env.VITE_USE_MOCK_DATA !== 'false';
const source = useMocks ? {
  getEmployee: mock.mockGetEmployee, getRecommendations: mock.mockGetRecommendations, completeActivity: mock.mockCompleteActivity,
  getHrSkillGaps: mock.mockGetHrSkillGaps, getHrEmployeesWithoutRecommendation: mock.mockGetHrEmployeesWithoutRecommendation,
  getHrParticipationStats: mock.mockGetHrParticipationStats, importData: mock.mockImportData,
} : api;
export const data = source;
export const getSkillName = mock.getSkillName;
export const normalizeList = result => Array.isArray(result) ? result : result?.items || result?.results || result?.data || [];
