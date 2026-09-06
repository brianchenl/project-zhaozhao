import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';
import { schemas } from './lib/content-schema.mjs';

export const collections = {
  facts: defineCollection({ loader: glob({ pattern: '**/*.md', base: './src/content/facts' }), schema: schemas.facts }),
  claims: defineCollection({ loader: glob({ pattern: '**/*.md', base: './src/content/claims' }), schema: schemas.claims }),
  ledger: defineCollection({ loader: glob({ pattern: '**/*.md', base: './src/content/ledger' }), schema: schemas.ledger })
};
