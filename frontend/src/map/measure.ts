export interface LonLat {
  lon: number
  lat: number
  height?: number
}

const EARTH_RADIUS_M = 6_378_137

export function distanceMeters(start: LonLat, end: LonLat): number {
  const toRad = (degree: number) => (degree * Math.PI) / 180
  const lat1 = toRad(start.lat)
  const lat2 = toRad(end.lat)
  const dLat = lat2 - lat1
  const dLon = toRad(end.lon - start.lon)
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(a)))
}

export function pathDistance(points: LonLat[]): number {
  let total = 0
  for (let index = 1; index < points.length; index += 1) {
    total += distanceMeters(points[index - 1], points[index])
  }
  return total
}

export function ringArea(points: LonLat[]): number {
  if (points.length < 3) return 0
  let total = 0
  for (let index = 0; index < points.length; index += 1) {
    const current = points[index]
    const next = points[(index + 1) % points.length]
    total +=
      ((next.lon - current.lon) * Math.PI) /
      180 *
      (2 + Math.sin((current.lat * Math.PI) / 180) + Math.sin((next.lat * Math.PI) / 180))
  }
  return Math.abs((total * EARTH_RADIUS_M * EARTH_RADIUS_M) / 2)
}

export function heightMeters(start: number, end: number): number {
  return Math.abs(end - start)
}

export function formatMeasure(kind: "distance" | "area" | "height", value: number): string {
  if (kind === "area") {
    return value >= 1_000_000 ? `${(value / 1_000_000).toFixed(2)} 平方千米` : `${value.toFixed(0)} 平方米`
  }
  const noun = kind === "height" ? "高度" : "距离"
  const body = value >= 1000 ? `${(value / 1000).toFixed(2)} 千米` : `${value.toFixed(0)} 米`
  return `${noun} ${body}`
}
