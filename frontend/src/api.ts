export interface AskResult {
  intent: string
  answer: string
  columns: string[]
  rows: (string | number)[][]
  count: number
  source_date: string | null
  sql_used: string | null
  chart_type?: 'bar' | 'line' | null
  chart?: { name: string; value: number }[]
  engine?: 'llm' | 'rules'
  rationale?: string
  question?: string
  parsed?: Record<string, unknown>
  supported_commodities?: string[]
  supported_states?: string[]
  unit_note?: string
}

export interface HistoryTurn {
  question: string
  parsed?: Record<string, unknown> | null
}

export async function askQuestion(question: string, history: HistoryTurn[] = []): Promise<AskResult> {
  const res = await fetch('/api/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, history: history.slice(-6) }),
  })
  if (!res.ok) throw new Error(`Backend ${res.status}`)
  return res.json()
}

export async function fetchExamples(): Promise<string[]> {
  try {
    const r = await fetch('/api/examples')
    const j = await r.json()
    return j.examples as string[]
  } catch {
    return [
      'What is the tomato price in Chennai?',
      'Which market has the cheapest onion price?',
      'Compare potato prices in Tamil Nadu and Kerala.',
      'How have onion prices moved over the last two weeks?',
    ]
  }
}

export interface Meta {
  total_records: number
  latest_date: string
  date_range: [string, string] | null
  days: number
  commodities: string[]
  states: string[]
}

export interface Status {
  records: number
  latest_date: string
  llm_available: boolean
  llm_provider: string | null
  llm_model: string | null
  stt_available?: boolean
  stt_model?: string | null
  data_sync_available: boolean
  voice: string
}

export async function fetchMeta(): Promise<Meta | null> {
  try {
    const r = await fetch('/api/meta')
    return await r.json()
  } catch {
    return null
  }
}

export async function fetchStatus(): Promise<Status | null> {
  try {
    const r = await fetch('/api/status')
    return await r.json()
  } catch {
    return null
  }
}

export async function transcribeAudio(blob: Blob): Promise<string> {
  const mime = (blob.type || 'audio/webm').split(';')[0]
  const ext = mime.includes('wav') ? 'wav' : mime.includes('ogg') ? 'ogg' : mime.includes('mp4') ? 'mp4' : 'webm'
  const res = await fetch('/api/transcribe', {
    method: 'POST',
    headers: {
      'Content-Type': mime,
      'X-Audio-Filename': `speech.${ext}`,
    },
    body: blob,
  })
  if (!res.ok) throw new Error(`STT ${res.status}`)
  const data = (await res.json()) as { text?: string }
  return (data.text ?? '').trim()
}
