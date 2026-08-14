"""WGS84、GCJ-02 与 BD-09 的离线坐标转换和输入校验。"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal


CoordinateSystem = Literal["WGS84", "GCJ02", "BD09"]

PI = math.pi
X_PI = PI * 3000.0 / 180.0
A = 6378245.0
EE = 0.00669342162296594323


@dataclass(frozen=True)
class Coordinate:
    lon: float
    lat: float


@dataclass(frozen=True)
class ValidationIssue:
    level: Literal["error", "warning", "info"]
    code: str
    message: str


@dataclass(frozen=True)
class ValidationResult:
    coordinate: Coordinate | None
    issues: tuple[ValidationIssue, ...]

    @property
    def has_error(self) -> bool:
        return any(issue.level == "error" for issue in self.issues)


SYSTEM_LABELS: dict[CoordinateSystem, str] = {
    "WGS84": "WGS84",
    "GCJ02": "GCJ-02",
    "BD09": "BD-09",
}


def is_outside_china(lon: float, lat: float) -> bool:
    """公开算法常用的中国大陆粗略外包范围。"""
    return lon < 72.004 or lon > 137.8347 or lat < 0.8293 or lat > 55.8271


def _is_likely_mainland(lon: float, lat: float) -> bool:
    return 73 <= lon <= 135 and 18 <= lat <= 54


def _transform_lat(x: float, y: float) -> float:
    result = (
        -100.0
        + 2.0 * x
        + 3.0 * y
        + 0.2 * y * y
        + 0.1 * x * y
        + 0.2 * math.sqrt(abs(x))
    )
    result += (20.0 * math.sin(6.0 * x * PI) + 20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0
    result += (20.0 * math.sin(y * PI) + 40.0 * math.sin(y / 3.0 * PI)) * 2.0 / 3.0
    result += (160.0 * math.sin(y / 12.0 * PI) + 320.0 * math.sin(y * PI / 30.0)) * 2.0 / 3.0
    return result


def _transform_lon(x: float, y: float) -> float:
    result = (
        300.0
        + x
        + 2.0 * y
        + 0.1 * x * x
        + 0.1 * x * y
        + 0.1 * math.sqrt(abs(x))
    )
    result += (20.0 * math.sin(6.0 * x * PI) + 20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0
    result += (20.0 * math.sin(x * PI) + 40.0 * math.sin(x / 3.0 * PI)) * 2.0 / 3.0
    result += (150.0 * math.sin(x / 12.0 * PI) + 300.0 * math.sin(x / 30.0 * PI)) * 2.0 / 3.0
    return result


def wgs84_to_gcj02(lon: float, lat: float) -> Coordinate:
    if is_outside_china(lon, lat):
        return Coordinate(lon, lat)

    d_lat = _transform_lat(lon - 105.0, lat - 35.0)
    d_lon = _transform_lon(lon - 105.0, lat - 35.0)
    rad_lat = lat / 180.0 * PI
    magic = math.sin(rad_lat)
    magic = 1 - EE * magic * magic
    sqrt_magic = math.sqrt(magic)
    d_lat = d_lat * 180.0 / ((A * (1 - EE) / (magic * sqrt_magic)) * PI)
    d_lon = d_lon * 180.0 / ((A / sqrt_magic) * math.cos(rad_lat) * PI)
    return Coordinate(lon + d_lon, lat + d_lat)


def gcj02_to_wgs84(lon: float, lat: float) -> Coordinate:
    """用二分迭代反算，避免一次近似造成的残余误差。"""
    if is_outside_china(lon, lat):
        return Coordinate(lon, lat)

    min_lon, max_lon = lon - 0.02, lon + 0.02
    min_lat, max_lat = lat - 0.02, lat + 0.02
    candidate = Coordinate(lon, lat)

    for _ in range(32):
        candidate = Coordinate((min_lon + max_lon) / 2, (min_lat + max_lat) / 2)
        transformed = wgs84_to_gcj02(candidate.lon, candidate.lat)
        delta_lon = transformed.lon - lon
        delta_lat = transformed.lat - lat
        if abs(delta_lon) < 1e-7 and abs(delta_lat) < 1e-7:
            break
        if delta_lon > 0:
            max_lon = candidate.lon
        else:
            min_lon = candidate.lon
        if delta_lat > 0:
            max_lat = candidate.lat
        else:
            min_lat = candidate.lat
    return candidate


def gcj02_to_bd09(lon: float, lat: float) -> Coordinate:
    z = math.sqrt(lon * lon + lat * lat) + 0.00002 * math.sin(lat * X_PI)
    theta = math.atan2(lat, lon) + 0.000003 * math.cos(lon * X_PI)
    return Coordinate(z * math.cos(theta) + 0.0065, z * math.sin(theta) + 0.006)


def bd09_to_gcj02(lon: float, lat: float) -> Coordinate:
    x, y = lon - 0.0065, lat - 0.006
    z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * X_PI)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * X_PI)
    return Coordinate(z * math.cos(theta), z * math.sin(theta))


def convert_coordinate(
    coordinate: Coordinate,
    source: CoordinateSystem,
    target: CoordinateSystem,
) -> Coordinate:
    if source == target:
        return coordinate
    if source == "WGS84":
        gcj = wgs84_to_gcj02(coordinate.lon, coordinate.lat)
        return gcj if target == "GCJ02" else gcj02_to_bd09(gcj.lon, gcj.lat)
    if source == "GCJ02":
        return (
            gcj02_to_wgs84(coordinate.lon, coordinate.lat)
            if target == "WGS84"
            else gcj02_to_bd09(coordinate.lon, coordinate.lat)
        )
    gcj = bd09_to_gcj02(coordinate.lon, coordinate.lat)
    return gcj if target == "GCJ02" else gcj02_to_wgs84(gcj.lon, gcj.lat)


def validate_coordinate(
    lon_input: object,
    lat_input: object,
    source: CoordinateSystem,
) -> ValidationResult:
    lon_text = "" if lon_input is None else str(lon_input).strip()
    lat_text = "" if lat_input is None else str(lat_input).strip()
    if not lon_text or not lat_text:
        return ValidationResult(
            None,
            (ValidationIssue("error", "EMPTY", "经度或纬度为空。"),),
        )

    try:
        lon, lat = float(lon_text), float(lat_text)
    except (TypeError, ValueError):
        return ValidationResult(
            None,
            (ValidationIssue("error", "NOT_NUMERIC", "经纬度必须是数字。"),),
        )
    if not math.isfinite(lon) or not math.isfinite(lat):
        return ValidationResult(
            None,
            (ValidationIssue("error", "NOT_FINITE", "经纬度必须是有限数值。"),),
        )

    issues: list[ValidationIssue] = []
    obvious_swap = abs(lon) <= 90 < abs(lat) <= 180
    likely_swap = _is_likely_mainland(lat, lon) and not _is_likely_mainland(lon, lat) and abs(lat) <= 180

    if obvious_swap or likely_swap:
        issues.append(
            ValidationIssue(
                "error",
                "LIKELY_SWAPPED",
                f"疑似经纬度写反；交换后为 {lat:.6f}, {lon:.6f}。",
            )
        )
    else:
        if not -180 <= lon <= 180:
            issues.append(ValidationIssue("error", "LON_RANGE", "经度必须在 -180 到 180 之间。"))
        if not -90 <= lat <= 90:
            issues.append(ValidationIssue("error", "LAT_RANGE", "纬度必须在 -90 到 90 之间。"))

    if any(issue.level == "error" for issue in issues):
        return ValidationResult(None, tuple(issues))

    if abs(lon) < 1e-12 and abs(lat) < 1e-12:
        issues.append(
            ValidationIssue(
                "warning",
                "ZERO_COORDINATE",
                "坐标为 0,0，通常代表缺失值或默认值，请核实。",
            )
        )

    reference = bd09_to_gcj02(lon, lat) if source == "BD09" else Coordinate(lon, lat)
    if is_outside_china(reference.lon, reference.lat):
        issues.append(
            ValidationIssue(
                "warning",
                "OUTSIDE_CHINA",
                "点位位于中国大陆常用加偏范围外；WGS84 与 GCJ-02 按该公开算法不加偏，BD-09 仅作数学换算。",
            )
        )
    return ValidationResult(Coordinate(lon, lat), tuple(issues))


def target_column_names(target: CoordinateSystem) -> tuple[str, str]:
    suffix = target.lower()
    return f"lon_{suffix}", f"lat_{suffix}"
