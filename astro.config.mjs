// @ts-check
import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

export default defineConfig({
  site: 'https://r18-blog.pages.dev',
  integrations: [sitemap()],
  build: { assets: '_assets' },
});
