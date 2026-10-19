/** Loki's presentation boundary. Keep upstream catalog keys and wire names stable. */
const DIAGNOSTICS_COPY: Record<string, string> = {
  title: 'Send diagnostics to your configured service',
  privacyNotice: 'Upload requires a diagnostics service configured for Loki. The bundle includes system information and agent, gateway and desktop logs, which may contain conversation content, tool outputs and file paths. Secrets are redacted before upload. Confirm the service owner, access policy and retention before uploading.',
  doneDescription: 'Your configured service accepted the bundle. Review its link-sharing policy before sharing the returned link.',
  failedHint: 'Run `loki debug share --local` to print a local report. A remote upload requires an explicitly configured Loki diagnostics service.'
}

const ONBOARDING_COPY: Record<string, string> = {
  headerDesc: 'Connect your own provider account, API key, or local model endpoint.',
  featuredPitch: 'Requires your own Nous account and an authorized OAuth client configured for Loki.'
}

const TUI_STARTUP_COPY: Record<string, string> = {
  'status.summoning': 'summoning Loki…',
  'chatBits.branding.tagFull': 'Loki · Personal AI agent',
  'chatBits.branding.tagMid': 'Loki',
  'help.commands.quit': 'exit Loki'
}

export function brandText(text: string): string {
  return text
    .replace(/curl -fsSL https:\/\/hermes-agent\.nousresearch\.com\/install\.sh \| sh/g, 'https://github.com/ObliviousOdin/loki#installation')
    .replace(/\bHermes Agent\b/g, 'Loki')
    .replace(/\bHermes\b/g, 'Loki')
    .replace(/~\/\.hermes\b/g, '~/.loki')
    .replace(/\bhermes:\/\//g, 'loki://')
    .replace(/\bhermes-tui\b/g, 'loki-tui')
    .replace(/\bhermes(?= (?:--|auth\b|binary\b|config\b|curator\b|dashboard\b|debug\b|desktop\b|doctor\b|gateway\b|logs\b|model\b|plugins\b|pm\b|setup\b|skills\b|update\b))/g, 'loki')
}

function brandMessage(format: (...args: unknown[]) => unknown, args: unknown[]): unknown {
  const rendered = format(...args)
  const strings = args.flatMap((value, index) => typeof value === 'string' ? [[`\uE000LOKI${index}\uE001`, value]] : [])
  const masked = args.map((value, index) => typeof value === 'string' ? `\uE000LOKI${index}\uE001` : value)
  const restore = (text: string) => strings.reduce((value, [token, original]) => value.split(token).join(original), text)
  const template = format(...masked)

  // Catalog formatters may return a string or a list of rotation choices.
  // Preserve user/model arguments and any branch that masking would change.
  const adapt = (original: unknown, candidate: unknown): unknown =>
    typeof original === 'string' && typeof candidate === 'string' && restore(candidate) === original
      ? restore(brandText(candidate))
      : original

  return Array.isArray(rendered) && Array.isArray(template)
    ? rendered.map((value, index) => adapt(value, template[index]))
    : adapt(rendered, template)
}

/** Adapt owned UI catalogs, including downloaded language packs, without editing translations. */
export function brandCatalog<T>(catalog: T, keyPath = ''): T {
  if (typeof catalog === 'string') {
    const startupCopy = TUI_STARTUP_COPY[keyPath.replace(/^\./, '')]

    if (startupCopy) {return startupCopy as T}

    const diagnosticsKey = keyPath.match(/(?:^|\.)sendDiagnostics\.(\w+)$/)?.[1]

    if (diagnosticsKey && DIAGNOSTICS_COPY[diagnosticsKey]) {return DIAGNOSTICS_COPY[diagnosticsKey] as T}

    const onboardingKey = keyPath.match(/(?:^|\.)onboarding\.(\w+)$/)?.[1]

    if (onboardingKey && ONBOARDING_COPY[onboardingKey]) {return ONBOARDING_COPY[onboardingKey] as T}

    const text = brandText(catalog)

    return (/sharedMetrics/i.test(keyPath) ? text.replace(/Nous/g, 'your configured metrics destination') : text) as T
  }

  if (typeof catalog === 'function') {
    return ((...args: unknown[]) => brandMessage(catalog as (...args: unknown[]) => unknown, args)) as T
  }

  if (Array.isArray(catalog)) {return catalog.map(value => brandCatalog(value, keyPath)) as T}

  if (catalog !== null && typeof catalog === 'object') {
    return Object.fromEntries(Object.entries(catalog).map(([key, value]) => [key, brandCatalog(value, `${keyPath}.${key}`)])) as T
  }

  return catalog
}
