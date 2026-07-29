const raw = import.meta.env.BASE_URL;
const base = raw.endsWith('/') ? raw : `${raw}/`;

export const url = (path = '') => base + path.replace(/^\//, '');
export const bookUrl = (id) => url(`books/${id}.html`);
