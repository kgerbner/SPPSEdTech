import { defineCollection, z } from 'astro:content';
import { file } from 'astro/loaders';
import { parse } from 'yaml';

const yamlParser = (text: string) => parse(text);

const source = z.object({
  label: z.string(),
  url: z.string().url(),
});

const timeline = defineCollection({
  loader: file('src/data/timeline.yaml', { parser: yamlParser }),
  schema: z.object({
    id: z.string(),
    date: z.coerce.string().regex(/^\d{4}(-\d{2})?$/, 'date must be YYYY or YYYY-MM'),
    dateDisplay: z.string(),
    title: z.string(),
    category: z.enum(['devices', 'funding', 'policy', 'state-law', 'covid', 'context']),
    body: z.string(),
    sources: z.array(source).min(1, 'every timeline entry needs at least one source'),
  }),
});

const districts = defineCollection({
  loader: file('src/data/districts.yaml', {
    parser: (text) => parse(text).map((d: { name: string }) => ({ id: d.name, ...d })),
  }),
  schema: z.object({
    name: z.string(),
    location: z.string(),
    summary: z.string(),
    highlights: z.array(z.string()).optional(),
    sources: z.array(source).min(1, 'every district entry needs at least one source'),
  }),
});

const resources = defineCollection({
  loader: file('src/data/resources.yaml', {
    parser: (text) => parse(text).map((s: { section: string }) => ({ id: s.section, ...s })),
  }),
  schema: z.object({
    section: z.enum(['books', 'research', 'articles', 'organizations']),
    items: z.array(
      z.object({
        title: z.string(),
        author: z.string(),
        year: z.number(),
        url: z.string().url(),
        why: z.string(),
      })
    ),
  }),
});

export const collections = { timeline, districts, resources };
