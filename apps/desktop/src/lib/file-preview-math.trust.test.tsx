import { render, waitFor } from '@testing-library/react'
import { Streamdown } from 'streamdown'
import { expect, it } from 'vitest'

import { createMemoizedMathPlugin } from '@/lib/katex-memo'

it('keeps inherited options from enabling trusted commands in preview math', async () => {
  const inheritedTrust = Object.getOwnPropertyDescriptor(Object.prototype, 'trust')

  Object.defineProperty(Object.prototype, 'trust', { configurable: true, value: true, writable: true })

  try {
    const math = createMemoizedMathPlugin({ singleDollarTextMath: true })

    const { container } = render(
      <Streamdown mode="static" plugins={{ math }}>
        {'$\\href{https://example.invalid/loki-math-trust}{Loki math trust}$'}
      </Streamdown>
    )

    await waitFor(() => expect(container.querySelector('.katex')).not.toBeNull())
    expect(container.querySelector('.katex [href]')).toBeNull()
  } finally {
    if (inheritedTrust) {
      Object.defineProperty(Object.prototype, 'trust', inheritedTrust)
    } else {
      Reflect.deleteProperty(Object.prototype, 'trust')
    }
  }
})
