import assert from 'node:assert/strict'
import { test } from 'node:test'
import { CELLS, HEADER, cell, clock, header, pages, screen, type Glance, type Units } from '../src/view.ts'

const METRIC: Units = { speed: 'km/h', temp: 'C' }
const US: Units = { speed: 'mph', temp: 'F' }

function driving(extra: Partial<Glance> = {}): Glance {
  return {
    state: 'connected', message: '', vin: '1FADP3F2XHL654321', recording: null, discovery: null, rate: 4, age: 0.1,
    gears_known: true, gear: 3, slip: 7.04,
    readings: [
      { key: '01:0C', name: 'Engine speed', value: 2874.25, unit: 'rpm' },
      { key: '01:0D', name: 'Vehicle speed', value: 60, unit: 'km/h' },
      { key: '01:05', name: 'Coolant temperature', value: 90, unit: '°C' },
      { key: '01:06', name: 'Short term fuel trim, bank 1', value: -2.344, unit: '%' },
      { key: '01:04', name: 'Calculated engine load', value: 61.6, unit: '%' },
      { key: '01:11', name: 'Throttle position', value: 33.3, unit: '%' },
      { key: '01:0E', name: 'Timing advance', value: 12.5, unit: '°' },
      { key: 'adapter:voltage', name: 'Battery voltage at the port', value: 14.12, unit: 'V' },
      { key: '22:7E9:1EBB', name: 'Clutch A slip', value: 132.5, unit: 'rpm' },
    ],
    ...extra,
  }
}

test('the layout fits the display', () => {
  for (const box of [HEADER, ...CELLS]) assert.ok(box.x >= 0 && box.y >= 0 && box.x + box.w <= 576 && box.y + box.h <= 288)
  assert.equal(CELLS.length, 6)
})

test('values are rounded to what can be read at a glance, in the chosen units', () => {
  const glance = driving()
  assert.equal(cell('01:0C', glance, METRIC), 'RPM\n2870 rpm')
  assert.equal(cell('01:0D', glance, METRIC), 'SPEED\n60 km/h')
  assert.equal(cell('01:0D', glance, US), 'SPEED\n37 mph')
  assert.equal(cell('01:05', glance, METRIC), 'COOLANT\n90 C')
  assert.equal(cell('01:05', glance, US), 'COOLANT\n194 F')
  assert.equal(cell('01:06', glance, METRIC), 'TRIM SHORT\n-2.3 %')
  assert.equal(cell('01:04', glance, METRIC), 'LOAD\n62 %')
  assert.equal(cell('01:0E', glance, METRIC), 'TIMING\n12.5 deg')
  assert.equal(cell('adapter:voltage', glance, METRIC), 'BATTERY\n14.1 V')
  assert.equal(cell('22:7E9:1EBB', glance, METRIC), 'CLUTCH A SLIP\n130 rpm')
})

test('gear and slip say when they cannot be known', () => {
  assert.equal(cell('gear', driving(), METRIC), 'GEAR\n3')
  assert.equal(cell('slip', driving(), METRIC), 'CLUTCH SLIP\n! 7.0 %')
  assert.equal(cell('slip', driving({ slip: 1.2 }), METRIC), 'CLUTCH SLIP\n1.2 %')
  assert.equal(cell('gear', driving({ gear: null, slip: null }), METRIC), 'GEAR\n--')
  assert.equal(cell('gear', driving({ gears_known: false, gear: null }), METRIC), 'GEAR\nnot learned')
  assert.equal(cell('01:0C', null, METRIC), 'RPM\n--')
  assert.equal(cell('', driving(), METRIC), ' ')
})

test('pages follow what the car is reporting', () => {
  const list = pages(driving(), ['', '', '', '', '', ''])
  assert.deepEqual(list.map((page) => page.name), ['DRIVE', 'ENGINE', 'MAKER'])
  assert.deepEqual(list[0].slots, ['01:0D', '01:0C', 'gear', 'slip', '01:04', '01:11']) // no pedal reading, so throttle
  assert.deepEqual(list[1].slots, ['01:05', '01:06', '01:0E', 'adapter:voltage', '', ''])
  assert.deepEqual(list[2].slots.slice(0, 2), ['22:7E9:1EBB', ''])
  assert.deepEqual(pages(null, ['slip', '', '', '', '', '']).map((page) => page.name), ['DRIVE', 'ENGINE', 'MINE'])
  assert.ok(pages(null, []).every((page) => page.slots.length === 6))
})

test('the top line names the page, or the reason nothing is showing', () => {
  const page = pages(driving(), [])[0]
  assert.equal(header(page, 0, 3, driving(), null), 'DRIVE 1/3')
  assert.equal(header(page, 0, 3, driving({ recording: 134.2 }), null), 'DRIVE 1/3 | REC 2:14')
  assert.equal(header(page, 0, 3, driving({ age: 8.4 }), null), 'DRIVE 1/3 | no news for 8 s')
  assert.equal(header(page, 0, 3, driving({ discovery: 'capturing' }), null), 'DRIVE 1/3 | discovery run')
  assert.equal(header(page, 0, 3, driving({ state: 'no_vehicle' }), null), 'cardiag | car not answering')
  assert.equal(header(page, 0, 3, null, null), 'cardiag | connecting')
  assert.equal(header(page, 0, 3, null, 'no answer from the box'), 'cardiag | no answer from the box')
  assert.equal(clock(59.9), '0:59')
})

test('a screen is seven texts, and a page number past the end wraps', () => {
  const texts = screen(driving(), null, [], 4, METRIC) // three pages, so this is the second
  assert.equal(texts.length, 7)
  assert.equal(texts[0], 'ENGINE 2/3')
  assert.equal(screen(driving(), null, [], -1, METRIC)[0], 'MAKER 3/3')
})
