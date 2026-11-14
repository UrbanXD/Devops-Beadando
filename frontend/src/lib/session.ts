const TOKEN_KEY = "converter_access_token";
const RETURN_TO_WORKSPACE_KEY = "return_to_workspace";

export function getAccessToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function saveAccessToken(token: string): void {
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearAccessToken(): void {
  sessionStorage.removeItem(TOKEN_KEY);
}

export function markWorkspaceReturn(): void {
  sessionStorage.setItem(RETURN_TO_WORKSPACE_KEY, "true");
}

export function consumeWorkspaceReturn(): boolean {
  const shouldReturn = sessionStorage.getItem(RETURN_TO_WORKSPACE_KEY) === "true";
  sessionStorage.removeItem(RETURN_TO_WORKSPACE_KEY);
  return shouldReturn;
}
