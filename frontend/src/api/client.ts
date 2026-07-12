export const API_BASE = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") || "";

function authHeaders(token?: string | null): HeadersInit {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function readError(response: Response) {
  const text = await response.text();
  try {
    const parsed = JSON.parse(text);
    return typeof parsed.detail === "string" ? parsed.detail : JSON.stringify(parsed.detail || parsed);
  } catch {
    return text || response.statusText;
  }
}

export async function loginAccess(email: string, password: string) {
  const response = await fetch(`${API_BASE}/api/access/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password })
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function verifySession(token: string) {
  const response = await fetch(`${API_BASE}/api/access/session`, {
    headers: authHeaders(token),
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function logoutAccess(token: string) {
  await fetch(`${API_BASE}/api/access/logout`, {
    method: "POST",
    headers: authHeaders(token),
  });
}

export async function validationHistory(token: string) {
  const response = await fetch(`${API_BASE}/api/validations/history`, {
    headers: authHeaders(token),
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function openValidation(runId: string, token: string) {
  const response = await fetch(`${API_BASE}/api/validations/${encodeURIComponent(runId)}`, {
    headers: authHeaders(token),
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function runDemo(token: string) {
  const response = await fetch(`${API_BASE}/api/demo/run`, {
    method: "POST",
    headers: authHeaders(token),
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function runFiveCaseDemo(token: string) {
  const response = await fetch(`${API_BASE}/api/demo/run-five-case`, {
    method: "POST",
    headers: authHeaders(token),
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function uploadRun(form: FormData, token: string) {
  const response = await fetch(`${API_BASE}/api/validation/upload-run`, {
    method: "POST",
    headers: authHeaders(token),
    body: form
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function uploadBatchRun(form: FormData, token: string) {
  const response = await fetch(`${API_BASE}/api/validation/upload-batch-run`, {
    method: "POST",
    headers: authHeaders(token),
    body: form
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}
