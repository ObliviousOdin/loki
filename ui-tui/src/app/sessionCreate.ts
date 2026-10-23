import { JsonRpcGatewayError } from '@hermes/shared/json-rpc-channel'

import { buildSetupRequiredSections, setupRequiredTitle } from '../content/setup.js'
import type { GatewayClient } from '../gatewayClient.js'
import type { SessionCreateResponse } from '../gatewayTypes.js'
import { t } from '../i18n/runtime.js'
import { asRpcResult, rpcErrorMessage } from '../lib/rpc.js'
import type { PanelSection } from '../types.js'

import type { GatewayRpc } from './interfaces.js'
import { patchUiState } from './uiStore.js'

interface SessionCreation {
  response: SessionCreateResponse | null
  needsSetup: boolean
}

interface CreateSessionOptions {
  gw: GatewayClient
  params: Record<string, unknown>
  rpc: GatewayRpc
  sys: (text: string) => void
}

export async function createSession({ gw, params, rpc, sys }: CreateSessionOptions) {
  if (!gw.isCanonical) {
    return { response: await rpc<SessionCreateResponse>('session.create', params), needsSetup: false }
  }

  try {
    const response = asRpcResult<SessionCreateResponse>(await gw.request('session.create', params))

    if (!response) {
      sys(`error: ${t('session.common.invalidResponse', 'session.create')}`)
    }

    return { response, needsSetup: false }
  } catch (error) {
    // Keep the structured create refusal until the lifecycle can offer the existing setup handoff.
    const data = error instanceof JsonRpcGatewayError ? (error.data as { reason?: unknown; field?: unknown }) : null

    if (data?.reason === 'invalid_params' && data.field === 'model') {
      return { response: null, needsSetup: true }
    }

    sys(`error: ${rpcErrorMessage(error)}`)

    return { response: null, needsSetup: false }
  }
}

/** Present a current create refusal; successful responses continue to session hydration. */
export function acceptCreatedSession(
  created: SessionCreation,
  panel: (title: string, sections: PanelSection[]) => void
): created is SessionCreation & { response: SessionCreateResponse } {
  if (created.needsSetup) {
    panel(setupRequiredTitle(), buildSetupRequiredSections())
    patchUiState({ status: t('session.status.setupRequired') })

    return false
  }

  if (!created.response) {
    patchUiState({ status: 'ready' })

    return false
  }

  return true
}
