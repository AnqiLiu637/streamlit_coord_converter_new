"""CSV 读取、列识别和批量转换。"""

from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
from pathlib import Path
import re

import pandas as pd

from coordinate_transform import (
    CoordinateSystem,
    convert_coordinate,
    target_column_names,
    validate_coordinate,
)


DEFAULT_SAMPLE_CSV = """name,lon_wgs84,lat_wgs84
天安门,116.397128,39.908722
上海外滩,121.490317,31.236305
广州塔,113.32452,23.106414
成都天府广场,104.065751,30.657457
西安钟楼,108.945227,34.263161
深圳市民中心,114.058921,22.546248
杭州西湖,120.148429,30.236764
武汉黄鹤楼,114.302976,30.543141
南京新街口,118.789423,32.041546
重庆解放碑,106.577023,29.559416
错点_经纬度写反,39.908722,116.397128
错点_落在巴黎,2.352222,48.856614
错点_落在东海,123.5,30.0
错点_零值,0.0,0.0
"""


@dataclass(frozen=True)
class BatchSummary:
    total: int
    success: int
    warnings: int
    errors: int
    lon_output: str
    lat_output: str
    status_output: str
    issue_output: str


def load_sample_csv(project_dir: Path) -> bytes:
    """读取随项目发布的示例；文件缺失时使用代码内置副本。"""
    candidates = (
        project_dir / "sample_data" / "coordinate_sample.csv",
        project_dir / "sample_data" / "坐标点位_待转换.csv",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.read_bytes()
    return DEFAULT_SAMPLE_CSV.encode("utf-8-sig")


def read_csv_bytes(content: bytes) -> tuple[pd.DataFrame, str]:
    """优先读取 UTF-8，兼容常见的 GB18030 中文 CSV。"""
    last_error: UnicodeDecodeError | None = None
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            text = content.decode(encoding)
            frame = pd.read_csv(StringIO(text), dtype=str, keep_default_na=False)
            return frame, encoding
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ValueError("CSV 编码无法识别，请另存为 UTF-8 或 GB18030 后重试。") from last_error


def _normalized(value: str) -> str:
    return re.sub(r"[\s_\-（）()]", "", value.lower())


def detect_coordinate_columns(columns: list[str], source: CoordinateSystem) -> tuple[str, str]:
    system_tokens: dict[CoordinateSystem, tuple[str, ...]] = {
        "WGS84": ("wgs84", "wgs", "gps"),
        "GCJ02": ("gcj02", "gcj", "火星"),
        "BD09": ("bd09", "bd", "百度"),
    }
    lon_tokens = ("lon", "lng", "longitude", "x", "经度")
    lat_tokens = ("lat", "latitude", "y", "纬度")
    normalized = [(column, _normalized(column)) for column in columns]

    def find(axis_tokens: tuple[str, ...]) -> str:
        for column, key in normalized:
            if any(_normalized(token) in key for token in axis_tokens) and any(
                _normalized(token) in key for token in system_tokens[source]
            ):
                return column
        for column, key in normalized:
            if any(key == _normalized(token) for token in axis_tokens):
                return column
        for column, key in normalized:
            if any(_normalized(token) in key for token in axis_tokens):
                return column
        return ""

    return find(lon_tokens), find(lat_tokens)


def unique_column(columns: list[str], desired: str) -> str:
    if desired not in columns:
        return desired
    index = 2
    while f"{desired}_{index}" in columns:
        index += 1
    return f"{desired}_{index}"


def process_dataframe(
    frame: pd.DataFrame,
    lon_column: str,
    lat_column: str,
    source: CoordinateSystem,
    target: CoordinateSystem,
) -> tuple[pd.DataFrame, BatchSummary]:
    result = frame.copy()
    existing = list(result.columns)
    lon_desired, lat_desired = target_column_names(target)
    lon_output = unique_column(existing, lon_desired)
    lat_output = unique_column(existing + [lon_output], lat_desired)
    status_output = unique_column(existing + [lon_output, lat_output], "转换状态")
    issue_output = unique_column(existing + [lon_output, lat_output, status_output], "异常说明")

    result[lon_output] = None
    result[lat_output] = None
    result[status_output] = ""
    result[issue_output] = ""

    success = warnings = errors = 0
    for index, row in result.iterrows():
        validation = validate_coordinate(row[lon_column], row[lat_column], source)
        messages = "；".join(issue.message for issue in validation.issues)
        result.at[index, issue_output] = messages
        if validation.has_error or validation.coordinate is None:
            result.at[index, status_output] = "错误"
            errors += 1
            continue

        converted = convert_coordinate(validation.coordinate, source, target)
        result.at[index, lon_output] = round(converted.lon, 8)
        result.at[index, lat_output] = round(converted.lat, 8)
        if any(issue.level == "warning" for issue in validation.issues):
            result.at[index, status_output] = "警告"
            warnings += 1
        else:
            result.at[index, status_output] = "成功"
            success += 1

    return result, BatchSummary(
        total=len(result),
        success=success,
        warnings=warnings,
        errors=errors,
        lon_output=lon_output,
        lat_output=lat_output,
        status_output=status_output,
        issue_output=issue_output,
    )


def dataframe_to_excel_csv(frame: pd.DataFrame) -> bytes:
    """添加 UTF-8 BOM，便于常见 Excel 版本直接识别中文。"""
    return frame.to_csv(index=False, lineterminator="\r\n").encode("utf-8-sig")
