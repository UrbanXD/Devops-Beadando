const TOKEN_KEY = "converter_access_token";
const RETURN_TO_WORKSPACE_KEY = "return_to_workspace";
let refreshInFlight: Promise<string | null> | null = null;

export function getAccessToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function saveAccessToken(token: string): void {
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearAccessToken(): void {
  sessionStorage.removeItem(TOKEN_KEY);
}

export async function refreshAccessToken(): Promise<string | null> {
  if (refreshInFlight) return refreshInFlight;

  const request = (async () => {
    try {
      const response = await fetch("/api/auth/refresh", {
        method: "POST",
        credentials: "include",
      });
      if (!response.ok) {
        clearAccessToken();
        return null;
      }

      const body = (await response.json()) as { access_token?: unknown };
      if (typeof body.access_token !== "string" || !body.access_token) {
        clearAccessToken();
        return null;
      }

      saveAccessToken(body.access_token);
      return body.access_token;
    } catch {
      clearAccessToken();
      return null;
    }
  })();

  refreshInFlight = request;
  try {
    return await request;
  } finally {
    if (refreshInFlight === request) refreshInFlight = null;
  }
}

export async function getActiveAccessToken(): Promise<string | null> {
  return getAccessToken() ?? refreshAccessToken();
}

export async function authenticatedFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<Response> {
  const makeRequest = (token: string | null) => {
    const headers = new Headers(init.headers);
    if (token) headers.set("Authorization", `Bearer ${token}`);
    return fetch(input, { ...init, headers, credentials: "include" });
  };

  let token = getAccessToken();
  if (!token) {
    token = await refreshAccessToken();
    if (!token) return makeRequest(null);
  }

  const response = await makeRequest(token);
  if (response.status !== 401) return response;

  const refreshedToken = await refreshAccessToken();
  return refreshedToken ? makeRequest(refreshedToken) : response;
}

export function markWorkspaceReturn(): void {
  sessionStorage.setItem(RETURN_TO_WORKSPACE_KEY, "true");
}

export function consumeWorkspaceReturn(): boolean {
  const shouldReturn = sessionStorage.getItem(RETURN_TO_WORKSPACE_KEY) === "true";
  sessionStorage.removeItem(RETURN_TO_WORKSPACE_KEY);
  return shouldReturn;
}
