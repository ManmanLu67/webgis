import re

_TOKEN = re.compile(r"\{\$([a-zA-Z0-9_=]+)\}|\{([a-zA-Z0-9_]+)\}")


def normalize_xyz_template(template: str) -> str:
    """把 {$z}、{z}、{$ovtm=time} 收成 Cesium 能用的 {z}/{x}/{y} 与 {time}。"""
    if not isinstance(template, str) or not template.strip():
        raise ValueError("URL 模板不能为空")

    def replace(match: re.Match) -> str:
        raw = match.group(1) or match.group(2)
        lowered = raw.lower()
        if lowered in {"z", "x", "y", "time"}:
            return "{" + lowered + "}"
        if lowered in {"ovtm=time", "ovtm"}:
            return "{time}"
        raise ValueError(f"不认识的占位符 {{{raw}}}")

    normalized = _TOKEN.sub(replace, template.strip())
    for required in ("{z}", "{x}", "{y}"):
        if required not in normalized:
            raise ValueError("URL 模板必须包含 z、x、y")
    return normalized


def apply_time(template: str, when: str | None) -> str:
    if "{time}" not in template:
        return template
    if not when:
        raise ValueError("模板含时间占位符时必须提供 time")
    return template.replace("{time}", when)
