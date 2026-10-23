import assert from 'node:assert/strict'
import { createRequire } from 'node:module'

import { test } from 'vitest'

interface SanitizeOptions {
  allowedTags: string[]
  allowedAttributes: Record<string, string[]>
  allowedStyles?: Record<string, Record<string, RegExp[]>>
  nonTextTags?: string[]
}

const sanitizeHtml = createRequire(import.meta.url)('sanitize-html') as (
  html: string,
  options: SanitizeOptions
) => string

test('discarded noscript content stays discarded after implied closes and comment boundaries', () => {
  const inputs = [
    '<div><noscript></div><img src="https://example.invalid/loki-beacon"></noscript>',
    '<p>Hi</p><![CDATA[ x > <noscript>]]><a href="https://example.invalid/loki-link">hidden</a></noscript>'
  ]

  for (const input of inputs) {
    const sanitized = sanitizeHtml(input, {
      allowedTags: ['div', 'p', 'a', 'img'],
      allowedAttributes: { a: ['href'], img: ['src'] },
      nonTextTags: ['script', 'style', 'textarea', 'option', 'noscript']
    })

    assert.doesNotMatch(sanitized, /<(?:a|img)\b/)
  }
})

test('allowed rich text and media survive while executable attributes are removed', () => {
  const input = '<p style="color: red; position: fixed">Hello <strong>Loki</strong> <a href="https://example.invalid/docs" onclick="ignored()">docs</a></p><img src="https://example.invalid/image" alt="preview" onerror="ignored()">'

  assert.equal(sanitizeHtml(input, {
    allowedTags: ['p', 'strong', 'a', 'img'],
    allowedAttributes: { a: ['href'], img: ['src', 'alt'], p: ['style'] },
    allowedStyles: { p: { color: [/^red$/] } }
  }), '<p style="color:red">Hello <strong>Loki</strong> <a href="https://example.invalid/docs">docs</a></p><img src="https://example.invalid/image" alt="preview" />')
})
