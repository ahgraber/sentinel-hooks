import assert from "node:assert/strict"
import { test } from "node:test"

import { shortened } from "../../extensions/pi/shorten.ts"

const MARKER = / … (\d+) characters left out … /

test("text that fits the limit is kept whole, and one unit more is shortened to the limit", () => {
  const fits = "x".repeat(200)

  assert.equal(shortened(fits, 200), fits)
  const longer = shortened(`${fits}y`, 200)
  assert.ok(longer.length <= 200)
  assert.match(longer, MARKER)
})

test("the start and the end are kept, and the marker counts the characters left out", () => {
  const value = `start ${"🔥".repeat(1000)} end`

  const result = shortened(value, 200)

  const [head, tail] = result.split(/ … \d+ characters left out … /)
  const leftOut = Number(result.match(MARKER)[1])
  assert.ok(head.startsWith("start "))
  assert.ok(tail.endsWith(" end"))
  assert.equal([...head].length + leftOut + [...tail].length, [...value].length)
})

for (const pad of [0, 1, 2, 3]) {
  test(`neither cut splits a code point, with ${pad} units before the emoji`, () => {
    const value = `${"x".repeat(pad)}${"🔥".repeat(3000)}`

    const result = shortened(value, 2000)

    assert.match(result, MARKER)
    assert.ok(result.isWellFormed())
  })
}
