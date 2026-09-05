// Restore shared strings before React Query caches the ordinary API response.
export function unpackCourseware<T>(response: T | { encoding: string; payload: unknown; strings: string[] }): T {
  if (!response || typeof response !== "object" || !("encoding" in response) || response.encoding !== "courseware-strings-v1") return response as T
  const packed = response as { payload: unknown; strings: string[] }
  const decode = (value: unknown): unknown => {
    if (Array.isArray(value)) return value.map(decode)
    if (value && typeof value === "object") {
      const record = value as Record<string, unknown>
      if (Object.keys(record).length === 1 && typeof record.$courseware_string === "number") {
        const text = packed.strings[record.$courseware_string]
        if (typeof text !== "string") throw new Error("Invalid courseware string reference")
        return text
      }
      return Object.fromEntries(Object.entries(record).map(([key, child]) => [key, decode(child)]))
    }
    return value
  }
  return decode(packed.payload) as T
}
