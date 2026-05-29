if (!("structuredClone" in globalThis)) {
  globalThis.structuredClone = (<T>(value: T): T => {
    if (value === undefined) return value
    return JSON.parse(JSON.stringify(value)) as T
  }) as typeof structuredClone
}
