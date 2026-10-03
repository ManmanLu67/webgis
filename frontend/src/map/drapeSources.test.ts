import { describe, expect, it } from "vitest"
import { layerPickerSources } from "./drapeSources"

describe("图层弹层", () => {
  it("只留下能铺上地球的可用源", () => {
    const picked = layerPickerSources([
      { id: "gibs", availability: "ready", drape: true },
      { id: "public_stac", availability: "ready", drape: true },
      { id: "custom_xyz", availability: "ready", drape: true },
      { id: "local_file", availability: "ready", drape: false },
      { id: "tianditu", availability: "needs_config", drape: false },
      { id: "jilin1", availability: "skeleton", drape: false },
      { id: "tencent_map", availability: "ready", drape: false },
    ])
    expect(picked.map((source) => source.id)).toEqual(["gibs", "public_stac", "custom_xyz"])
  })
})
