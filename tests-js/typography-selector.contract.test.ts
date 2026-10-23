import assert from 'node:assert/strict'
import { createRequire } from 'node:module'

import { test } from 'vitest'

interface TypographySelectorConsumer {
  commonTrailingPseudos: (selector: string) => [string | null, string]
}

const { commonTrailingPseudos } = createRequire(import.meta.url)(
  '@tailwindcss/typography/src/utils'
) as TypographySelectorConsumer

const selectors: [string, string | null, string][] = [
  ['p::before, a::before', '::before', 'p, a'],
  ['p::before, a::after', null, 'p::before, a::after'],
  [':is(h1, h2)::first-line, blockquote::first-line', '::first-line', ':is(h1, h2), blockquote'],
  ['p:hover::before, a:focus::before', '::before', 'p:hover, a:focus']
]

test.each(selectors)('typography preserves the trailing pseudo-elements in %s', (selector, pseudo, rebuilt) => {
  assert.deepEqual(commonTrailingPseudos(selector), [pseudo, rebuilt])
})
