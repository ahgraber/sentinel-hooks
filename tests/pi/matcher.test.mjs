import assert from "node:assert/strict"
import { test } from "node:test"

import { compileMatcher } from "../../extensions/pi/matcher.ts"

test("Bash matches Pi's bash", () => {
  assert.equal(compileMatcher("Bash").matches("bash"), true)
})

test("a list of names matches each name exactly", () => {
  const matcher = compileMatcher("write|edit")

  assert.equal(matcher.matches("edit"), true)
  assert.equal(matcher.matches("Write"), true)
  assert.equal(matcher.matches("read"), false)
  assert.equal(matcher.matches("editor"), false)
})

test("names separated by commas and spaces are a list of exact names", () => {
  const matcher = compileMatcher("Edit, Write | bash")

  assert.equal(matcher.matches("write"), true)
  assert.equal(matcher.matches("bash"), true)
  assert.equal(matcher.matches("read"), false)
})

test("a hyphenated name matches only that name", () => {
  const matcher = compileMatcher("my-tool")

  assert.equal(matcher.matches("my-tool"), true)
  assert.equal(matcher.matches("my-tool_all"), false)
})

test("an empty matcher and * match every tool", () => {
  for (const matcher of ["", "*"]) {
    assert.equal(compileMatcher(matcher).matches("anything"), true)
  }
})

test("a regular expression matches anywhere in the name", () => {
  assert.equal(compileMatcher("mcp.*").matches("mcp"), true)
  assert.equal(compileMatcher("^mcp__").matches("MCP__server__tool"), true)
  assert.equal(compileMatcher("^mcp__").matches("bash"), false)
})

test("an invalid regular expression matches nothing and is reported", () => {
  const matcher = compileMatcher("bash(")

  assert.equal(matcher.matches("bash"), false)
  assert.match(matcher.problem, /not a valid regular expression/)
})
