import {
  CreateStartUpPageContainer,
  OsEventTypeList,
  TextContainerProperty,
  TextContainerUpgrade,
  waitForEvenAppBridge,
  type EvenAppBridge,
} from '@evenrealities/even_hub_sdk'
import { CELLS, GEAR, HEADER, SLIP, SLOTS, label, pages, screen, type Box, type Glance, type Units } from './view.ts'

type Settings = { server: string; every: number; speed: Units['speed']; temp: Units['temp']; mine: string[] }

const DEFAULTS: Settings = { server: '', every: 500, speed: 'km/h', temp: 'C', mine: ['', '', '', '', '', ''] }
const KEY = 'cardiag-glasses'
const TIMEOUT = 3000
const BOXES: Box[] = [HEADER, ...CELLS]
const NAMES = ['head', 'cell1', 'cell2', 'cell3', 'cell4', 'cell5', 'cell6']

function load(): Settings {
  try {
    const kept = JSON.parse(localStorage.getItem(KEY) ?? '{}')
    const mine = Array.isArray(kept.mine) ? DEFAULTS.mine.map((_, n) => String(kept.mine[n] ?? '')) : DEFAULTS.mine
    return { ...DEFAULTS, ...kept, mine }
  } catch {
    return { ...DEFAULTS }
  }
}

function save(): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(settings))
  } catch {
    // A page that cannot keep its settings still shows values.
  }
}

const settings = load()
let packed: string[] = [] // the addresses a packaged build was made for (see scripts/pack.mjs)
let using = 0 // which of them is being asked
let glance: Glance | null = null
let problem: string | null = null
let misses = 0
let index = 0
let paused = false
let bridge: EvenAppBridge | null = null

// ---- where the values come from ----------------------------------------------

function tidy(address: string): string {
  const text = address.trim().replace(/\/+$/, '')
  return text && !/^https?:\/\//i.test(text) ? `http://${text}` : text
}

/** The address to ask: the one typed in, else one packed in, else wherever this page came from. */
function source(): string | null {
  const base = tidy(settings.server) || packed[using % (packed.length || 1)]
  if (base) return `${base}/api/glance`
  return location.protocol.startsWith('http') ? new URL('../api/glance', location.href).href : null
}

async function ask(url: string): Promise<Glance> {
  const stop = new AbortController()
  const timer = setTimeout(() => stop.abort(), TIMEOUT)
  try {
    const reply = await fetch(url, { cache: 'no-store', signal: stop.signal })
    if (!reply.ok) throw new Error(String(reply.status))
    return (await reply.json()) as Glance
  } finally {
    clearTimeout(timer)
  }
}

async function tick(): Promise<void> {
  const url = source()
  if (!url) {
    glance = null
    problem = 'set the address in the phone app'
  } else {
    try {
      glance = await ask(url)
      problem = null
      misses = 0
    } catch {
      misses += 1
      using += 1 // a packaged build may know the box by more than one address; try the next
      if (misses >= Math.max(2, packed.length)) {
        glance = null
        problem = 'no answer from the box'
      }
    }
  }
  draw()
}

async function run(): Promise<void> {
  for (;;) {
    if (!paused) await tick()
    await new Promise((done) => setTimeout(done, settings.every))
  }
}

// ---- the glasses -----------------------------------------------------------

const wanted: (string | undefined)[] = [] // text waiting to go to each part
const sent: string[] = [] // what each part last showed
let sending = false

/** Send what changed, one part at a time; text overtaken while the link was busy is never sent. */
async function pump(): Promise<void> {
  if (sending || !bridge) return
  sending = true
  try {
    for (let n = wanted.findIndex((text) => text !== undefined); n >= 0; n = wanted.findIndex((text) => text !== undefined)) {
      const content = wanted[n] as string
      wanted[n] = undefined
      if (content === sent[n]) continue
      const ok = await bridge.textContainerUpgrade(new TextContainerUpgrade({ containerID: n + 1, containerName: NAMES[n], content }))
      if (ok) sent[n] = content
    }
  } catch (error) {
    console.error('[cardiag] could not update the glasses', error)
  } finally {
    sending = false
  }
}

function part(n: number, content: string): TextContainerProperty {
  const box = BOXES[n]
  return new TextContainerProperty({
    xPosition: box.x,
    yPosition: box.y,
    width: box.w,
    height: box.h,
    borderWidth: n ? 1 : 0,
    borderColor: 6,
    borderRadius: 6,
    paddingLength: n ? 10 : 6,
    containerID: n + 1,
    containerName: NAMES[n],
    content,
    isEventCapture: n ? 0 : 1, // the header takes every tap and swipe
  })
}

function turn(by: number): void {
  const total = pages(glance, settings.mine).length
  index = (index + by + total) % total
  draw()
}

async function wear(found: EvenAppBridge): Promise<void> {
  const first = texts()
  const result = await found.createStartUpPageContainer(
    new CreateStartUpPageContainer({ containerTotalNum: BOXES.length, textObject: first.map((content, n) => part(n, content)) }),
  )
  if (result !== 0) {
    console.error('[cardiag] the glasses refused the page:', result)
    return
  }
  first.forEach((content, n) => (sent[n] = content))
  bridge = found
  let last = { type: -1, at: 0 }
  // Presses come from the header or from the system, depending on the firmware; one that
  // arrives both ways within a moment is one press.
  const touch = (type: OsEventTypeList | undefined) => {
    const kind = type ?? OsEventTypeList.CLICK_EVENT // a press arrives with no type at all
    if (kind === last.type && Date.now() - last.at < 150) return
    last = { type: kind, at: Date.now() }
    if (kind === OsEventTypeList.CLICK_EVENT || kind === OsEventTypeList.SCROLL_BOTTOM_EVENT) turn(1)
    else if (kind === OsEventTypeList.SCROLL_TOP_EVENT) turn(-1)
    else if (kind === OsEventTypeList.DOUBLE_CLICK_EVENT) void found.shutDownPageContainer(1) // the system asks before leaving
  }
  found.onEvenHubEvent((event) => {
    if (event.textEvent) touch(event.textEvent.eventType)
    const system = event.sysEvent?.eventType
    if (event.sysEvent?.eventSource !== undefined && (system === undefined || system === OsEventTypeList.CLICK_EVENT || system === OsEventTypeList.DOUBLE_CLICK_EVENT)) touch(system)
    if (system === OsEventTypeList.FOREGROUND_EXIT_EVENT) paused = true
    if (system === OsEventTypeList.FOREGROUND_ENTER_EVENT) {
      paused = false
      sent.length = 0 // whatever was on the display may be gone
      draw()
    }
  })
  console.log('[cardiag] ready')
  draw()
}

// ---- the page on the phone ---------------------------------------------------

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T
const lens = $('lens')
const parts = BOXES.map((box, n) => {
  const element = document.createElement('div')
  element.className = n ? 'cell' : 'head'
  Object.assign(element.style, { left: `${box.x}px`, top: `${box.y}px`, width: `${box.w}px`, height: `${box.h}px` })
  lens.append(element)
  return element
})

function texts(): string[] {
  return screen(glance, problem, settings.mine, index, { speed: settings.speed, temp: settings.temp })
}

let offered = ''

/** The choices for the person's own page: whatever the car is reporting now, plus the two worked out from it. */
function choices(): void {
  const readings = glance?.readings ?? []
  const options: [string, string][] = [['', 'Nothing'], [GEAR, 'Gear'], [SLIP, 'Clutch slip'], ...readings.map((r) => [r.key, r.name] as [string, string])]
  for (const slot of settings.mine) if (slot && !options.some(([key]) => key === slot)) options.push([slot, label(slot)])
  const signature = options.map(([key]) => key).join()
  if (signature === offered) return
  offered = signature
  document.querySelectorAll<HTMLSelectElement>('#mine select').forEach((select, n) => {
    select.replaceChildren(...options.map(([key, name]) => new Option(name, key, false, key === settings.mine[n])))
  })
}

function draw(): void {
  const list = texts()
  list.forEach((content, n) => {
    parts[n].textContent = content
    wanted[n] = content
  })
  void pump()
  const url = source()
  const where = url ? new URL(url).host : 'nowhere yet'
  $('link').textContent = problem ? `No answer from ${where}` : glance ? `Reading from ${where}` : `Asking ${where}`
  $('link').className = problem ? 'bad' : glance ? 'good' : ''
  $('worn').textContent = bridge ? 'Showing on the glasses' : 'Glasses not attached: this is a preview'
  choices()
}

function fit(): void {
  lens.style.transform = `scale(${Math.min(1, ($('stage').clientWidth || 576) / 576)})`
  $('stage').style.height = `${288 * Math.min(1, ($('stage').clientWidth || 576) / 576)}px`
}

function form(): void {
  const server = $<HTMLInputElement>('server')
  server.value = settings.server
  server.addEventListener('change', () => {
    settings.server = server.value.trim()
    misses = 0
    save()
    void tick()
  })
  const pick = (id: string, key: 'every' | 'speed' | 'temp') => {
    const select = $<HTMLSelectElement>(id)
    select.value = String(settings[key])
    select.addEventListener('change', () => {
      if (key === 'every') settings.every = Number(select.value)
      else if (key === 'speed') settings.speed = select.value as Units['speed']
      else settings.temp = select.value as Units['temp']
      save()
      draw()
    })
  }
  pick('every', 'every')
  pick('speed', 'speed')
  pick('temp', 'temp')
  const mine = $('mine')
  for (let n = 0; n < SLOTS; n += 1) {
    const select = document.createElement('select')
    select.setAttribute('aria-label', `Cell ${n + 1} of your own page`)
    select.addEventListener('change', () => {
      settings.mine[n] = select.value
      save()
      draw()
    })
    mine.append(select)
  }
  $('back').addEventListener('click', () => turn(-1))
  $('next').addEventListener('click', () => turn(1))
  window.addEventListener('resize', fit)
  fit()
}

async function start(): Promise<void> {
  form()
  draw()
  try {
    const reply = await fetch('./config.json', { cache: 'no-store' })
    if (reply.ok) packed = ((await reply.json()).servers ?? []).map((address: unknown) => tidy(String(address))).filter(Boolean)
  } catch {
    // Only a packaged build names an address there.
  }
  void run()
  try {
    await wear(await waitForEvenAppBridge()) // never settles in an ordinary browser, which then stays a preview
  } catch (error) {
    console.error('[cardiag] no glasses', error)
  }
}

void start()
