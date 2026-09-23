const BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
const TIMEOUT_MS = 12_000;

export class ApiError extends Error {
  constructor(message, status, body) { super(message); this.name = 'ApiError'; this.status = status; this.body = body; }
}

async function request(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const response = await fetch(`${BASE_URL}${path}`, {
      ...options, signal: controller.signal,
      headers: { ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...options.headers },
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
    throw new ApiError(error.message || 'Unable to reach the server.', 0);
  } finally { clearTimeout(timeout); }
}

export const getEmployee = id => request(`/employees/${encodeURIComponent(id)}`);
export const getRecommendations = id => request(`/employees/${encodeURIComponent(id)}/recommendations`);
export const completeActivity = (employeeId, eventId) => request(`/employees/${encodeURIComponent(employeeId)}/activities/${encodeURIComponent(eventId)}/complete`, { method: 'POST' });
export const getHrSkillGaps = () => request('/hr/skill-gaps');
export const getHrEmployeesWithoutRecommendation = () => request('/hr/employees-without-recommendation');
export const getHrParticipationStats = () => request('/hr/participation-stats');
export const importData = payload => request('/data/import', { method: 'POST', body: JSON.stringify(payload) });
