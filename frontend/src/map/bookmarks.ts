export interface Bookmark {
  name: string
  lon: number
  lat: number
  height: number
}

export function coordinateError(lon: number, lat: number): string | null {
  if (Number.isNaN(lon) || Number.isNaN(lat)) return "请输入数字经纬度"
  if (lon < -180 || lon > 180 || lat < -90 || lat > 90) return "经度须在 -180 到 180，纬度须在 -90 到 90"
  return null
}

export function addBookmark(bookmarks: Bookmark[], bookmark: Bookmark): Bookmark[] {
  return [...bookmarks.filter((item) => item.name !== bookmark.name), bookmark]
}

const STORAGE_KEY = "webgis.bookmarks"

export function readBookmarks(storage: Pick<Storage, "getItem"> = localStorage): Bookmark[] {
  try {
    const parsed = JSON.parse(storage.getItem(STORAGE_KEY) ?? "[]")
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export function writeBookmarks(bookmarks: Bookmark[], storage: Pick<Storage, "setItem"> = localStorage): void {
  storage.setItem(STORAGE_KEY, JSON.stringify(bookmarks))
}
