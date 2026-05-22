const OPTION_PREFIX_PATTERN = /^([A-D])\s*[.)、。:：）-]\s*/i

export function optionLabel(index: number) {
  return `${String.fromCharCode(65 + index)}.`
}

export function optionKey(index: number) {
  return String.fromCharCode(65 + index)
}

export function stripOptionPrefix(value: unknown, index?: number) {
  let text = String(value ?? "").trim()
  const expectedKey = typeof index === "number" ? optionKey(index) : ""

  for (let guard = 0; guard < 3; guard += 1) {
    const match = text.match(OPTION_PREFIX_PATTERN)
    if (!match) break
    if (expectedKey && match[1].toUpperCase() !== expectedKey) break
    text = text.slice(match[0].length).trim()
  }

  return text
}
