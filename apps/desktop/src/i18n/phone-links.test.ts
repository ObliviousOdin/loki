import { describe, expect, it } from 'vitest'

import { phoneLinkMessages } from './phone-links'
import type { BundledLocale } from './types'

const locales = ['en', 'zh', 'zh-hant', 'ja', 'ar', 'ru', 'fr', 'de', 'es'] as const satisfies readonly BundledLocale[]

describe('phone linking on desktop hosts', () => {
  it('explains that work stays on the computer, not a required Mac', () => {
    const copy = phoneLinkMessages('en')

    expect(copy.intro).toContain('this computer')
    expect(copy.unavailableDetail).toContain('this computer')
    expect(copy.ownerSignInRequired).toContain('this computer')
  })

  it.each(locales)('does not require a Mac in %s phone setup', locale => {
    const copy = phoneLinkMessages(locale)

    for (const value of Object.values(copy)) {
      if (typeof value === 'string') {
        expect(value).not.toMatch(/Mac/)
      }
    }
  })
})
