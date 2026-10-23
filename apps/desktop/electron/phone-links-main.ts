import type { IpcMain, IpcMainInvokeEvent } from 'electron'

import { redialLocalGateway } from './local-gateway'
import { type NativeLoginDeps, runNativeLogin } from './native-oauth-login'
import { createPhoneLinksManager, type PhoneLinkLocalDescriptor } from './phone-links'
import { registerPhoneLinksIpc } from './phone-links-ipc'

interface DesktopPhoneLinkDeps {
  ipc: Pick<IpcMain, 'handle'>
  trusted(event: IpcMainInvokeEvent): boolean
  ensure(): Promise<PhoneLinkLocalDescriptor>
  forget(): Promise<void> | void
  fetchJson(
    url: string,
    token: null,
    options: {
      method?: string
      body?: unknown
      bearer?: string
      gatewayDescriptor: PhoneLinkLocalDescriptor
      timeoutMs: number
    }
  ): Promise<unknown>
  openExternal(url: string): Promise<{ ok: boolean }>
  postJson: NativeLoginDeps['postJson']
}

/** Bind the existing native grant transport and browser broker without persisting owner tokens. */
export function registerDesktopPhoneLinks(deps: DesktopPhoneLinkDeps): void {
  const manager = createPhoneLinksManager({
    withLocal: use => redialLocalGateway({ ensure: deps.ensure, forget: deps.forget, use }),
    request: (descriptor, requestPath, options) =>
      deps.fetchJson(`${descriptor.baseUrl}${requestPath}`, null, {
        ...options,
        gatewayDescriptor: descriptor,
        timeoutMs: 15_000
      }),
    login: (baseUrl, provider, authorizeBaseUrl) =>
      runNativeLogin(
        baseUrl,
        {
          openExternal: async url => {
            if (!(await deps.openExternal(url)).ok) {
              throw new Error('unavailable')
            }
          },
          postJson: deps.postJson
        },
        { provider, authorizeBaseUrl }
      )
  })

  registerPhoneLinksIpc(deps.ipc, manager, deps.trusted)
}
