/** The one way this extension shortens text a hook produced before the model or the user sees it. */

const isHighSurrogate = (code: number): boolean => code >= 0xd800 && code <= 0xdbff
const isLowSurrogate = (code: number): boolean => code >= 0xdc00 && code <= 0xdfff

const marker = (count: number): string => ` … ${count} characters left out … `

/**
 * Return `value` whole when it fits in `limit` UTF-16 code units, and otherwise cut out its middle.
 *
 * The start names what the text is, and the end holds what a reader acts on, such as the last line
 * of a traceback, so the end keeps three quarters of the room. The marker counts the characters left
 * out, and neither cut falls inside a surrogate pair, so a character outside the Basic Multilingual
 * Plane stays whole.
 */
export function shortened(value: string, limit: number): string {
  if (value.length <= limit) return value
  const room = limit - marker(value.length).length
  let head = Math.floor(room / 4)
  let tailStart = value.length - (room - head)
  if (isHighSurrogate(value.charCodeAt(head - 1))) head--
  if (isLowSurrogate(value.charCodeAt(tailStart))) tailStart++
  const leftOut = [...value.slice(head, tailStart)].length
  return `${value.slice(0, head)}${marker(leftOut)}${value.slice(tailStart)}`
}
