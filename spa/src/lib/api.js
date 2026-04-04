/**
 * API client for /api/* endpoints.
 * Handles GET (query params) and POST (JSON body) methods.
 * Returns parsed JSON on success, throws on error with detail message.
 */
export async function apiCall(endpoint, params = {}, method = 'GET') {
  let url = `/api/${endpoint}`;
  let options = { headers: {} };

  if (method === 'POST') {
    options.method = 'POST';
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(params);
  } else {
    // Build query string from params, omitting null/undefined/empty
    const searchParams = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== null && value !== undefined && value !== '') {
        searchParams.set(key, String(value));
      }
    }
    const qs = searchParams.toString();
    if (qs) url += `?${qs}`;
  }

  const response = await fetch(url, options);

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {}
    throw new Error(detail);
  }

  return response.json();
}
