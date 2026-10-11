import { useEffect, useRef, useState } from 'react'
import type { Cash } from '../api'
import { money } from '../api'

export function CashCard({ cash }: { cash: Cash | null }) {
  const prev = useRef<number | null>(null)
  const [flash, setFlash] = useState<'down' | 'up' | null>(null)

  useEffect(() => {
    if (!cash) return
    if (prev.current !== null && prev.current !== cash.balance) {
      setFlash(cash.balance < prev.current ? 'down' : 'up')
      const t = setTimeout(() => setFlash(null), 2200)
      prev.current = cash.balance
      return () => clearTimeout(t)
    }
    prev.current = cash.balance
  }, [cash])

  return (
    <section className={`card cash-card ${flash ? `flash-${flash}` : ''}`} aria-label="Checking balance">
      <div className="eyebrow">Checking balance</div>
      <div className="cash-amount">{cash ? money(cash.balance) : '…'}</div>
      {cash && (
        <dl className="cash-lines">
          <div><dt>Awaiting approval</dt><dd>{money(cash.pending_total)}</dd></div>
          <div className={cash.balance_after_pending < 0 ? 'neg' : ''}>
            <dt>If all approved</dt><dd>{money(cash.balance_after_pending)}</dd>
          </div>
          <div><dt>As of</dt><dd>{cash.date}</dd></div>
        </dl>
      )}
    </section>
  )
}
