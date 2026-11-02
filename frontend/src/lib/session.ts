const KEY = "bt-session-token";

export const session = {
  token: (): string | null => localStorage.getItem(KEY),
  set: (token: string) => localStorage.setItem(KEY, token),
  clear: () => localStorage.removeItem(KEY),
};

export const AUTH_EXPIRED = "auth:expired";
