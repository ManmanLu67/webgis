<script setup lang="ts">
import { computed, ref } from "vue"
import { loadTimes as fetchTimes, type CatalogSource, type Job } from "./api/client"
import { describeJob, jobTitle } from "./api/jobs"
import type { Bookmark } from "./map/bookmarks"
import { layerPickerSources } from "./map/drapeSources"
import { parseLayerDate } from "./map/layerDate"
import { groupLayers, type ManagedLayer } from "./map/layers"
import type { SketchKind } from "./map/sketchKind"
import { sceneOptionLabel, type SwipeScene } from "./map/swipe"

type TimeChoice = { id: string; title: string; time: string }

const props = defineProps<{
  layers: ManagedLayer[]
  message: string
  measureText: string
  bookmarks: Bookmark[]
  sources: CatalogSource[]
  scenes: SwipeScene[]
  tilesetConfigured: boolean
  sketching: boolean
  annotationCount: number
  jobs: Job[]
}>()

const emit = defineEmits<{
  visible: [id: string, value: boolean]
  opacity: [id: string, value: number]
  move: [id: string, direction: "up" | "down"]
  remove: [id: string]
  // 用联合类型而不是 string：按钮里写 emit('sketch', 'poitn') 会被当场拦下。
  // 运行时还有 isSketchKind 兜底，但那只是第二道防线，主要靠这一条。
  sketch: [kind: SketchKind]
  finish: []
  eraseLastAnnotation: []
  clearAnnotations: []
  clearMeasure: []
  exportGeojson: []
  copy: []
  fly: [lon: number, lat: number]
  flyExtent: []
  saveBookmark: [name: string, lon: number, lat: number]
  useBookmark: [bookmark: Bookmark]
  customXyz: [template: { name: string; url_template: string; tiling_scheme: string; max_zoom: number; layer_kind: string; time: string }]
  loadSource: [payload: { id: string; name: string; datetime?: string; bbox?: number[] }]
  uploadCog: [payload: { file: File; acquiredAt: string }]
  refreshJobs: []
  cancelJob: [jobId: string]
  sampleTiming: []
  home: []
}>()

const imageryOn = defineModel<boolean>("imageryOn", { default: true })
const terrainOn = defineModel<boolean>("terrainOn", { default: true })
const tilesetOn = defineModel<boolean>("tilesetOn", { default: true })
const opacity = defineModel<number>("opacity", { default: 1 })
const screenError = defineModel<number>("screenError", { default: 16 })
const swipeOn = defineModel<boolean>("swipeOn", { default: false })
const leftId = defineModel<string>("leftId", { default: "" })
const rightId = defineModel<string>("rightId", { default: "" })
const xyzName = defineModel<string>("xyzName", { default: "" })
const xyzUrl = defineModel<string>("xyzUrl", { default: "" })
const xyzScheme = defineModel<string>("xyzScheme", { default: "WebMercator" })
const xyzKind = defineModel<string>("xyzKind", { default: "imagery" })
const xyzZoom = defineModel<number>("xyzZoom", { default: 18 })
const xyzTime = defineModel<string>("xyzTime", { default: "" })
const lon = defineModel<number>("lon", { default: 116 })
const lat = defineModel<number>("lat", { default: 40 })
const bookmarkName = defineModel<string>("bookmarkName", { default: "" })

const openSection = ref("view")
const openGroup = ref<string | null>(null)
const selectedLayer = ref<string | null>(null)
const pickerOpen = ref(false)
const pickerStep = ref<"sources" | "extent" | "time" | "template">("sources")
const picked = ref<CatalogSource | null>(null)
const times = ref<TimeChoice[]>([])
const selectedTime = ref("")
const pickerError = ref("")
const west = ref("")
const south = ref("")
const east = ref("")
const north = ref("")
const customDate = ref("")
const uploadFile = ref<File | null>(null)
const uploadDate = ref(today())

/** 采集日期默认今天：多数情况下用户传的就是刚拍的那一景。 */
function today(): string {
  const now = new Date()
  const month = `${now.getMonth() + 1}`.padStart(2, "0")
  const day = `${now.getDate()}`.padStart(2, "0")
  return `${now.getFullYear()}-${month}-${day}`
}

const uploadHint = ref("")
const canUpload = computed(() => uploadFile.value !== null && uploadDate.value !== "")

const sections = [
  { id: "view", label: "视图" },
  { id: "layers", label: "图层" },
  { id: "ingest", label: "入库" },
  { id: "draw", label: "标注" },
  { id: "measure", label: "量算" },
  { id: "place", label: "定位" },
]

const pickerSources = computed(() => layerPickerSources(props.sources))

function onFilePicked(event: Event): void {
  const file = (event.target as HTMLInputElement).files?.[0] ?? null
  uploadFile.value = file
  uploadHint.value = ""
  if (file && !/\.(tif|tiff)$/i.test(file.name)) {
    // 后端也会拒，但在这里先说清楚，省得白等一次上传
    uploadHint.value = "只接受 .tif 或 .tiff"
  }
}

/** 模板里的事件处理器只传值，不做类型断言。
 *
 * 原来是在模板里写 `($event.target as HTMLInputElement).checked`，两个问题：
 * 模板表达式不该夹带类型断言（读起来费劲，而且 lint 规则认不出类型名，
 * 会误报成"未定义属性"）；断言散在模板各处，改一次要动好几行。
 */
function checkedOf(event: Event): boolean {
  return (event.target as HTMLInputElement).checked
}

function valueOf(event: Event): number {
  return Number((event.target as HTMLInputElement).value)
}

function submitUpload(): void {
  if (!uploadFile.value || !canUpload.value) return
  emit("uploadCog", { file: uploadFile.value, acquiredAt: uploadDate.value })
  uploadFile.value = null
  uploadHint.value = "已提交，正在排队"
}

function toggleSection(id: string): void {
  const opening = openSection.value !== id
  openSection.value = opening ? id : ""
  openGroup.value = null
  selectedLayer.value = null
  pickerOpen.value = opening && id === "layers"
  resetPicker()
}

function resetPicker(): void {
  pickerStep.value = "sources"
  picked.value = null
  times.value = []
  selectedTime.value = ""
  customDate.value = ""
  pickerError.value = ""
}

function openPicker(): void {
  pickerOpen.value = true
  resetPicker()
}

function toggleGroup(name: string): void {
  openGroup.value = openGroup.value === name ? null : name
  selectedLayer.value = null
}

function toggleLayer(id: string): void {
  selectedLayer.value = selectedLayer.value === id ? null : id
}

function extentBbox(): number[] | null {
  const raw = [west.value, south.value, east.value, north.value]
  if (raw.some((value) => value.trim() === "")) return null
  const [minx, miny, maxx, maxy] = raw.map(Number)
  if ([minx, miny, maxx, maxy].some((value) => Number.isNaN(value))) return null
  if (minx >= maxx || miny >= maxy) return null
  return [minx, miny, maxx, maxy]
}

async function chooseSource(source: CatalogSource): Promise<void> {
  picked.value = source
  pickerError.value = ""
  if (source.picker === "template") {
    pickerStep.value = "template"
    return
  }
  if (source.picker === "extent") {
    pickerStep.value = "extent"
    return
  }
  await loadTimes()
}

async function loadTimes(): Promise<void> {
  if (!picked.value) return
  // 没有范围就是 undefined，不要拿 [] 顶上：空数组会被当成"给了范围但长度不对"。
  const bbox = picked.value.picker === "extent" ? (extentBbox() ?? undefined) : undefined
  if (picked.value.picker === "extent" && !bbox) {
    pickerError.value = "公开目录检索需要范围"
    return
  }
  pickerError.value = ""
  try {
    const found = await fetchTimes(picked.value.id, bbox)
    times.value = found
    selectedTime.value = found[0]?.time ?? ""
    if (!found.length) {
      pickerError.value = "没有可加载的图层"
      return
    }
    pickerStep.value = "time"
  } catch (error) {
    pickerError.value = error instanceof Error ? error.message : "检索失败"
  }
}

function confirmTime(): void {
  if (!picked.value) return
  const typed = customDate.value.trim()
  const datetime = typed ? parseLayerDate(typed) : selectedTime.value
  if (typed && !datetime) {
    pickerError.value = "时间写成 年-月-日，例如 2026-09-23"
    return
  }
  if (!datetime) return
  const bbox = picked.value.picker === "extent" ? extentBbox() ?? undefined : undefined
  emit("loadSource", {
    id: picked.value.id,
    name: picked.value.name,
    datetime,
    bbox,
  })
  pickerOpen.value = false
  resetPicker()
}

function submitCustom(): void {
  emit("customXyz", {
    name: xyzName.value,
    url_template: xyzUrl.value,
    tiling_scheme: xyzScheme.value,
    max_zoom: xyzZoom.value,
    layer_kind: xyzKind.value,
    time: xyzTime.value,
  })
  pickerOpen.value = false
  resetPicker()
}
</script>

<template>
  <aside class="dock">
    <header class="brand">
      <button type="button" class="home" aria-label="回到初始视角" title="回到初始视角" @click="emit('home')">
        <svg class="globe-mark" viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
          <!-- 球体的轮廓与纬线是静止的：绕竖直轴自转时它们本来就不动，
               动的是经线，所以"球在转"这件事全靠下面两个椭圆。 -->
          <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.5" />
          <path
            d="M4 8h16M4 12h16M4 16h16"
            fill="none"
            stroke="currentColor"
            stroke-width="1.1"
            stroke-linecap="round"
          />
          <!-- 经线在球面上的投影是个椭圆，横向半轴 = R·cos(经度)。
               自转就是经度在变，rx 于是从 9 缩到 0 再回到 9；两个椭圆错开半个
               周期，于是一个正好侧过去时另一个正好转正 facing，读起来就是转。 -->
          <ellipse class="meridian" cx="12" cy="12" rx="9" ry="9" fill="none" stroke="currentColor" stroke-width="1.3" />
          <ellipse
            class="meridian meridian-lag"
            cx="12"
            cy="12"
            rx="9"
            ry="9"
            fill="none"
            stroke="currentColor"
            stroke-width="1.3"
          />
        </svg>
      </button>
      <strong>遥感地球</strong>
    </header>

    <div v-for="section in sections" :key="section.id" class="block">
      <button type="button" class="section" :aria-expanded="openSection === section.id" @click="toggleSection(section.id)">
        <span>{{ section.label }}</span>
        <span class="chev" :class="{ open: openSection === section.id }"></span>
      </button>

      <div v-if="openSection === section.id" class="body">
        <template v-if="section.id === 'view'">
          <label class="check"><input v-model="imageryOn" type="checkbox" /> 影像</label>
          <label class="field">透明度 <input v-model.number="opacity" type="range" min="0" max="1" step="0.05" /></label>
          <label class="check"><input v-model="terrainOn" type="checkbox" /> 地形</label>
          <label v-if="tilesetConfigured" class="check">
            <input v-model="tilesetOn" type="checkbox" />
            三维瓦片
          </label>
          <label v-if="tilesetConfigured" class="field">
            屏幕误差 <input v-model.number="screenError" type="range" min="1" max="64" step="1" />
          </label>
          <p class="muted">帧率 <span id="fps"></span></p>
          <label class="check"><input v-model="swipeOn" type="checkbox" /> 卷帘</label>
          <div v-if="swipeOn" class="nest">
            <label class="field">左侧
              <select v-model="leftId">
                <option v-for="scene in scenes" :key="scene.id" :value="scene.id">{{ sceneOptionLabel(scene) }}</option>
              </select>
            </label>
            <label class="field">右侧
              <select v-model="rightId">
                <option v-for="scene in scenes" :key="'r-' + scene.id" :value="scene.id">{{ sceneOptionLabel(scene) }}</option>
              </select>
            </label>
          </div>
        </template>

        <template v-else-if="section.id === 'layers'">
          <div v-if="pickerOpen" class="picker">
            <template v-if="pickerStep === 'sources'">
              <p v-if="pickerSources.length === 0" class="muted">没有可铺到地球的数据源</p>
              <ul v-else class="source-list">
                <li v-for="source in pickerSources" :key="source.id">
                  <button type="button" class="link" @click="chooseSource(source)">{{ source.name }}</button>
                </li>
              </ul>
            </template>
            <template v-else-if="pickerStep === 'extent'">
              <p class="muted">{{ picked?.name }} 需要地图范围</p>
              <label class="field">西 <input v-model="west" type="number" step="any" /></label>
              <label class="field">南 <input v-model="south" type="number" step="any" /></label>
              <label class="field">东 <input v-model="east" type="number" step="any" /></label>
              <label class="field">北 <input v-model="north" type="number" step="any" /></label>
              <div class="actions">
                <button type="button" class="primary" @click="loadTimes">检索时间</button>
                <button type="button" @click="pickerStep = 'sources'">返回</button>
              </div>
            </template>
            <template v-else-if="pickerStep === 'time'">
              <p class="muted">{{ picked?.name }}</p>
              <label v-for="(item, index) in times" :key="item.id" class="check">
                <span>
                  <input v-model="selectedTime" type="radio" name="layer-time" :value="item.time" />
                  {{ index === 0 ? "最近 · " : "" }}{{ item.time }}
                </span>
              </label>
              <label class="field">自选
                <input v-model="customDate" type="text" placeholder="年-月-日" />
              </label>
              <div class="actions">
                <button type="button" class="primary" @click="confirmTime">显示</button>
                <button type="button" @click="pickerStep = picked?.picker === 'extent' ? 'extent' : 'sources'">返回</button>
              </div>
            </template>
            <form v-else class="nest" @submit.prevent="submitCustom">
              <p class="muted">只填写你有权使用的地址。底图和地形不在这里。</p>
              <label class="field">名称 <input v-model="xyzName" type="text" /></label>
              <label class="field">模板 <input v-model="xyzUrl" type="text" placeholder="https://…/{z}/{x}/{y}.png" /></label>
              <label class="field">投影
                <select v-model="xyzScheme">
                  <option value="WebMercator">墨卡托</option>
                  <option value="Geographic">经纬度</option>
                </select>
              </label>
              <label class="field">种类
                <select v-model="xyzKind">
                  <option value="imagery">影像</option>
                  <option value="map">普通地图</option>
                </select>
              </label>
              <label class="field">最大级别 <input v-model.number="xyzZoom" type="number" min="0" max="24" /></label>
              <label class="field">时间 <input v-model="xyzTime" type="text" placeholder="含 {time} 时填写" /></label>
              <div class="actions">
                <button type="submit" class="primary">显示</button>
                <button type="button" @click="pickerStep = 'sources'">返回</button>
              </div>
            </form>
            <p v-if="pickerError" class="hint">{{ pickerError }}</p>
            <button type="button" class="text-btn" @click="pickerOpen = false">收起</button>
          </div>
          <button v-else type="button" class="text-btn" @click="openPicker">添加图层</button>
          <div v-for="bucket in groupLayers(layers)" :key="bucket.group" class="group">
            <button type="button" class="group-btn" @click="toggleGroup(bucket.group)">
              <span>{{ bucket.group }}</span>
            </button>
            <div v-if="openGroup === bucket.group" class="nest">
              <div v-for="layer in bucket.layers" :key="layer.id" class="layer">
                <button type="button" class="layer-name" @click="toggleLayer(layer.id)">
                  <input type="checkbox" :checked="layer.visible" @click.stop @change="emit('visible', layer.id, checkedOf($event))" />
                  {{ layer.name }}
                </button>
                <div v-if="selectedLayer === layer.id" class="detail">
                  <label class="field">透明度
                    <input type="range" min="0" max="1" step="0.05" :value="layer.opacity" @input="emit('opacity', layer.id, valueOf($event))" />
                  </label>
                  <div class="actions">
                    <button type="button" @click="emit('move', layer.id, 'up')">上移</button>
                    <button type="button" @click="emit('move', layer.id, 'down')">下移</button>
                    <button type="button" @click="emit('flyExtent')">范围</button>
                    <button type="button" class="danger" @click="emit('remove', layer.id)">删除</button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </template>

        <template v-else-if="section.id === 'ingest'">
          <p class="muted">上传 GeoTIFF，转成 COG 后由切片服务出瓦片。</p>
          <label class="field">影像 <input type="file" accept=".tif,.tiff,image/tiff" @change="onFilePicked" /></label>
          <label class="field">拍摄日期 <input v-model="uploadDate" type="date" /></label>
          <button type="button" class="primary" :disabled="!canUpload" @click="submitUpload">上传入库</button>
          <p v-if="uploadHint" class="hint">{{ uploadHint }}</p>
          <p v-if="jobs.length" class="muted">最近任务</p>
          <ul v-if="jobs.length" class="source-list">
            <li v-for="job in jobs" :key="job.id">
              <span class="job" :data-tone="describeJob(job).tone">
                {{ jobTitle(job) }} · {{ describeJob(job).label }}
              </span>
              <button
                v-if="job.status === 'queued'"
                type="button"
                class="link"
                @click="emit('cancelJob', job.id)"
              >
                取消
              </button>
            </li>
          </ul>
          <button type="button" class="text-btn" @click="emit('refreshJobs')">刷新任务</button>
          <button type="button" class="text-btn" @click="emit('sampleTiming')">采样切片耗时</button>
        </template>

        <template v-else-if="section.id === 'draw'">
          <div class="actions">
            <button type="button" @click="emit('sketch', 'point')">点</button>
            <button type="button" @click="emit('sketch', 'line')">线</button>
            <button type="button" @click="emit('sketch', 'polygon')">面</button>
          </div>
          <p v-if="sketching" class="hint">在地球上单击取点，然后按完成</p>
          <div class="actions">
            <button type="button" class="primary" @click="emit('finish')">完成</button>
            <button type="button" @click="emit('exportGeojson')">导出</button>
          </div>
          <div class="actions">
            <button
              type="button"
              class="danger"
              :disabled="annotationCount === 0"
              @click="emit('eraseLastAnnotation')"
            >
              擦除最近
            </button>
            <button
              type="button"
              class="danger"
              :disabled="annotationCount === 0"
              @click="emit('clearAnnotations')"
            >
              清除全部（{{ annotationCount }}）
            </button>
          </div>
        </template>

        <template v-else-if="section.id === 'measure'">
          <div class="actions">
            <button type="button" @click="emit('sketch', 'distance')">距离</button>
            <button type="button" @click="emit('sketch', 'area')">面积</button>
            <button type="button" @click="emit('sketch', 'height')">高度</button>
          </div>
          <p v-if="sketching" class="hint">在地球上单击取点，然后按完成</p>
          <div class="actions">
            <button type="button" class="primary" @click="emit('finish')">完成</button>
            <button type="button" class="danger" @click="emit('clearMeasure')">清除</button>
          </div>
          <p v-if="measureText" class="result">{{ measureText }}</p>
          <button type="button" class="primary" :disabled="!measureText" @click="emit('copy')">复制结果</button>
        </template>

        <template v-else>
          <label class="field">经度 <input v-model.number="lon" type="number" /></label>
          <label class="field">纬度 <input v-model.number="lat" type="number" /></label>
          <button type="button" class="primary" @click="emit('fly', lon, lat)">飞行</button>
          <label class="field">书签 <input v-model="bookmarkName" type="text" /></label>
          <button type="button" @click="emit('saveBookmark', bookmarkName, lon, lat)">保存当前位置</button>
          <ul v-if="bookmarks.length" class="source-list">
            <li v-for="bookmark in bookmarks" :key="bookmark.name">
              <button type="button" class="link" @click="emit('useBookmark', bookmark)">{{ bookmark.name }}</button>
            </li>
          </ul>
        </template>
      </div>
    </div>

    <p v-if="sketching && openSection !== 'draw' && openSection !== 'measure'" class="hint">在地球上单击取点，然后按完成</p>
    <p v-else-if="message" class="hint">{{ message }}</p>
  </aside>
</template>

<style scoped>
.dock {
  position: absolute;
  top: 16px;
  left: 16px;
  z-index: 2;
  width: 300px;
  max-height: calc(100% - 72px);
  overflow: auto;
  padding: 12px;
  color: #e8eef2;
  background: rgba(12, 18, 24, 0.88);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 14px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.35);
  font: 13px/1.45 "Segoe UI", sans-serif;
}
.brand {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 10px;
}
.brand strong { font-size: 15px; }
.home {
  width: 28px;
  height: 28px;
  padding: 0;
  display: grid;
  place-items: center;
  color: #3dbea5;
  background: none;
  border: 0;
  border-radius: 99px;
  cursor: pointer;
}
.home:hover { background: rgba(61, 190, 165, 0.16); }
/* 经线的横向半轴随自转收缩。rx 是 SVG 的几何属性，可以直接用 CSS 动画，
   不用 SMIL —— 后者在部分浏览器里已不再推荐。 */
@keyframes globe-spin {
  0% { rx: 9px; }
  50% { rx: 0px; }
  100% { rx: 9px; }
}
.meridian {
  animation: globe-spin 3.6s linear infinite;
}
/* 错开半个周期（3.6s 的一半），让两条经线始终一正一侧 */
.meridian-lag {
  animation-delay: -1.8s;
}
/* 尊重系统的"减少动态效果"设置：图标保持静止，不剥夺功能（它仍是个按钮） */
@media (prefers-reduced-motion: reduce) {
  .meridian {
    animation: none;
    rx: 6.5px;
  }
}
.block + .block { border-top: 1px solid rgba(255, 255, 255, 0.06); }
.section {
  width: 100%;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 11px 4px;
  color: inherit;
  background: none;
  border: 0;
  cursor: pointer;
  font: inherit;
}
.chev {
  width: 7px;
  height: 7px;
  border-right: 1.5px solid #9ab;
  border-bottom: 1.5px solid #9ab;
  transform: rotate(-45deg);
}
.chev.open { transform: rotate(45deg); }
.body { padding: 0 4px 12px; display: flex; flex-direction: column; gap: 8px; }
.nest {
  margin-left: 8px;
  padding-left: 10px;
  border-left: 1px solid rgba(61, 190, 165, 0.45);
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.check, .field { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.field input, .field select, button { font: inherit; }
.field input[type="text"], .field input[type="number"], .field select {
  width: 168px;
  padding: 4px 6px;
  color: #14202a;
  background: #f4f7f8;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 6px;
  color-scheme: light;
}
.field option {
  color: #14202a;
  background: #f4f7f8;
}
.field option {
  color: #14202a;
  background: #f4f7f8;
}
.group-btn, .layer-name, .text-btn, .link {
  width: 100%;
  text-align: left;
  color: inherit;
  background: none;
  border: 0;
  cursor: pointer;
  font: inherit;
}
.group-btn { display: flex; justify-content: space-between; padding: 6px 0; }
.check em {
  color: #8ea0ab;
  font-style: normal;
}
.source-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.source-list li { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; align-items: center; }
.key { width: 120px; color: #14202a; background: #f4f7f8; border: 0; border-radius: 6px; padding: 4px 6px; }
.picker {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.04);
}
.actions { display: flex; flex-wrap: wrap; gap: 6px; }
.actions button, .primary, .danger {
  padding: 4px 8px;
  color: inherit;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 6px;
  cursor: pointer;
}
.primary { background: #1f6f62; border-color: transparent; }
.danger { color: #ffb4b4; }
/* 擦除/清除在没有对应内容时必须明显不可用，否则点了才知道没反应 */
.actions button:disabled,
button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.muted, .hint { margin: 0; color: #8ea0ab; }
.hint { margin-top: 8px; color: #f3ddaa; }
.result { margin: 0; font-variant-numeric: tabular-nums; }
/* 任务状态按语义着色，失败要一眼能看出来 */
.job { color: #cfdbe2; font-size: 13px; }
.job[data-tone="wait"] { color: #8ea0ab; }
.job[data-tone="busy"] { color: #8fc7e8; }
.job[data-tone="ok"] { color: #8fd6a8; }
.job[data-tone="bad"] { color: #f0a3a3; }
</style>
