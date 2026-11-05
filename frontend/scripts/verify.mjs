import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { execSync } from 'node:child_process'
import puppeteer from 'puppeteer-core'

const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const BASE = 'http://127.0.0.1:5173'
const OUT = 'C:/Users/sanir/AppData/Local/Temp/opencode/dg'

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: 'new',
  args: ['--no-sandbox', '--disable-gpu', '--hide-scrollbars'],
})

const results = []
const record = (check, ok, detail) => results.push({ check, ok, detail })

async function newPage(width = 1280, height = 900) {
  const page = await browser.newPage()
  await page.setViewport({ width, height, deviceScaleFactor: 1 })
  const errors = []
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()) })
  page.on('pageerror', e => errors.push(String(e)))
  page._errors = errors
  return page
}

// ---------- home + responsive ----------
for (const [w, h] of [[1440, 900], [1024, 768], [768, 1024], [390, 844]]) {
  const page = await newPage(w, h)
  await page.goto(BASE, { waitUntil: 'networkidle0' })
  await new Promise(r => setTimeout(r, 900))
  const m = await page.evaluate(() => ({
    vw: document.documentElement.clientWidth,
    sw: document.documentElement.scrollWidth,
    engine: document.querySelector('.badge')?.textContent?.trim() || '',
    chips: document.querySelectorAll('.chip').length,
  }))
  record(`home ${w}: no overflow`, m.sw <= m.vw + 1, m)
  record(`home ${w}: engine badge`, m.engine.length > 0, m.engine)
  record(`home ${w}: no console errors`, page._errors.length === 0, page._errors)
  if (w === 1440) await page.screenshot({ path: `${OUT}/v2-home.png`, fullPage: true })
  await page.close()
}

// ---------- portal title + supported parameter directory ----------
{
  const page = await newPage(1440, 900)
  await page.goto(BASE, { waitUntil: 'networkidle0' })
  const info = await page.evaluate(() => ({
    docTitle: document.title,
    h1: document.querySelector('.hero h1')?.textContent?.trim() || '',
    lead: document.querySelector('.hero-lead')?.textContent?.trim() || '',
    commodityPills: document.querySelectorAll('.scope-panel .scope-group:first-child .scope-pill').length,
    statePills: document.querySelectorAll('.scope-panel .scope-group:last-child .scope-pill').length,
  }))
  record('portal: intuitive title & heading', /Mandi Price/i.test(info.docTitle) && /Mandi Price/i.test(info.h1), info)
  record('portal: lists 6 tracked commodities & 12 states', info.commodityPills === 6 && info.statePills === 12, info)
  await page.close()
}

// ---------- valid bare commodity ("Tomato"), invalid ("Cloth"), and junk ("@#$%^&*!") ----------
{
  const page = await newPage()
  await page.goto(`${BASE}/?q=Tomato`, { waitUntil: 'networkidle0' })
  await page.waitForSelector('.turn', { timeout: 25000 })
  await new Promise(r => setTimeout(r, 900))
  const validRes = await page.evaluate(() => ({
    rows: document.querySelectorAll('.turn tbody tr').length,
    bars: document.querySelectorAll('.recharts-bar-rectangle').length,
    answer: document.querySelector('.answer-text')?.textContent || '',
  }))
  record('valid input "Tomato": returns table & bar chart', validRes.rows >= 5 && validRes.bars >= 5, validRes)
  await page.close()
}
{
  const page = await newPage()
  await page.goto(`${BASE}/?q=Cloth`, { waitUntil: 'networkidle0' })
  await page.waitForSelector('.turn', { timeout: 25000 })
  await new Promise(r => setTimeout(r, 700))
  const invalidRes = await page.evaluate(() => ({
    rows: document.querySelectorAll('.turn tbody tr').length,
    callout: document.querySelector('.scope-callout-title')?.textContent?.trim() || '',
    recoveryPills: document.querySelectorAll('.scope-callout .scope-pill').length,
    answer: document.querySelector('.answer-text')?.textContent || '',
  }))
  record('invalid input "Cloth": 0 rows + supported commodity recovery callout', invalidRes.rows === 0 && invalidRes.recoveryPills === 6 && /Cloth/i.test(invalidRes.answer), invalidRes)
  await page.close()
}
{
  const page = await newPage()
  await page.goto(`${BASE}/?q=${encodeURIComponent('@#$%^&*!')}`, { waitUntil: 'networkidle0' })
  await page.waitForSelector('.turn', { timeout: 25000 })
  await new Promise(r => setTimeout(r, 700))
  const junkRes = await page.evaluate(() => ({
    rows: document.querySelectorAll('.turn tbody tr').length,
    callout: document.querySelector('.scope-callout-title')?.textContent?.trim() || '',
    recoveryPills: document.querySelectorAll('.scope-callout .scope-pill').length,
    answer: document.querySelector('.answer-text')?.textContent || '',
  }))
  record('junk input "@#$%^&*!": 0 rows + unrecognized format guidance', junkRes.rows === 0 && junkRes.recoveryPills === 6 && /Unrecognized query/i.test(junkRes.callout), junkRes)
  await page.close()
}

// ---------- typed question + chart + trace ----------
{
  const page = await newPage()
  await page.goto(BASE, { waitUntil: 'networkidle0' })
  await page.waitForSelector('.search-wrap input')
  await page.type('.search-wrap input', 'Which market has the cheapest onion price?')
  await Promise.all([
    page.waitForSelector('.turn', { timeout: 20000 }),
    page.click('.search-wrap button[type="submit"]'),
  ])
  await new Promise(r => setTimeout(r, 1000))
  const s = await page.evaluate(() => ({
    rows: document.querySelectorAll('.turn tbody tr').length,
    bars: document.querySelectorAll('.recharts-bar-rectangle').length,
    engine: document.querySelector('.turn .meta')?.textContent || '',
    hasTrace: !!document.querySelector('.trace'),
    followups: document.querySelectorAll('.followups .chip').length,
  }))
  record('typed question: 5 rows', s.rows === 5, s.rows)
  record('typed question: 5 bars', s.bars === 5, s.bars)
  record('typed question: engine label', /Rule-based|AI-generated/.test(s.engine), s.engine)
  record('typed question: trace panel', s.hasTrace, s.hasTrace)
  record('typed question: follow-up chips', s.followups === 3, s.followups)
  await page.screenshot({ path: `${OUT}/v2-result.png`, fullPage: true })
  await page.close()
}

// ---------- trend line chart ----------
{
  const page = await newPage()
  await page.goto(`${BASE}/?q=How+have+onion+prices+moved+over+the+last+two+weeks%3F`, { waitUntil: 'networkidle0' })
  await page.waitForSelector('.turn', { timeout: 20000 })
  await new Promise(r => setTimeout(r, 1200))
  const s = await page.evaluate(() => ({
    path: document.querySelectorAll('.recharts-line-curve').length,
    points: document.querySelectorAll('.recharts-line-dot').length,
    rows: document.querySelectorAll('.turn tbody tr').length,
    answer: document.querySelector('.answer-text')?.textContent || '',
  }))
  record('trend: line rendered', s.path >= 1, s.path)
  record('trend: 21 rows', s.rows === 21, s.rows)
  record('trend: answer mentions movement', /moved (up|down|flat)/.test(s.answer), s.answer)
  await page.screenshot({ path: `${OUT}/v2-trend.png`, fullPage: true })
  await page.close()
}

// ---------- follow-up conversation ----------
{
  const page = await newPage()
  await page.goto(BASE, { waitUntil: 'networkidle0' })
  await page.type('.search-wrap input', 'Which market has the cheapest tomato price?')
  await Promise.all([
    page.waitForSelector('.turn', { timeout: 20000 }),
    page.click('.search-wrap button[type="submit"]'),
  ])
  await new Promise(r => setTimeout(r, 700))
  await page.type('.search-wrap input', 'And in Kerala?')
  await Promise.all([
    page.waitForFunction(() => document.querySelectorAll('.turn').length === 2, { timeout: 20000 }),
    page.click('.search-wrap button[type="submit"]'),
  ])
  await new Promise(r => setTimeout(r, 900))
  const s = await page.evaluate(() => {
    const turns = [...document.querySelectorAll('.turn')]
    const newest = turns[0]
    return {
      count: turns.length,
      collapsed: document.querySelectorAll('.turn-collapsed').length,
      states: [...newest.querySelectorAll('tbody tr')].map(tr => tr.children[2]?.textContent),
      url: window.location.search,
    }
  })
  record('follow-up: two turns', s.count === 2, s.count)
  record('follow-up: previous turn collapsed', s.collapsed === 1, s.collapsed)
  record('follow-up: scoped to Kerala', s.states.length > 0 && s.states.every(x => x === 'Kerala'), s.states)
  record('follow-up: url updated', s.url.includes('Kerala'), s.url)
  await page.screenshot({ path: `${OUT}/v2-followup.png`, fullPage: true })
  await page.close()
}

// ---------- voice fallback (headless has no speech API) ----------
{
  const page = await newPage()
  await page.goto(BASE, { waitUntil: 'networkidle0' })
  await page.click('.mic')
  await new Promise(r => setTimeout(r, 500))
  const s = await page.evaluate(() => ({
    note: document.querySelector('.voice-note')?.textContent?.trim() || '',
  }))
  record('voice: explains unsupported browser', /support|microphone|Chrome|Edge/i.test(s.note), s.note)
  await page.close()
}

// ---------- voice: live Groq Whisper STT via mic button ----------
{
  const wavPath = path.join(os.tmpdir(), 'dg_verify_stt.wav')
  execSync(
    `powershell -NoProfile -Command "Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; $s.SetOutputToWaveFile('${wavPath}'); $s.Speak('What is the tomato price in Chennai?'); $s.Dispose()"`
  )
  const wavB64 = fs.readFileSync(wavPath).toString('base64')

  const page = await newPage()
  await page.goto(BASE, { waitUntil: 'networkidle0' })
  await page.evaluate((b64) => {
    const bin = atob(b64)
    const bytes = new Uint8Array(bin.length)
    for (let i = 0; i < bin.length; i += 1) bytes[i] = bin.charCodeAt(i)
    const wavBlob = new Blob([bytes], { type: 'audio/wav' })

    navigator.mediaDevices.getUserMedia = async () => new MediaStream()
    window.AudioContext = undefined
    window.MediaRecorder = class FakeRecorder {
      static isTypeSupported() { return true }
      constructor() {
        this.state = 'inactive'
        this.mimeType = 'audio/wav'
        this.ondataavailable = null
        this.onstop = null
      }
      start() {
        this.state = 'recording'
        setTimeout(() => {
          if (this.ondataavailable) this.ondataavailable({ data: wavBlob })
        }, 50)
      }
      stop() {
        if (this.state === 'inactive') return
        this.state = 'inactive'
        if (this.onstop) this.onstop()
      }
    }
  }, wavB64)

  await page.click('.mic') // start recording
  await new Promise(r => setTimeout(r, 200))
  await Promise.all([
    page.waitForSelector('.turn', { timeout: 25000 }),
    page.click('.mic'), // stop recording -> sends WAV to /api/transcribe -> runs query
  ])
  await new Promise(r => setTimeout(r, 900))
  const s = await page.evaluate(() => ({
    q: document.querySelector('.turn-q')?.textContent?.trim() || '',
    rows: document.querySelectorAll('.turn tbody tr').length,
  }))
  record('voice: live Groq Whisper STT search', /tomato/i.test(s.q) && /chennai/i.test(s.q) && s.rows > 0, s)
  await page.close()
}

// ---------- mobile result ----------
{
  const page = await newPage(390, 844)
  await page.goto(`${BASE}/?q=How+have+onion+prices+moved+over+the+last+two+weeks%3F`, { waitUntil: 'networkidle0' })
  await page.waitForSelector('.turn', { timeout: 20000 })
  await new Promise(r => setTimeout(r, 900))
  const m = await page.evaluate(() => ({
    vw: document.documentElement.clientWidth,
    sw: document.documentElement.scrollWidth,
  }))
  record('mobile result: no overflow', m.sw <= m.vw + 1, m)
  await page.screenshot({ path: `${OUT}/v2-mobile.png`, fullPage: true })
  await page.close()
}

await browser.close()
console.log(JSON.stringify(results, null, 2))
const failed = results.filter(r => !r.ok)
console.log(failed.length ? `${failed.length} FAILURES` : 'ALL V2 UI CHECKS PASS')
process.exit(failed.length ? 1 : 0)
