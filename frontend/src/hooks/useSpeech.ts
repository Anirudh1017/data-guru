import { useCallback, useEffect, useRef, useState } from 'react'
import { transcribeAudio } from '../api'
import type { SpeechRecognitionLike } from '../speech'

type Status = 'idle' | 'listening' | 'unsupported' | 'denied'

const ERROR_COPY: Record<string, string> = {
  'not-allowed': 'Microphone permission was blocked. Allow it in the browser address bar.',
  'service-not-allowed': 'Speech recognition is blocked by the browser.',
  'audio-capture': 'No microphone was found.',
  network: 'Speech recognition needs a network connection.',
  'no-speech': 'I did not catch that. Try again.',
}

function pickMimeType(): string {
  if (typeof MediaRecorder === 'undefined') return ''
  for (const candidate of ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4']) {
    if (MediaRecorder.isTypeSupported(candidate)) return candidate
  }
  return ''
}

export function useSpeech(onFinal: (text: string) => void, useServerStt = false) {
  const [status, setStatus] = useState<Status>('idle')
  const [interim, setInterim] = useState('')
  const [error, setError] = useState('')
  const recognition = useRef<SpeechRecognitionLike | null>(null)
  const mediaRecorder = useRef<MediaRecorder | null>(null)
  const mediaStream = useRef<MediaStream | null>(null)
  const audioCtx = useRef<AudioContext | null>(null)
  const vadTimer = useRef<number | null>(null)
  const chunks = useRef<Blob[]>([])
  const finalText = useRef('')
  const onFinalRef = useRef(onFinal)

  useEffect(() => {
    onFinalRef.current = onFinal
  }, [onFinal])

  const cleanupMedia = useCallback(() => {
    if (vadTimer.current !== null) {
      window.clearInterval(vadTimer.current)
      vadTimer.current = null
    }
    if (audioCtx.current) {
      void audioCtx.current.close().catch(() => {})
      audioCtx.current = null
    }
    if (mediaStream.current) {
      mediaStream.current.getTracks().forEach((t) => t.stop())
      mediaStream.current = null
    }
    mediaRecorder.current = null
  }, [])

  useEffect(() => {
    const Ctor = window.SpeechRecognition ?? window.webkitSpeechRecognition
    if (!Ctor) {
      if (!navigator.mediaDevices?.getUserMedia) setStatus('unsupported')
      return
    }
    const rec = new Ctor()
    rec.lang = 'en-IN'
    rec.continuous = false
    rec.interimResults = true
    rec.maxAlternatives = 1

    rec.onstart = () => {
      setStatus('listening')
      setError('')
      setInterim('')
      finalText.current = ''
    }
    rec.onresult = (event) => {
      let live = ''
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i]
        const text = result[0]?.transcript ?? ''
        if (result.isFinal) finalText.current += text
        else live += text
      }
      setInterim(live)
    }
    rec.onerror = (event) => {
      if (useServerStt && mediaRecorder.current) return
      setError(ERROR_COPY[event.error] ?? `Voice error: ${event.error}`)
      setStatus(event.error === 'not-allowed' ? 'denied' : 'idle')
    }
    rec.onend = () => {
      if (useServerStt) return
      setInterim('')
      setStatus((prev) => (prev === 'denied' ? prev : 'idle'))
      const text = finalText.current.trim()
      if (text) onFinalRef.current(text)
    }

    recognition.current = rec
    return () => {
      rec.onstart = null
      rec.onresult = null
      rec.onerror = null
      rec.onend = null
      try { rec.abort() } catch { /* already stopped */ }
      recognition.current = null
      cleanupMedia()
    }
  }, [cleanupMedia, useServerStt])

  const stop = useCallback(() => {
    if (mediaRecorder.current && mediaRecorder.current.state !== 'inactive') {
      try { mediaRecorder.current.stop() } catch { /* ignore */ }
    }
    try { recognition.current?.stop() } catch { /* ignore */ }
  }, [])

  const startServerRecording = useCallback(async () => {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setStatus('unsupported')
      setError('This browser does not support voice search. Try Chrome or Edge.')
      return
    }
    try {
      // Start Web Speech API alongside so permission errors or live interim previews fire immediately
      try { recognition.current?.start() } catch { /* optional */ }

      const { promise: timeoutPromise, reject: rejectTimeout } = Promise.withResolvers<MediaStream>()
      const timer = window.setTimeout(
        () => rejectTimeout(Object.assign(new Error('Permission timeout'), { name: 'NotAllowedError' })),
        350,
      )
      const stream = await Promise.race([
        navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          },
        }),
        timeoutPromise,
      ]).finally(() => window.clearTimeout(timer))
      mediaStream.current = stream
      chunks.current = []
      finalText.current = ''
      setError('')
      setInterim('')
      setStatus('listening')

      const mimeType = pickMimeType()
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream)
      mediaRecorder.current = recorder

      recorder.ondataavailable = (ev) => {
        if (ev.data && ev.data.size > 0) chunks.current.push(ev.data)
      }

      recorder.onstop = async () => {
        try { recognition.current?.stop() } catch { /* ignore */ }
        const recordedChunks = chunks.current
        const blobType = recorder.mimeType || mimeType || 'audio/webm'
        cleanupMedia()
        const blob = new Blob(recordedChunks, { type: blobType })
        if (blob.size < 256) {
          setInterim('')
          setStatus('idle')
          const fallback = finalText.current.trim()
          if (fallback) onFinalRef.current(fallback)
          else setError(ERROR_COPY['no-speech'])
          return
        }
        setInterim('Transcribing with Groq Whisper…')
        try {
          const text = await transcribeAudio(blob)
          setInterim('')
          setStatus('idle')
          const resolved = (text || finalText.current).trim()
          if (resolved) onFinalRef.current(resolved)
          else setError(ERROR_COPY['no-speech'])
        } catch {
          setInterim('')
          setStatus('idle')
          const fallback = finalText.current.trim()
          if (fallback) onFinalRef.current(fallback)
          else setError('Could not transcribe audio. Try again.')
        }
      }

      recorder.start(200)

      // Voice Activity Detection (VAD): auto-stop after speech + 1.3s silence (or max 12s)
      const Ctx = window.AudioContext ?? window.webkitAudioContext
      const startedAt = performance.now()
      let spokeAt = 0
      let silenceSince = 0

      if (Ctx) {
        const ctx = new Ctx()
        audioCtx.current = ctx
        const source = ctx.createMediaStreamSource(stream)
        const analyser = ctx.createAnalyser()
        analyser.fftSize = 512
        source.connect(analyser)
        const data = new Uint8Array(analyser.fftSize)

        vadTimer.current = window.setInterval(() => {
          const now = performance.now()
          if (now - startedAt > 12000) {
            stop()
            return
          }
          analyser.getByteTimeDomainData(data)
          let sumSq = 0
          for (let i = 0; i < data.length; i += 1) {
            const norm = (data[i] - 128) / 128
            sumSq += norm * norm
          }
          const rms = Math.sqrt(sumSq / data.length)
          if (rms > 0.025) {
            spokeAt = now
            silenceSince = 0
          } else if (spokeAt > 0) {
            if (!silenceSince) silenceSince = now
            else if (now - silenceSince > 1300) {
              stop()
            }
          } else if (now - startedAt > 6500) {
            stop()
          }
        }, 100)
      } else {
        vadTimer.current = window.setInterval(() => {
          if (performance.now() - startedAt > 8000) stop()
        }, 250)
      }
    } catch (err) {
      cleanupMedia()
      const name = err instanceof Error ? err.name : ''
      if (name === 'NotAllowedError' || name === 'PermissionDeniedError' || name === 'SecurityError') {
        setStatus('denied')
        setError(ERROR_COPY['not-allowed'])
      } else if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
        setStatus('idle')
        setError(ERROR_COPY['audio-capture'])
      } else {
        setStatus('idle')
        setError(ERROR_COPY['not-allowed'])
      }
    }
  }, [cleanupMedia, stop])

  const start = useCallback(() => {
    setError('')
    if (status === 'listening') {
      stop()
      return
    }
    if (useServerStt) {
      void startServerRecording()
      return
    }
    if (!recognition.current) {
      setStatus('unsupported')
      setError('This browser does not support voice search. Try Chrome or Edge.')
      return
    }
    try {
      recognition.current.start()
    } catch {
      recognition.current.stop()
    }
  }, [startServerRecording, status, stop, useServerStt])

  return {
    status,
    interim,
    error,
    start,
    stop,
    clearError: () => setError(''),
  }
}
