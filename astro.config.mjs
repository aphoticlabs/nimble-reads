import { defineConfig } from 'astro/config';

// Project sites are served from /<repo-name>/. The workflow derives this from
// the repo; override to '/' for a user site or custom domain.
const base = process.env.BASE_PATH ?? '/nimble-reads';

export default defineConfig({
  base,
  trailingSlash: 'ignore',
  build: {
    format: 'file',
    // Astro inlines small stylesheets by default, which would repeat the whole
    // sheet across 1001 pages instead of caching it once.
    inlineStylesheets: 'never',
  },
});
