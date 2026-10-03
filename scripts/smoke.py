#!/usr/bin/env python3
"""对默认部署做一次端到端冒烟。

`docker compose up` 之后跑这个脚本，确认三件事同时成立：
网关能出静态页面、/api 走通前缀转换、切片路由真的出图。

不依赖任何第三方库，`python scripts/smoke.py [base_url]` 即可。
默认指向 compose 暴露的网关端口。
"""

import io
import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE = "http://127.0.0.1:8080"
TINY_ACQUIRED_AT = "2024-01-01T00:00:00+00:00"
# 造测试影像用的范围（西、南、东、北），同时用来算瓦片行列号。
SMOKE_BOUNDS = (100.0, 20.0, 101.0, 21.0)


class Failure(Exception):
    pass


def fetch(url: str, *, method: str = "GET", body: bytes | None = None, timeout: float = 20.0):
    request = urllib.request.Request(url, data=body, method=method)
    if body is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read(), dict(response.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers)
    except urllib.error.URLError as exc:
        raise Failure(f"{url} 连不上：{exc.reason}") from exc


def check(label: str, ok: bool, detail: str = "") -> bool:
    mark = "PASS" if ok else "FAIL"
    line = f"[{mark}] {label}"
    if detail:
        line += f" — {detail}"
    print(line)
    return ok


def main() -> int:
    base = (sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE).rstrip("/")
    print(f"冒烟目标：{base}\n")
    results: list[bool] = []

    # 1. 静态页面
    try:
        status, body, _ = fetch(f"{base}/")
        results.append(check("网关出静态首页", status == 200 and b"<div id=\"app\">" in body, f"HTTP {status}"))
    except Failure as exc:
        results.append(check("网关出静态首页", False, str(exc)))

    # 2. 目录 API（验证 /api 前缀被正确剥掉）
    try:
        status, body, _ = fetch(f"{base}/api/providers")
        rows = json.loads(body) if status == 200 else []
        results.append(
            check(
                "目录 API 经网关可达",
                status == 200 and isinstance(rows, list),
                f"HTTP {status}，{len(rows)} 个数据源" if status == 200 else f"HTTP {status}",
            )
        )
        drapable = [row["id"] for row in rows if row.get("drape")]
        print(f"       可铺到地球的源：{'、'.join(drapable) or '（无）'}")
    except Failure as exc:
        results.append(check("目录 API 经网关可达", False, str(exc)))

    # 3. 瓦片路由存在且路径校验生效
    try:
        status, _, _ = fetch(f"{base}/cog/tiles/WebMercatorQuad/0/0/0.png?url=../../etc/passwd")
        results.append(check("切片路由挡得住路径穿越", status == 403, f"HTTP {status}"))
    except Failure as exc:
        results.append(check("切片路由挡得住路径穿越", False, str(exc)))

    # 4. 耗时采样如实报告
    try:
        status, body, _ = fetch(f"{base}/api/tiles/timing")
        payload = json.loads(body) if status == 200 else {}
        results.append(
            check(
                "耗时端点不谎报缓存命中",
                status == 200 and payload.get("cache") in ("none", "unverified"),
                f"cache={payload.get('cache')} sampled={payload.get('sampled')}",
            )
        )
    except Failure as exc:
        results.append(check("耗时端点不谎报缓存命中", False, str(exc)))

    # 5. 上传一景 GeoTIFF → 入库 → 出瓦片。这是 002 声称的主链路，
    #    之前只能靠手 curl 演示，现在脚本里跑通。
    cog = make_tiny_cog()
    try:
        upload = upload_cog(base, cog)
        results.append(
            check("上传返回 202 并给出任务号", upload.get("status") == 202, f"status={upload.get('status')}")
        )
        job = wait_for_job(base, upload["id"])
        results.append(
            check(
                "入库任务跑到终态",
                job.get("status") in ("success", "failed"),
                f"status={job.get('status')} error={job.get('error')}",
            )
        )
        if job.get("status") == "success":
            item_id = job.get("payload", {}).get("item_id")
            layer = layer_spec(base, item_id)
            results.append(
                check("入库产物给出可加载的图层", layer.get("type") in ("xyz", "wmts", "cog"), f"type={layer.get('type')}")
            )
            zoom = 5
            x, y = tile_inside(SMOKE_BOUNDS, zoom)
            status, tile_body, _ = fetch(f"{base}{expand(layer['url'], zoom, x, y)}")
            results.append(
                check(
                    "该图层的瓦片真的能取到",
                    status == 200 and tile_body[:4] == b"\x89PNG",
                    f"z{zoom}/{x}/{y} HTTP {status}，{len(tile_body)} 字节",
                )
            )
            capabilities = layer.get("wmts_capabilities")
            if capabilities:
                status, body, _ = fetch(f"{base}{capabilities}")
                identifier = (layer.get("wmts_layer") or "").encode()
                results.append(
                    check(
                        "WMTS capabilities 可取到且指向该图层",
                        status == 200 and b"<Capabilities" in body and identifier in body,
                        f"HTTP {status}",
                    )
                )
            asset = url_param(layer["url"])
            status, body, _ = fetch(
                f"{base}/api/tiles/timing",
            )
            timing = json.loads(body) if status == 200 else {}
            results.append(
                check(
                    "耗时端点如实报告未采样状态",
                    timing.get("sampled") is False and timing.get("duration_ms") is None,
                    f"sampled={timing.get('sampled')}",
                )
            )
            status, body, _ = fetch(
                f"{base}/api/tiles/timing?url={urllib.parse.quote(asset, safe='')}"
                f"&z={zoom}&x={x}&y={y}"
            )
            timing = json.loads(body) if status == 200 else {}
            results.append(
                check(
                    "耗时端点实测到一次真实瓦片",
                    timing.get("sampled") is True and timing.get("status") == 200,
                    f"{timing.get('duration_ms')} ms，cache={timing.get('cache')}",
                )
            )
    except Failure as exc:
        results.append(check("入库主链路", False, str(exc)))

    passed = sum(results)
    print(f"\n{passed}/{len(results)} 通过")
    return 0 if passed == len(results) else 1


def make_tiny_cog() -> bytes:
    """现场造一景 COG，不依赖仓库里带二进制测试数据。

    块大小要取 256 而不是 128：等于影像宽度时 GDAL 会退化成条带存储，
    那样 `is_tiled` 为假，测的就不是 COG 路径了。
    """
    import numpy
    import rasterio
    from rasterio.transform import from_bounds

    buffer = io.BytesIO()
    profile = {
        "driver": "GTiff",
        "height": 128,
        "width": 128,
        "count": 3,
        "dtype": "uint8",
        "crs": "EPSG:4326",
        "transform": from_bounds(*SMOKE_BOUNDS, 128, 128),
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
        "compress": "deflate",
    }
    with rasterio.open(buffer, "w", **profile) as dataset:
        # 三个波段各偏一点的横向渐变，肉眼能看出方向对不对
        ramp = numpy.tile(numpy.linspace(0, 255, 128, dtype="uint8"), (128, 1))
        dataset.write(
            numpy.stack([ramp, numpy.roll(ramp, 40, axis=1), numpy.roll(ramp, 80, axis=1)])
        )
    return buffer.getvalue()


def tile_inside(bounds: tuple[float, float, float, float], z: int) -> tuple[int, int]:
    """算一个落在影像范围内的 WebMercatorQuad 瓦片。

    不硬编码行列号——换测试影像就得跟着换，越硬编码越容易在别的
    瓦片方案下悄悄取到越界瓦片，然后误判成"切片坏了"。
    """
    west, south, east, north = bounds
    lon = (west + east) / 2
    lat = (south + north) / 2
    scale = 2**z
    x = int((lon + 180.0) / 360.0 * scale)
    lat_radians = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(lat_radians)) / math.pi) / 2.0 * scale)
    return x, y


def upload_cog(base: str, payload: bytes) -> dict:
    boundary = "----webgissmoke"
    parts = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"smoke.tif\"\r\n"
        "Content-Type: image/tiff\r\n\r\n",
    ]
    head = "".join(parts).encode() + payload + f"\r\n--{boundary}\r\n".encode()
    tail = (
        'Content-Disposition: form-data; name="acquired_at"\r\n\r\n'
        f"{TINY_ACQUIRED_AT}\r\n--{boundary}--\r\n"
    ).encode()
    request = urllib.request.Request(
        f"{base}/api/jobs/uploads",
        data=head + tail,
        method="POST",
    )
    request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return {"status": response.status, **json.loads(response.read())}
    except urllib.error.HTTPError as exc:
        raise Failure(f"上传失败 HTTP {exc.code}：{exc.read()[:300]!r}") from exc
    except urllib.error.URLError as exc:
        raise Failure(f"上传连不上：{exc.reason}") from exc


TINY_ACQUIRED_AT = "2024-01-01T00:00:00+00:00"


def expand(template: str, z: int, x: int, y: int) -> str:
    """把瓦片模板里的占位符填上。XYZ 与 WMTS 两种写法都认。"""
    return (
        template.replace("{z}", str(z))
        .replace("{x}", str(x))
        .replace("{y}", str(y))
        .replace("{TileMatrix}", str(z))
        .replace("{TileCol}", str(x))
        .replace("{TileRow}", str(y))
    )


def url_param(layer_url: str, key: str = "url") -> str:
    """从图层地址里取出查询参数。

    拿 encode 过的原串去当参数会二次编码，路径校验会直接拒掉——所以这里
    走 parse_qs 让它自己解码。
    """
    return urllib.parse.parse_qs(urllib.parse.urlparse(layer_url).query).get(key, [""])[0]


def wait_for_job(base: str, job_id: str, *, attempts: int = 90, delay: float = 1.0) -> dict:
    for _ in range(attempts):
        status, body, _ = fetch(f"{base}/api/jobs/{job_id}")
        if status != 200:
            raise Failure(f"查询任务失败 HTTP {status}")
        payload = json.loads(body)
        if payload["status"] in ("success", "failed"):
            return payload
        time.sleep(delay)
    raise Failure(f"任务 {job_id} 在 {attempts} 秒内没到终态")


def layer_spec(base: str, item_id: str) -> dict:
    status, body, _ = fetch(f"{base}/api/items/{item_id}/layer")
    if status != 200:
        raise Failure(f"取图层描述失败 HTTP {status}")
    return json.loads(body)


if __name__ == "__main__":
    sys.exit(main())