import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { PassThrough } from 'node:stream'

import { renderSync, Text } from '@hermes/ink'
import { JsonRpcRequestChannel } from '@hermes/shared/json-rpc-channel'
import React from 'react'
import { expect, it, vi } from 'vitest'

import { runExternalSetup } from '../app/setupHandoff.js'
import { getUiState, resetUiState } from '../app/uiStore.js'
import { useSessionLifecycle } from '../app/useSessionLifecycle.js'
import { canonicalRequest, canonicalResult } from '../canonicalGateway.js'
import { asRpcResult, rpcErrorMessage } from '../lib/rpc.js'

function fixture() {
  const home = mkdtempSync(join(tmpdir(), 'ink-unconfigured-'))
  vi.stubEnv('HERMES_HOME', home)
  vi.stubEnv('HERMES_TUI_ACTIVE_SESSION_FILE', join(home, 'active'))
  vi.stubEnv('HERMES_MODEL', '')
  resetUiState()
  const frames: Array<{ method: string; params: Record<string, unknown> }> = []
  let configured = false
  let refusedField: null | string = null
  const channel = new JsonRpcRequestChannel()
  channel.attach({
    send(text) {
      const frame = JSON.parse(text)
      frames.push({ method: frame.method, params: frame.params })

      const field =
        refusedField ?? (frame.method === 'session.create' && !configured && !frame.params.model ? 'model' : null)

      const response = field
        ? {
            error: {
              code: 4001,
              message: 'invalid_params',
              data: {
                reason: 'invalid_params',
                field,
                detail: 'select a model with loki setup before starting a session'
              }
            }
          }
        : {
            result:
              frame.method === 'setup.status'
                ? { provider_configured: configured }
                : {
                    session_id: 'configured-session',
                    stored_session_id: 'configured-session',
                    messages: [],
                    info: {
                      model: frame.params.model || 'configured-fixture',
                      skills: {},
                      tools: {},
                      stored_session_id: 'configured-session'
                    }
                  }
          }

      queueMicrotask(() => channel.handleFrame(JSON.stringify({ jsonrpc: '2.0', id: frame.id, ...response })))
    }
  })
  const contract = { sources: ['tui'], parameters: ['source', 'request_id', 'model', 'cwd', 'client_env'] }

  const request = async (method: string, params: Record<string, unknown> = {}) => {
    const wire = canonicalRequest(method, params, contract)

    return canonicalResult(method, await channel.request(wire.method, wire.params), wire.params)
  }

  const sys = vi.fn()
  const panel = vi.fn()

  const rpc = async (method: string, params: Record<string, unknown> = {}) => {
    try {
      return asRpcResult(await request(method, params))
    } catch (error) {
      sys(`error: ${rpcErrorMessage(error)}`)

      return null
    }
  }

  const gateway = { gw: { isCanonical: true, request }, rpc }
  let lifecycle!: ReturnType<typeof useSessionLifecycle>

  function Harness() {
    lifecycle = useSessionLifecycle({
      colsRef: { current: 80 },
      composerActions: { setComposerTokens: vi.fn() },
      ...gateway,
      scrollRef: { current: null },
      panel,
      sys,
      setHistoryItems: vi.fn(),
      setLastUserMsg: vi.fn(),
      setSessionStartedAt: vi.fn(),
      setStickyPrompt: vi.fn(),
      setVoiceProcessing: vi.fn(),
      setVoiceRecording: vi.fn()
    } as any)

    return <Text>session setup</Text>
  }

  const instance = renderSync(<Harness />, {
    stdin: new PassThrough() as any,
    stdout: Object.assign(new PassThrough(), { columns: 80, rows: 20, isTTY: false }) as any,
    stderr: new PassThrough() as any,
    patchConsole: false
  })

  return {
    frames,
    panel,
    sys,
    gateway,
    session: () => lifecycle,
    configure: () => {
      configured = true
    },
    refuse: (field: string) => {
      refusedField = field
    },
    close: () => {
      instance.unmount()
      channel.detach(new Error('fixture finished'))
      resetUiState()
      vi.unstubAllEnvs()
      rmSync(home, { recursive: true, force: true })
    }
  }
}

it('routes the decoded missing-model refusal to existing setup and retries after its handoff', async () => {
  const f = fixture()

  try {
    expect(await f.session().newSession()).toBeNull()
    expect(f.panel).toHaveBeenCalledWith(
      expect.any(String),
      expect.arrayContaining([
        expect.objectContaining({ rows: expect.arrayContaining([expect.arrayContaining(['/setup'])]) })
      ])
    )
    expect(getUiState().status).toBe('setup required')
    expect(f.sys).not.toHaveBeenCalled()

    const launcher = vi.fn(async () => {
      f.configure()

      return { code: 0 }
    })

    await runExternalSetup({
      args: ['setup'],
      done: 'configured',
      launcher,
      suspend: async run => {
        await run()
      },
      ctx: {
        gateway: f.gateway,
        session: {
          newSession: () => {
            void f.session().newSession()
          }
        },
        transcript: { sys: f.sys }
      } as any
    })
    await vi.waitFor(() => expect(getUiState().sid).toBe('configured-session'))
    expect(launcher).toHaveBeenCalledWith(['setup'])
    expect(f.frames.filter(frame => frame.method === 'session.create')).toHaveLength(2)
    expect(f.frames.some(frame => frame.method.startsWith('prompt.'))).toBe(false)
  } finally {
    f.close()
  }
})

it('preserves explicit model launch and does not turn another field refusal into setup', async () => {
  const f = fixture()

  try {
    vi.stubEnv('HERMES_MODEL', 'explicit-fixture')
    expect(await f.session().newSession()).toBe('configured-session')
    expect(f.frames[0]).toMatchObject({ method: 'session.create', params: { model: 'explicit-fixture' } })
    expect(f.panel).not.toHaveBeenCalled()
    f.refuse('cwd')
    expect(await f.session().newSession()).toBeNull()
    expect(f.panel).not.toHaveBeenCalled()
    expect(f.sys).toHaveBeenCalled()
  } finally {
    f.close()
  }
})
