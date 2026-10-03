export type CatalogSource = {
  id: string
  name: string
  availability: string
  drape?: boolean
  picker?: "time" | "extent" | "template" | null
}

export function layerPickerSources<T extends { drape?: boolean; availability: string }>(sources: T[]): T[] {
  return sources.filter((source) => source.drape === true && source.availability === "ready")
}
