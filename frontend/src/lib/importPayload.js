export const activityColumns = [
  'record_id', 'employee_id', 'event_id', 'date', 'due_date', 'status',
  'completion_pct', 'score', 'feedback_rating', 'assigned_by',
];

export const employeeFields = [
  'employee_id', 'full_name', 'department', 'role', 'grade', 'hire_date',
  'tenure_months', 'work_format', 'preferred_language', 'skills',
];

export const historyFields = [
  'record_id', 'employee_id', 'event_id', 'date', 'status', 'completion_pct', 'assigned_by',
];

// Inspect only the header. The backend's CSV parser owns record parsing and
// conversion, including quoted newlines, nullable values and numeric ratings.
function validateCsvHeader(text) {
  const source = text.replace(/^\uFEFF+/, '');
  const header = [];
  let cell = '', quoted = false, position = 0;
  for (; position < source.length; position++) {
    const character = source[position];
    if (character === '"') {
      if (quoted && source[position + 1] === '"') { cell += '"'; position++; }
      else quoted = !quoted;
    } else if (!quoted && character === ',') {
      header.push(cell); cell = '';
    } else if (!quoted && (character === '\r' || character === '\n')) {
      break;
    } else cell += character;
  }
  header.push(cell);
  if (quoted || header.length !== activityColumns.length || header.some((name, index) => name !== activityColumns[index])) {
    throw new Error(`CSV header must match this exact column order: ${activityColumns.join(', ')}.`);
  }
  if (!source.slice(position).trim()) throw new Error('CSV has a header but no records.');
}

export function createImportPayload(text, selectedType) {
  if (!text.trim()) throw new Error('Choose a file or paste data to continue.');
  const type = selectedType === 'activity_history' ? 'history' : selectedType;
  if (type !== 'employees' && type !== 'history') throw new Error('Choose employees or activity history.');

  const source = text.replace(/^\uFEFF+/, '');
  if (type === 'history' && !/^[\[{]/.test(source.trimStart())) {
    validateCsvHeader(text);
    return { payload: { type, data: text }, firstEmployeeId: null };
  }

  let parsed;
  try { parsed = JSON.parse(source); }
  catch (error) { throw new Error(`Invalid JSON: ${error.message}`); }

  const wrappers = type === 'employees' ? ['employees'] : ['history', 'activity_history', 'records'];
  let records = parsed;
  if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
    const keys = wrappers.filter(key => Object.hasOwn(parsed, key));
    if (keys.length !== 1 || Object.keys(parsed).some(key => key !== keys[0] && key !== 'meta')) {
      throw new Error(`Expected one ${wrappers.join(' or ')} array, with optional meta information.`);
    }
    records = parsed[keys[0]];
  }
  if (!Array.isArray(records) || !records.length) {
    throw new Error(`Expected a non-empty array of ${type === 'employees' ? 'employee' : 'activity'} records.`);
  }
  const fields = type === 'employees' ? employeeFields : historyFields;
  records.forEach((record, index) => {
    if (!record || typeof record !== 'object' || Array.isArray(record)) {
      throw new Error(`Record ${index + 1} must be an object.`);
    }
    const missing = fields.filter(field => !Object.hasOwn(record, field));
    if (missing.length) throw new Error(`Record ${index + 1} is missing fields: ${missing.join(', ')}.`);
  });

  return { payload: { type, data: records }, firstEmployeeId: type === 'employees' ? records[0].employee_id : null };
}
