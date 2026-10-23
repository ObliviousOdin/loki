import { useStore } from '@nanostores/react'
import { useEffect, useMemo } from 'react'

import { createPhoneLinkSettings } from '@/store/phone-links'

import type { PhoneLinksBridge } from '../../electron/phone-link-types'

export function usePhoneLinkSettings(api: PhoneLinksBridge | undefined) {
  const controller = useMemo(() => createPhoneLinkSettings(api), [api])
  const state = useStore(controller.$state)
  useEffect(() => controller.start(), [controller])

  return {
    ...state,
    refresh: controller.refresh,
    create: controller.create,
    cancel: controller.cancel,
    decide: controller.decide,
    revoke: controller.revoke,
    signIn: controller.signIn,
    act: controller.act
  }
}
