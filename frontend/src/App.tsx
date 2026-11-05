import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import './App.css'
import {
  askQuestion, fetchExamples, fetchMeta, fetchStatus,
  type AskResult, type HistoryTurn, type Meta, type Status,
} from './api'
import ResultsTable from './components/ResultsTable'
import ChartView from './components/ChartView'
import { MicIcon } from './components/MicIcon'
import { useSpeech } from './hooks/useSpeech'

interface Turn {
  id: number
  question: string
  result: AskResult
}

let nextId = 1

function suggestionsFor(result: AskResult): string[] {
  const parsed = result.parsed ?? {}
  const commodity = String(parsed.commodity ?? '').toLowerCase()
  if (!commodity) {
    return [
      'What is the tomato price in Chennai?',
      'Which market has the cheapest onion price?',
      'Compare the prices of potatoes in Tamil Nadu and Kerala.',
    ]
  }

  const out: string[] = []
  if (result.intent === 'cheapest' || result.intent === 'price' || result.intent === 'llm_sql' || result.intent === 'search') {
    out.push(`What is the ${commodity} price in Chennai?`)
    out.push(`Compare ${commodity} prices in Tamil Nadu and Kerala.`)
    out.push(`How have ${commodity} prices moved over the last two weeks?`)
  } else if (result.intent === 'compare') {
    out.push(`Which market has the cheapest ${commodity} price?`)
    out.push(`How have ${commodity} prices moved over the last two weeks?`)
  } else if (result.intent === 'trend') {
    out.push(`Compare ${commodity} prices in Tamil Nadu and Kerala.`)
    out.push(`Which market has the cheapest ${commodity} price?`)
  }
  return out.slice(0, 3)
}

export default function App() {
  const [question, setQuestion] = useState('')
  const [turns, setTurns] = useState<Turn[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [examples, setExamples] = useState<string[]>([])
  const [meta, setMeta] = useState<Meta | null>(null)
  const [status, setStatus] = useState<Status | null>(null)
  const [chartModes, setChartModes] = useState<Record<number, 'bar' | 'line'>>({})
  const started = useRef(false)
  const threadRef = useRef<HTMLDivElement>(null)
  const run = useCallback(async (text: string) => {
    const q = text.trim()
    if (!q || loading) return

    const history: HistoryTurn[] = turns
      .slice(-6)
      .map((t) => ({ question: t.question, parsed: t.result.parsed ?? null }))

    setQuestion(q)
    setLoading(true)
    setError('')

    try {
      const result = await askQuestion(q, history)
      setTurns((prev) => [{ id: nextId++, question: q, result }, ...prev])
      setQuestion('')
      const url = new URL(window.location.href)
      url.searchParams.set('q', q)
      window.history.replaceState({}, '', url)
      requestAnimationFrame(() => threadRef.current?.scrollIntoView({ block: 'start', behavior: 'smooth' }))
    } catch {
      setError('Could not reach the backend. Start it with: cd backend && python -m uvicorn main:app --port 8000 --reload')
    } finally {
      setLoading(false)
    }
  }, [loading, turns])

  const speech = useSpeech((text) => { void run(text) }, Boolean(status?.stt_available))

  useEffect(() => {
    fetchExamples().then(setExamples)
    fetchMeta().then(setMeta)
    fetchStatus().then(setStatus)
    if (started.current) return
    started.current = true
    const q = new URLSearchParams(window.location.search).get('q')
    if (q) void run(q)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const hasResult = turns.length > 0
  const latest = turns[0]
  const followUps = useMemo(() => (latest ? suggestionsFor(latest.result) : []), [latest])

  function reset() {
    window.history.replaceState({}, '', '/')
    setTurns([])
    setQuestion('')
    setError('')
  }

  function toggleMic() {
    speech.clearError()
    if (speech.status === 'listening') speech.stop()
    else speech.start()
  }

  const engineLabel = status?.llm_available
    ? `AI · ${status.llm_model ?? 'LLM'}`
    : 'Rules engine'
  const engineTitle = status?.llm_available
    ? 'Questions are translated to SQL by an LLM, then validated against a read-only guard.'
    : 'Questions are parsed by a deterministic rule engine. Add an LLM key to enable AI SQL.'

  return (
    <>
      <main className={`page ${hasResult ? 'page-result' : 'page-home'}`}>
        <div className="topbar">
          <a className="logo-mini" href="/" onClick={(e) => { e.preventDefault(); reset() }}>
            <strong>DATA GURU</strong>
          </a>
          <div className="topbar-right">
            <span className="badge" title={engineTitle}>
              <span className={`dot ${status?.llm_available ? 'dot-live' : ''}`} />
              {engineLabel}
            </span>
          </div>
        </div>

        <section className={`hero ${hasResult ? 'hero-compact' : ''}`}>
          <div className="hero-head">
            <h1>
              Indian <em>Mandi Price</em> Portal
            </h1>
            {!hasResult ? (
              <p className="hero-lead">
                Search daily wholesale vegetable rates (₹/quintal), compare states, and track 21-day price trends across India.
              </p>
            ) : (
              <p className="hero-lead hero-lead-compact">
                Wholesale AGMARKNET rates (₹/quintal) across {meta?.commodities.length ?? 6} commodities and {meta?.states.length ?? 12} states.
              </p>
            )}
          </div>

          <div className="hero-search-block">
            <form
              className={`search-wrap ${speech.status === 'listening' ? 'is-listening' : ''}`}
              onSubmit={(e) => { e.preventDefault(); void run(question) }}
            >
              <input
                autoFocus
                placeholder={speech.status === 'listening' ? 'Listening… speak your question' : 'Search anything...  e.g. Which market has the cheapest tomato?'}
                value={speech.status === 'listening' && speech.interim ? speech.interim : question}
                onChange={(e) => setQuestion(e.target.value)}
                aria-label="Ask a question"
              />
              <button
                type="button"
                className={`btn btn-ghost mic ${speech.status === 'listening' ? 'mic-active' : ''}`}
                title={
                  speech.status === 'unsupported'
                    ? 'Voice needs Chrome or Edge'
                    : status?.stt_available
                      ? `Ask by voice (Groq ${status.stt_model ?? 'Whisper'})`
                      : 'Ask by voice'
                }
                aria-label={speech.status === 'listening' ? 'Stop listening' : 'Ask by voice'}
                aria-pressed={speech.status === 'listening'}
                onClick={toggleMic}
              >
                <MicIcon />
              </button>
              <button type="submit" className="btn" disabled={loading}>
                {loading ? 'Searching…' : 'Search'}
              </button>
            </form>

            {speech.status === 'listening' && (
              <div className="voice-note" aria-live="polite">
                <span className="pulse" />{' '}
                {speech.interim || `Listening${status?.stt_available ? ' (Groq Whisper)' : ''} — ask your question, then pause.`}
              </div>
            )}
            {speech.error && (
              <div className="voice-note voice-error" role="status">{speech.error}</div>
            )}

            {!hasResult && (
              <div className="chips">
                {examples.slice(0, 3).map((ex) => (
                  <button key={ex} className="chip" onClick={() => void run(ex)}>{ex}</button>
                ))}
              </div>
            )}
          </div>
          {!hasResult && meta && (
            <div className="home-bottom">
              <section className="coverage" aria-label="Dataset coverage">
                <div><strong>{meta.total_records.toLocaleString('en-IN')}</strong><span>records loaded</span></div>
                <div><strong>{meta.commodities.length}</strong><span>commodities</span></div>
                <div><strong>{meta.states.length}</strong><span>states</span></div>
                <div><strong>{meta.days}</strong><span>days of history</span></div>
              </section>
            </div>
          )}
        </section>
        {error && <div className="empty" role="alert">{error}</div>}
        {loading && <div className="loader">Searching mandi records…</div>}

        <div ref={threadRef} />

        {hasResult && (
          <section className="thread">
            {turns.map((turn, index) => {
              const r = turn.result
              const isLatest = index === 0
              const body = (
                <>
                  <div className="meta">
                    <span>Intent: <b>{r.intent.replace('_', ' ')}</b></span>
                    <span>{r.engine === 'llm' ? 'AI-generated SQL' : 'Rule-based'}</span>
                    {r.source_date && <span>Data as of {r.source_date}</span>}
                    <span>{r.count} record{r.count !== 1 ? 's' : ''}</span>
                  </div>

                  <div className="answer-text">{r.answer}</div>

                  {r.unit_note && (
                    <div className="unit-banner" role="note">
                      <strong>Unit Conversion (₹/quintal → Kg / gms):</strong> {r.unit_note}
                    </div>
                  )}

                  {r.chart && r.chart.length > 0 && r.chart_type && (() => {
                    const activeChartType = chartModes[turn.id] ?? r.chart_type
                    return (
                      <div className="card chart-card">
                        <div className="card-header">
                          <div className="card-label">
                            {activeChartType === 'line'
                              ? 'Modal price over time (₹ per quintal)'
                              : 'Modal price visualization (₹ per quintal)'}
                          </div>
                          <div className="chart-toggle" role="group" aria-label="Chart visualization type">
                            <button
                              type="button"
                              className={`chart-toggle-btn ${activeChartType === 'bar' ? 'is-active' : ''}`}
                              onClick={() => setChartModes((prev) => ({ ...prev, [turn.id]: 'bar' }))}
                            >
                              Bar
                            </button>
                            <button
                              type="button"
                              className={`chart-toggle-btn ${activeChartType === 'line' ? 'is-active' : ''}`}
                              onClick={() => setChartModes((prev) => ({ ...prev, [turn.id]: 'line' }))}
                            >
                              Line
                            </button>
                          </div>
                        </div>
                        <ChartView type={activeChartType} data={r.chart} />
                      </div>
                    )
                  })()}

                  {r.count === 0 ? (
                    <div className="scope-callout" role="status">
                      <div className="scope-callout-title">
                        {r.intent === 'invalid'
                          ? 'Unrecognized query format — search by commodity, market, or state'
                          : 'Commodity not in portal dataset — choose a tracked crop below'}
                      </div>
                      <p className="scope-callout-desc">
                        This portal covers wholesale AGMARKNET mandi records for{' '}
                        <b>{(r.supported_commodities ?? meta?.commodities ?? []).join(', ')}</b>{' '}
                        across <b>{(r.supported_states ?? meta?.states ?? []).length || 12} Indian states</b>.
                      </p>
                      <div className="scope-pills">
                        {(r.supported_commodities ?? meta?.commodities ?? []).map((c) => (
                          <button
                            key={c}
                            type="button"
                            className="scope-pill scope-pill-action"
                            onClick={() => void run(c)}
                          >
                            Search {c}
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : r.intent === 'trend' && r.rows.length > 8 ? (
                    <details className="table-details">
                      <summary>Show all {r.rows.length} daily values</summary>
                      <div className="table-details-body">
                        <ResultsTable columns={r.columns} rows={r.rows} />
                      </div>
                    </details>
                  ) : (
                    <ResultsTable columns={r.columns} rows={r.rows} />
                  )}
                  <details className="trace">
                    <summary>How this was answered</summary>
                    {r.rationale && <p className="trace-note">{r.rationale}</p>}
                    {r.parsed && <pre>{JSON.stringify(r.parsed, null, 2)}</pre>}
                    {r.sql_used && <pre>{r.sql_used}</pre>}
                  </details>
                </>
              )

              if (isLatest) {
                return (
                  <article key={turn.id} className="turn">
                    <div className="turn-q"><span>You asked</span>{turn.question}</div>
                    {body}
                  </article>
                )
              }

              return (
                <details key={turn.id} className="turn turn-collapsed">
                  <summary>
                    <span>{turn.question}</span>
                    <em>{turn.result.count} records</em>
                  </summary>
                  <div className="turn-body">{body}</div>
                </details>
              )
            })}

            {followUps.length > 0 && !loading && (
              <div className="followups">
                <span className="followups-label">Ask next</span>
                <div className="chips chips-left">
                  {followUps.map((f) => (
                    <button key={f} className="chip" onClick={() => void run(f)}>{f}</button>
                  ))}
                </div>
              </div>
            )}
          </section>
        )}
      </main>

      <footer className="footer">
        <span>
          Source: AGMARKNET / data.gov.in
          {meta?.date_range && <> • {meta.date_range[0]} to {meta.date_range[1]}</>}
        </span>
        <span>
          {status?.llm_available ? 'LLM SQL + read-only guard' : 'Rules engine'} •{' '}
          {status?.stt_available ? 'Groq Whisper Voice STT' : 'Voice on-device'}
        </span>
      </footer>
    </>
  )
}
