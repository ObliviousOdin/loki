import { brandCatalog, brandText } from '@hermes/shared/branding'
import { describe, expect, it } from 'vitest'

import { TRANSLATIONS } from '@/i18n/catalog'

describe('Loki catalog presentation', () => {
  it('brands static, nested, and formatted copy without changing catalog keys', () => {
    const original = { hermes: { title: 'Hermes Agent', hint: 'hermes doctor', named: (count: number) => `Hermes has ${count} sessions` } }
    const branded = brandCatalog(original)
    expect(branded.hermes.title).toBe('Loki')
    expect(branded.hermes.hint).toBe('loki doctor')
    expect(branded.hermes.named(2)).toBe('Loki has 2 sessions')
    expect(brandText('hermes desktop · hermes curator restore · hermes debug share --local')).toBe('loki desktop · loki curator restore · loki debug share --local')
    expect(original.hermes.title).toBe('Hermes Agent')
  })

  it('retains third-party attribution and internal names', () => {
    expect(brandText('Nous Research · hermes_cli · MIT')).toBe('Nous Research · hermes_cli · MIT')
    expect(brandText('~/.hermes/config.yaml · hermes://skill/install')).toBe('~/.loki/config.yaml · loki://skill/install')
  })

  it('preserves user names and provider model names in formatted messages', () => {
    const branded = brandCatalog({ name: (name: string) => `Hermes selected ${name}` })
    expect(branded.name('Hermes-3')).toBe('Loki selected Hermes-3')
    expect(branded.name('Hermes')).toBe('Loki selected Hermes')
    const choices = brandCatalog({ name: (name: string) => [`Hermes selected ${name}`] })
    expect(choices.name('Hermes-3')).toEqual(['Loki selected Hermes-3'])
  })

  it('does not inherit upstream diagnostics access or retention promises', () => {
    const original = { sendDiagnostics: { title: 'Send to Nous', privacyNotice: 'Only Nous staff can view; deletes after 14 days.' } }
    const branded = brandCatalog(original)
    expect(branded.sendDiagnostics.title).toContain('your configured service')
    expect(branded.sendDiagnostics.privacyNotice).toContain('Confirm the service owner, access policy and retention')
    expect(branded.sendDiagnostics.privacyNotice).not.toMatch(/Nous staff|14 days/)
    expect(original.sendDiagnostics.privacyNotice).toContain('14 days')
  })

  it.each(Object.keys(TRANSLATIONS))('explains separately configured provider access in the %s catalog', locale => {
    const onboarding = TRANSLATIONS[locale as keyof typeof TRANSLATIONS].onboarding
    expect(onboarding.headerDesc).toBe('Connect your own provider account, API key, or local model endpoint.')
    expect(onboarding.featuredPitch).toBe('Requires your own Nous account and an authorized OAuth client configured for Loki.')
  })

  it('keeps downloaded onboarding copy within the same provider-access contract', () => {
    const original = { onboarding: { headerDesc: 'One-click access', featuredPitch: 'An included subscription', signInWith: (provider: string) => `Sign in with ${provider}` } }
    const adapted = brandCatalog(original)
    expect(adapted.onboarding.featuredPitch).toContain('your own Nous account')
    expect(adapted.onboarding.headerDesc).toContain('your own provider account')
    expect(adapted.onboarding.signInWith('Nous Portal')).toBe('Sign in with Nous Portal')
    expect(original.onboarding.featuredPitch).toBe('An included subscription')
  })
})
