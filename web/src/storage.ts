// Per-viewer conveniences only (theme, user id, open tab).
export function load(key: string, fallback: string): string {
  try {
    return localStorage.getItem(`quintessa.${key}`) ?? fallback;
  } catch {
    return fallback;
  }
}

export function save(key: string, value: string): void {
  try {
    localStorage.setItem(`quintessa.${key}`, value);
  } catch {
    /* storage unavailable */
  }
}
