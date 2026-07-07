import { defineConfig, defineDocs } from 'fumadocs-mdx/config';
import { metaSchema, pageSchema } from 'fumadocs-core/source/schema';

// You can customize Zod schemas for frontmatter and `meta.json` here
// see https://fumadocs.dev/docs/mdx/collections
export const docs = defineDocs({
  dir: 'content/docs',
  docs: {
    schema: pageSchema,
    postprocess: {
      includeProcessedMarkdown: true,
    },
  },
  meta: {
    schema: metaSchema,
  },
});

// Two-tone monochrome code themes: ink for code, mute for the parts you skim
// past (comments, strings, punctuation) — the last color on the site removed.
function monochromeTheme(name: string, type: 'light' | 'dark', ink: string, mute: string) {
  return {
    name,
    type,
    colors: {
      'editor.background': 'transparent',
      'editor.foreground': ink,
    },
    tokenColors: [
      { settings: { foreground: ink } },
      {
        scope: ['comment', 'punctuation.definition.comment'],
        settings: { foreground: mute, fontStyle: 'italic' },
      },
      {
        scope: ['string', 'string.quoted', 'constant.numeric', 'constant.language'],
        settings: { foreground: mute },
      },
      {
        scope: ['keyword', 'storage.type', 'storage.modifier', 'keyword.control'],
        settings: { foreground: ink, fontStyle: 'bold' },
      },
      {
        scope: ['punctuation', 'meta.brace'],
        settings: { foreground: mute },
      },
    ],
  };
}

export default defineConfig({
  mdxOptions: {
    rehypeCodeOptions: {
      themes: {
        light: monochromeTheme('bt-light', 'light', '#292929', '#8a8a8a'),
        dark: monochromeTheme('bt-dark', 'dark', '#ebebeb', '#7d7d7d'),
      },
    },
  },
});
