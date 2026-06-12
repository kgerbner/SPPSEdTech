/**
 * Build an internal link that respects the GitHub Pages base path.
 * href('/history/') -> '/SPPSEdTech/history/'
 * If the site later moves to a custom domain, only astro.config.mjs changes.
 */
export function href(path: string): string {
  const base = import.meta.env.BASE_URL.replace(/\/$/, '');
  return `${base}${path.startsWith('/') ? path : `/${path}`}`;
}
