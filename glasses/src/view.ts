// What each part of the display says. Nothing here touches the glasses or the network,
// so it can be checked with plain Node (see test/).

export type Reading = { key: string; name: string; value: number | string; unit: string }

/** What cardiag answers at /api/glance. */
export type Glance = {
  state: string
  message: string
  vin: string | null
  recording: number | null // seconds, when a recording is going
  discovery: string | null
  rate: number | null
  age: number | null // seconds since the car last answered
  readings: Reading[]
  gears_known: boolean
  gear: number | null
  slip: number | null // percent above the gear's line
}

export type Units = { speed: 'km/h' | 'mph'; temp: 'C' | 'F' }
export type Page = { name: string; slots: string[] }
export type Box = { x: number; y: number; w: number; h: number }

export const GEAR = 'gear'
export const SLIP = 'slip'
export const SLOTS = 6
export const SLIP_WORTH_A_LOOK = 5 // percent
export const STALE_AFTER = 3 // seconds

// The display is 576 by 288. One line across the top, then three cells by two.
export const HEADER: Box = { x: 0, y: 0, w: 576, h: 44 }
export const CELLS: Box[] = [0, 1, 2, 3, 4, 5].map((n) => ({ x: (n % 3) * 194, y: 44 + Math.floor(n / 3) * 124, w: 188, h: 120 }))

const SPEED = '01:0D'
const PEDAL = '01:49'
const THROTTLE = '01:11'

const SHORT: Record<string, string> = {
  '01:04': 'LOAD',
  '01:05': 'COOLANT',
  '01:06': 'TRIM SHORT',
  '01:07': 'TRIM LONG',
  '01:0B': 'MANIFOLD',
  '01:0C': 'RPM',
  '01:0D': 'SPEED',
  '01:0E': 'TIMING',
  '01:0F': 'INTAKE AIR',
  '01:10': 'AIR FLOW',
  '01:11': 'THROTTLE',
  '01:42': 'MODULE V',
  '01:49': 'PEDAL',
  '01:5C': 'OIL',
  'adapter:voltage': 'BATTERY',
}

// Shown on the Engine page, in this order, as far as the car is reporting them.
const ENGINE = ['01:05', '01:06', '01:07', '01:0B', '01:0E', '01:10', '01:42', 'adapter:voltage', '01:0F', '01:5C']

const WAITING: Record<string, string> = {
  starting: 'starting',
  no_adapter: 'no adapter found',
  no_vehicle: 'car not answering',
}

function find(glance: Glance | null, key: string): Reading | undefined {
  return glance?.readings.find((reading) => reading.key === key)
}

export function label(slot: string, reading?: Reading): string {
  if (slot === GEAR) return 'GEAR'
  if (slot === SLIP) return 'CLUTCH SLIP'
  if (SHORT[slot]) return SHORT[slot]
  return (reading?.name ?? slot).toUpperCase().slice(0, 18)
}

function number(key: string, value: number, unit: string): string {
  if (unit === 'rpm') return String(Math.round(value / 10) * 10)
  const whole = ['km/h', 'mph', 'C', 'F', 'kPa'].includes(unit) || (unit === '%' && !['01:06', '01:07', '01:08', '01:09'].includes(key))
  if (whole || Math.abs(value) >= 100) return String(Math.round(value))
  return value.toFixed(1)
}

/** A reading as it is shown: converted to the chosen units, and without signs the glasses may not have. */
export function shown(reading: Reading, units: Units): { value: string; unit: string } {
  if (typeof reading.value === 'string') return { value: reading.value.slice(0, 16), unit: '' }
  let value = reading.value
  let unit = reading.unit
  if (unit === 'km/h' && units.speed === 'mph') {
    value *= 0.621371
    unit = 'mph'
  } else if (unit === '°C') {
    unit = units.temp
    if (units.temp === 'F') value = (value * 9) / 5 + 32
  } else if (unit === '°') {
    unit = 'deg'
  }
  return { value: number(reading.key, value, unit), unit }
}

/** The two lines of one cell: what it is, then its value. */
export function cell(slot: string, glance: Glance | null, units: Units): string {
  if (!slot) return ' '
  if (slot === GEAR) {
    if (glance && glance.state === 'connected' && !glance.gears_known) return 'GEAR\nnot learned'
    return `GEAR\n${glance?.gear ?? '--'}`
  }
  if (slot === SLIP) {
    const slip = glance?.slip
    if (slip === null || slip === undefined) return 'CLUTCH SLIP\n--'
    return `CLUTCH SLIP\n${slip >= SLIP_WORTH_A_LOOK ? '! ' : ''}${slip.toFixed(1)} %`
  }
  const reading = find(glance, slot)
  if (!reading) return `${label(slot)}\n--`
  const { value, unit } = shown(reading, units)
  return `${label(slot, reading)}\n${value}${unit ? ' ' + unit : ''}`
}

/** The pages on offer: two fixed ones, the maker's values when any are being read, and the person's own. */
export function pages(glance: Glance | null, mine: string[]): Page[] {
  const have = new Set((glance?.readings ?? []).map((reading) => reading.key))
  const effort = have.has(PEDAL) || !have.has(THROTTLE) ? PEDAL : THROTTLE
  const engine = ENGINE.filter((key) => have.has(key))
  const list: Page[] = [
    { name: 'DRIVE', slots: [SPEED, '01:0C', GEAR, SLIP, '01:04', effort] },
    { name: 'ENGINE', slots: (engine.length ? engine : ENGINE).slice(0, SLOTS) },
  ]
  const maker = [...have].filter((key) => key.startsWith('22:')).slice(0, SLOTS)
  if (maker.length) list.push({ name: 'MAKER', slots: maker })
  if (mine.some(Boolean)) list.push({ name: 'MINE', slots: mine.slice(0, SLOTS) })
  for (const page of list) while (page.slots.length < SLOTS) page.slots.push('')
  return list
}

export function clock(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds))
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`
}

/** The line across the top: which page this is, or why there is nothing to show. */
export function header(page: Page, index: number, total: number, glance: Glance | null, problem: string | null): string {
  if (problem) return `cardiag | ${problem}`
  if (!glance) return 'cardiag | connecting'
  if (glance.state !== 'connected') return `cardiag | ${WAITING[glance.state] ?? (glance.message || glance.state)}`
  let text = `${page.name} ${index + 1}/${total}`
  if (glance.age !== null && glance.age > STALE_AFTER) text += ` | no news for ${Math.round(glance.age)} s`
  else if (glance.discovery) text += ' | discovery run'
  if (glance.recording !== null) text += ` | REC ${clock(glance.recording)}`
  return text
}

/** Everything on the display, header first, as the text of its seven parts. */
export function screen(glance: Glance | null, problem: string | null, mine: string[], index: number, units: Units): string[] {
  const list = pages(glance, mine)
  const at = ((index % list.length) + list.length) % list.length
  const page = list[at]
  return [header(page, at, list.length, glance, problem), ...page.slots.map((slot) => cell(slot, glance, units))]
}
