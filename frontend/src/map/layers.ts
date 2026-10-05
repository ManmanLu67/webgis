export interface ManagedLayer {
  id: string
  name: string
  group: string
  visible: boolean
  opacity: number
  order: number
  /** 这条图层自己的范围。没有就说明它是全球底图或地形，"范围"按钮不该假装飞到它。 */
  extent?: { west: number; south: number; east: number; north: number }
}

export function groupLayers(layers: ManagedLayer[]): { group: string; layers: ManagedLayer[] }[] {
  const sorted = [...layers].sort((left, right) => left.order - right.order)
  const groups = new Map<string, ManagedLayer[]>()
  for (const layer of sorted) {
    const bucket = groups.get(layer.group) ?? []
    bucket.push(layer)
    groups.set(layer.group, bucket)
  }
  return [...groups.entries()].map(([group, items]) => ({ group, layers: items }))
}

export function moveLayer(layers: ManagedLayer[], id: string, direction: "up" | "down"): ManagedLayer[] {
  const sorted = [...layers].sort((left, right) => left.order - right.order).map((layer) => ({ ...layer }))
  const index = sorted.findIndex((layer) => layer.id === id)
  const target = direction === "up" ? index - 1 : index + 1
  if (index < 0 || target < 0 || target >= sorted.length) return layers
  const currentOrder = sorted[index].order
  sorted[index].order = sorted[target].order
  sorted[target].order = currentOrder
  return sorted
}

export function withoutLayer(layers: ManagedLayer[], id: string): ManagedLayer[] {
  return layers.filter((layer) => layer.id !== id)
}
