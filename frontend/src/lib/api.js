const BASE_URL = import.meta.env?.VITE_API_BASE_URL || 'http://127.0.0.1:8000';
const TIMEOUT_MS = 12_000;

export class ApiError extends Error {
  constructor(message, status, body) { super(message); this.name = 'ApiError'; this.status = status; this.body = body; }
}

export function createApiClient(baseUrl = BASE_URL, timeoutMs = TIMEOUT_MS) {
  const origin = baseUrl.replace(/\/+$/, '');
  async function request(path, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(`${origin}${path}`, {
        ...options, signal: controller.signal,
        headers: { ...(options.body && !(options.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}), ...options.headers },
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) {
        const detail = body?.detail || body?.message;
        const message = Array.isArray(detail)
          ? detail.map(item => typeof item === 'string' ? item : item?.msg || JSON.stringify(item)).join('; ')
          : typeof detail === 'string' ? detail : `Request failed (${response.status})`;
        throw new ApiError(message, response.status, body);
      }
      return body;
    } catch (error) {
      if (error.name === 'AbortError') throw new ApiError('The request timed out. Please try again.', 0);
      if (error instanceof ApiError) throw error;
      throw new ApiError('Unable to reach the backend. Check that the API is running and its address is correct, then try again.', 0);
    } finally { clearTimeout(timeout); }
  }

  return {
    getEmployee: id => request(`/employees/${encodeURIComponent(id)}`),
    getSkills: () => request('/skills'),
    getRecommendations: id => request(`/employees/${encodeURIComponent(id)}/recommendations`),
    completeActivity: (employeeId, eventId) => request(`/employees/${encodeURIComponent(employeeId)}/activities/${encodeURIComponent(eventId)}/complete`, { method: 'POST' }),
    getHrSkillGaps: () => request('/hr/skill-gaps'),
    getHrEmployeesWithoutRecommendation: () => request('/hr/employees-without-recommendation'),
    getHrParticipationStats: () => request('/hr/participation-stats'),
    importData: payload => request('/data/import', { method: 'POST', body: JSON.stringify(payload) }),
  };
}

export const {
  getEmployee, getSkills, getRecommendations, completeActivity, getHrSkillGaps,
  getHrEmployeesWithoutRecommendation, getHrParticipationStats, importData,
} = createApiClient();
