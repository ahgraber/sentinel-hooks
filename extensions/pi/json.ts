/**
 * Parse JSON under the rule every Sentinel JSON reader applies: text that is not
 * valid UTF-8, that holds `NaN` or `Infinity`, that holds a number outside the
 * range of a double, or that is nested too deeply to parse does not parse.
 *
 * `JSON.parse` already rejects `NaN` and `Infinity`; a number outside the range
 * would otherwise read as `Infinity`. A reader of bytes checks them with `isUtf8`
 * from `node:buffer` before it decodes them.
 */

/** Parse `text` as JSON; throw when it does not parse or holds a number outside the range of a double. */
export function parseJson(text: string): unknown {
  return JSON.parse(text, (_key, value: unknown) => {
    if (typeof value === "number" && !Number.isFinite(value)) {
      throw new SyntaxError("a number is outside the range of a double")
    }
    return value
  })
}
