import { describe, expect, it } from "vitest"

import type { CatalogSource } from "../api/client"
import { layerPickerSources } from "./drapeSources"

function source(overrides: Partial<CatalogSource> & { id: string }): CatalogSource {
  return {
    name: overrides.id,
    mode: "reference",
    status: "implemented",
    enabled: true,
    availability: "ready",
    drape: false,
    picker: null,
    time_choices: null,
    license_note: "",
    ...overrides,
  }
}

describe("图层弹层", () => {
  it("只留下能铺到地球的可用源", () => {
    const picked = layerPickerSources([
      source({ id: "gibs", drape: true, picker: "time" }),
      source({ id: "public_stac", drape: true, picker: "extent" }),
      source({ id: "custom_xyz", drape: true, picker: "template" }),
      // 本地文件的地址要等上传发布之后才有，所以不进弹层
      source({ id: "local_file", mode: "ingest" }),
      // 需 Key、骨架、未实现的都不该出现
      source({ id: "tianditu", drape: true, picker: "template", availability: "needs_config" }),
      source({ id: "jilin1", drape: true, availability: "skeleton", status: "skeleton" }),
      source({ id: "tencent_map", drape: false }),
    ])
    expect(picked.map((item) => item.id)).toEqual(["gibs", "public_stac", "custom_xyz"])
  })

  it("一个都没有时返回空数组而不是 undefined", () => {
    expect(layerPickerSources([source({ id: "a" })])).toEqual([])
    expect(layerPickerSources([])).toEqual([])
  })

  it("availability 与 drape 都得是 ready/true 才留下", () => {
    expect(layerPickerSources([source({ id: "x", drape: true, availability: "needs_config" })])).toEqual([])
    expect(layerPickerSources([source({ id: "x", drape: false, availability: "ready" })])).toEqual([])
  })
})