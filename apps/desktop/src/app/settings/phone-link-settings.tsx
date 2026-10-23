import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from '@/components/ui/dialog'
import { useI18n } from '@/i18n'
import { phoneLinkMessages, type PhoneLinkMessages } from '@/i18n/phone-links'
import { Link, RefreshCw } from '@/lib/icons'
import { samePhoneLinkClaim, samePhoneLinkOwner } from '@/lib/phone-link-identity'
import { usePhoneLinkSettings } from '@/lib/phone-links'

import type {
  PhoneLinkClaim,
  PhoneLinkDevice,
  PhoneLinkInvitation,
  PhoneLinkOwner,
  PhoneLinksBridge,
  PhoneLinkStatus
} from '../../../electron/phone-link-types'

import { ListRow, Pill, SectionHeading, SettingsContent } from './primitives'

interface Review<T> {
  value: T
  owner: PhoneLinkOwner
  api: PhoneLinksBridge
}

function usePhoneLinkClock(active: boolean): number {
  const [now, setNow] = useState(() => Date.now() / 1000)
  useEffect(() => {
    if (!active) {
      return
    }

    const timer = window.setInterval(() => {
      if (document.visibilityState !== 'hidden') {
        setNow(Date.now() / 1000)
      }
    }, 1000)

    return () => window.clearInterval(timer)
  }, [active])

  return now
}

function displayTime(timestamp: number, locale: string): string {
  return new Date(timestamp * 1000).toLocaleString(locale)
}

function phoneLinkIssueCopy(copy: PhoneLinkMessages, issue: PhoneLinkPageState['issue']): string {
  const messages = {
    owner_changed: copy.ownerChanged,
    unsupported: copy.unsupported,
    owner_sign_in_required: copy.ownerSignInRequired,
    unavailable: copy.actionFailed,
    refused: copy.actionFailed,
    invalid_request: copy.actionFailed
  }

  return messages[issue ?? 'unavailable']
}

export function PhoneLinkSettings({ api = window.hermesDesktop?.phoneLinks }: { api?: PhoneLinksBridge }) {
  const { locale, t } = useI18n(),
    copy = phoneLinkMessages(locale)

  const state = usePhoneLinkSettings(api)
  const [review, setReview] = useState<Review<PhoneLinkClaim> | null>(null)
  const [removal, setRemoval] = useState<Review<PhoneLinkDevice> | null>(null)

  const status = state.status,
    now = usePhoneLinkClock(Boolean(state.invitation || status?.value.claims.length))

  const act = state.act
  const sameReviewOwner = review && api === review.api && status && samePhoneLinkOwner(review.owner, status.owner)
  const sameRemovalOwner = removal && api === removal.api && status && samePhoneLinkOwner(removal.owner, status.owner)

  useEffect(() => {
    if (review && !sameReviewOwner) {
      setReview(null)
    }

    if (removal && !sameRemovalOwner) {
      setRemoval(null)
    }
  }, [api, status?.owner, sameReviewOwner, sameRemovalOwner, review, removal])
  const issue = phoneLinkIssueCopy(copy, state.issue)

  return (
    <SettingsContent>
      <SectionHeading icon={Link} page title={copy.title} />
      <p className="mb-5 max-w-2xl text-sm text-(--ui-text-secondary)">{copy.intro}</p>
      {!api ? <p role="status">{copy.desktopUnavailable}</p> : null}
      {api && state.loading ? <p role="status">{copy.checking}</p> : null}
      {api && state.issue ? (
        <p className="mb-4 text-sm text-destructive" role="alert">
          {issue}
        </p>
      ) : null}
      <PhoneLinkOverview
        copy={copy}
        locale={locale}
        now={now}
        onAction={action => void act(action)}
        onRemove={(value, owner) => {
          if (api) {
            setRemoval({ value, owner, api })
          }
        }}
        onReview={(value, owner) => {
          if (api) {
            setReview({ value, owner, api })
          }
        }}
        state={state}
      />
      <PhoneApprovalDialog
        busy={state.busy}
        cancel={t.common.cancel}
        copy={copy}
        current={Boolean(
          review &&
          status?.value.claims.some(claim => samePhoneLinkClaim(claim, review.value)) &&
          review.value.expiresAt > now
        )}
        onApprove={() =>
          review &&
          act(async () => {
            await state.decide(review.owner, review.value, true)
            setReview(current => (current === review ? null : current))
          })
        }
        onClose={() => setReview(null)}
        review={sameReviewOwner ? review : null}
      />
      <PhoneRevokeDialog
        busy={state.busy}
        cancel={t.common.cancel}
        copy={copy}
        onClose={() => setRemoval(null)}
        onRevoke={() =>
          removal &&
          act(async () => {
            await state.revoke(removal.owner, removal.value.id)
            setRemoval(current => (current === removal ? null : current))
          })
        }
        review={sameRemovalOwner ? removal : null}
      />
    </SettingsContent>
  )
}

type PhoneLinkPageState = ReturnType<typeof usePhoneLinkSettings>

function PhoneLinkOverview({
  state,
  copy,
  locale,
  now,
  onAction,
  onReview,
  onRemove
}: {
  state: PhoneLinkPageState
  copy: PhoneLinkMessages
  locale: string
  now: number
  onAction(action: () => Promise<unknown>): void
  onReview(claim: PhoneLinkClaim, owner: PhoneLinkOwner): void
  onRemove(device: PhoneLinkDevice, owner: PhoneLinkOwner): void
}) {
  const status = state.status

  if (!status) {
    return null
  }

  const cannotCreate =
    state.busy ||
    !status.value.configured ||
    status.value.ownerSignInRequired ||
    Boolean(state.issue) ||
    Boolean(state.invitation && state.invitation.expiresAt > now)

  return (
    <>
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <span className="font-medium">{status.value.hostName}</span>
        <Pill tone={status.value.ready ? 'success' : 'muted'}>
          {status.value.ready ? copy.statusReady : copy.statusUnavailable}
        </Pill>
        <Button className="min-h-11" disabled={state.busy} onClick={() => void state.refresh()} variant="ghost">
          <RefreshCw />
          {copy.refresh}
        </Button>
      </div>
      <PhoneLinkReadiness
        busy={state.busy}
        copy={copy}
        onSignIn={provider => onAction(() => state.signIn(status.owner, provider))}
        status={status.value}
      />
      {state.invitation ? (
        <PhoneInvitationCard
          busy={state.busy}
          copy={copy}
          locale={locale}
          now={now}
          onCancel={() => onAction(state.cancel)}
          value={state.invitation}
        />
      ) : null}
      <Button
        aria-label={state.invitation ? copy.newCode : copy.connect}
        className="mb-8 min-h-11"
        disabled={cannotCreate}
        loading={state.busy}
        onClick={() => onAction(state.create)}
      >
        {state.invitation ? copy.newCode : copy.connect}
      </Button>
      <PhoneClaimList
        busy={state.busy}
        claims={status.value.claims}
        copy={copy}
        now={now}
        onDeny={claim => onAction(() => state.decide(status.owner, claim, false))}
        onReview={claim => onReview(claim, status.owner)}
      />
      <PhoneDeviceList
        busy={state.busy}
        copy={copy}
        devices={status.value.devices}
        locale={locale}
        onRemove={device => onRemove(device, status.owner)}
      />
    </>
  )
}

function PhoneInvitationCard({
  value,
  copy,
  now,
  locale,
  busy,
  onCancel
}: {
  value: PhoneLinkInvitation
  copy: PhoneLinkMessages
  now: number
  locale: string
  busy: boolean
  onCancel(): void
}) {
  return (
    <section className="mb-6 rounded-lg border p-4">
      <h3 className="text-sm font-medium">{copy.codeTitle}</h3>
      <p className="my-3 select-text break-all font-mono text-3xl tracking-widest">{value.code}</p>
      <p className="mb-3 text-sm text-(--ui-text-secondary)">
        {value.expiresAt <= now ? copy.codeExpired : `${copy.expiresAt} ${displayTime(value.expiresAt, locale)}`}
      </p>
      <Button className="min-h-11" disabled={busy} onClick={onCancel} variant="outline">
        {copy.cancelCode}
      </Button>
    </section>
  )
}

function PhoneClaimList({
  claims,
  copy,
  now,
  busy,
  onReview,
  onDeny
}: {
  claims: PhoneLinkClaim[]
  copy: PhoneLinkMessages
  now: number
  busy: boolean
  onReview(claim: PhoneLinkClaim): void
  onDeny(claim: PhoneLinkClaim): void
}) {
  return (
    <section className="mb-8">
      <h3 className="mb-2 text-sm font-medium">{copy.pending}</h3>
      {claims.length === 0 ? <p className="text-sm text-(--ui-text-secondary)">{copy.noPending}</p> : null}
      {claims.map(claim => (
        <ListRow
          action={
            <div className="flex flex-wrap gap-2">
              <Button className="min-h-11" disabled={busy || claim.expiresAt <= now} onClick={() => onReview(claim)}>
                {copy.approve}
              </Button>
              <Button className="min-h-11" disabled={busy} onClick={() => onDeny(claim)} variant="ghost">
                {copy.deny}
              </Button>
            </div>
          }
          description={`${copy.comparison}: ${claim.comparison}`}
          key={claim.id}
          title={claim.deviceName}
        />
      ))}
    </section>
  )
}

function PhoneDeviceList({
  devices,
  copy,
  locale,
  busy,
  onRemove
}: {
  devices: PhoneLinkDevice[]
  copy: PhoneLinkMessages
  locale: string
  busy: boolean
  onRemove(device: PhoneLinkDevice): void
}) {
  return (
    <section className="mb-8">
      <h3 className="mb-2 text-sm font-medium">{copy.approved}</h3>
      {devices.length === 0 ? <p className="text-sm text-(--ui-text-secondary)">{copy.noDevices}</p> : null}
      {devices.map(device => (
        <ListRow
          action={
            <Button className="min-h-11" disabled={busy} onClick={() => onRemove(device)} variant="outline">
              {copy.revoke}
            </Button>
          }
          description={`${copy.lastUsed}: ${device.lastUsedAt ? displayTime(device.lastUsedAt, locale) : copy.neverUsed}`}
          key={device.id}
          title={device.deviceName}
        />
      ))}
    </section>
  )
}

function PhoneLinkReadiness({
  copy,
  status,
  busy,
  onSignIn
}: {
  copy: PhoneLinkMessages
  status: PhoneLinkStatus
  busy: boolean
  onSignIn(provider: string): void
}) {
  return (
    <div className="mb-4 grid gap-3 text-sm text-(--ui-text-secondary)">
      {!status.configured ? <p>{copy.unavailableDetail}</p> : null}
      {status.configured && status.unavailableReason === 'transport_unverified' ? (
        <p>{copy.transportUnverified}</p>
      ) : null}
      {status.configured && status.ownerSignInRequired ? (
        <>
          <p>{status.ownerLoginProviders.length > 0 ? copy.ownerSignInRequired : copy.ownerSignInUnavailable}</p>
          <div className="flex flex-wrap gap-2">
            {status.ownerLoginProviders.map(provider => (
              <Button
                className="min-h-11"
                disabled={busy}
                key={provider.name}
                onClick={() => onSignIn(provider.name)}
                variant="outline"
              >
                {status.ownerLoginProviders.length === 1 ? copy.signIn : copy.signInWith(provider.displayName)}
              </Button>
            ))}
          </div>
        </>
      ) : null}
    </div>
  )
}

function PhoneApprovalDialog({
  copy,
  cancel,
  review,
  busy,
  current,
  onClose,
  onApprove
}: {
  copy: PhoneLinkMessages
  cancel: string
  review: Review<PhoneLinkClaim> | null
  busy: boolean
  current: boolean
  onClose(): void
  onApprove(): unknown
}) {
  return (
    <Dialog
      onOpenChange={open => {
        if (!open && !busy) {
          onClose()
        }
      }}
      open={Boolean(review)}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{review ? copy.approvalTitle(review.value.deviceName) : copy.title}</DialogTitle>
          <DialogDescription>{copy.approvalConsent}</DialogDescription>
        </DialogHeader>
        {review ? (
          <div className="grid gap-3 text-sm">
            <p>{copy.approvalCheck}</p>
            <div>
              <span className="text-(--ui-text-secondary)">{copy.comparison}</span>
              <p className="font-mono text-xl">{review.value.comparison}</p>
            </div>
            <div>
              <span className="text-(--ui-text-secondary)">{copy.fingerprint}</span>
              <p className="break-all font-mono text-xs">{review.value.keyFingerprint}</p>
            </div>
            {!current ? <p role="alert">{copy.requestMismatch}</p> : null}
          </div>
        ) : null}
        <DialogFooter>
          <Button className="min-h-11" disabled={busy} onClick={onClose} variant="outline">
            {cancel}
          </Button>
          <Button
            aria-label={copy.approveConfirm}
            className="min-h-11"
            disabled={busy || !current}
            loading={busy}
            onClick={() => void onApprove()}
          >
            {copy.approveConfirm}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function PhoneRevokeDialog({
  copy,
  cancel,
  review,
  busy,
  onClose,
  onRevoke
}: {
  copy: PhoneLinkMessages
  cancel: string
  review: Review<PhoneLinkDevice> | null
  busy: boolean
  onClose(): void
  onRevoke(): unknown
}) {
  return (
    <Dialog
      onOpenChange={open => {
        if (!open && !busy) {
          onClose()
        }
      }}
      open={Boolean(review)}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{review ? copy.revokeTitle(review.value.deviceName) : copy.title}</DialogTitle>
          <DialogDescription>{copy.revokeDetail}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button className="min-h-11" disabled={busy} onClick={onClose} variant="outline">
            {cancel}
          </Button>
          <Button
            aria-label={copy.revoke}
            className="min-h-11"
            disabled={busy}
            loading={busy}
            onClick={() => void onRevoke()}
            variant="destructive"
          >
            {copy.revoke}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
