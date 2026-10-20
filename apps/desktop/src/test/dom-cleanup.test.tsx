import { FocusScope } from '@radix-ui/react-focus-scope'
import { render, screen } from '@testing-library/react'
import { afterAll, expect, it, vi } from 'vitest'

const unmountEvents: Event[] = []
const eventConstructor = window.CustomEvent

it('unmounts a real focus scope before the test DOM realm is released', () => {
  // Keep its zero-delay autofocus callback pending deterministically. The
  // shared afterEach must finish it before Vitest restores Node globals.
  vi.useFakeTimers()
  render(
    <FocusScope onUnmountAutoFocus={event => unmountEvents.push(event)}>
      <button>Focus target</button>
    </FocusScope>
  )
  expect(screen.getByRole('button', { name: 'Focus target' })).toBeTruthy()
})

afterAll(async () => {
  try {
    expect(unmountEvents).toHaveLength(1)
    expect(unmountEvents[0]).toBeInstanceOf(eventConstructor)
  } finally {
    await vi.advanceTimersByTimeAsync(0)
    vi.useRealTimers()
  }
})
