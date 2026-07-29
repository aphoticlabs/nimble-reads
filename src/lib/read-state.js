const KEY = 'nimble-reads:read';

export function getRead() {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY));
    return new Set(Array.isArray(raw) ? raw : []);
  } catch {
    return new Set();
  }
}

export function isRead(id) {
  return getRead().has(id);
}

export function toggleRead(id) {
  const read = getRead();
  read.has(id) ? read.delete(id) : read.add(id);
  try {
    localStorage.setItem(KEY, JSON.stringify([...read]));
  } catch {}
  return read.has(id);
}
