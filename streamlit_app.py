"""离线坐标系转换工具的 Streamlit 入口。"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import streamlit as st

from coordinate_transform import (
    CoordinateSystem,
    SYSTEM_LABELS,
    convert_coordinate,
    validate_coordinate,
)
from csv_helpers import (
    BatchSummary,
    dataframe_to_excel_csv,
    detect_coordinate_columns,
    load_sample_csv,
    process_dataframe,
    read_csv_bytes,
)


APP_DIR = Path(__file__).resolve().parent
SAMPLE_BYTES = load_sample_csv(APP_DIR)
SAMPLE_DOWNLOAD_NAME = "坐标点位_待转换.csv"
SYSTEMS: list[CoordinateSystem] = ["WGS84", "GCJ02", "BD09"]

st.set_page_config(
    page_title="坐标系转换工具",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    html, body, [class*="css"], [data-testid="stAppViewContainer"] {
      font-family: "Source Han Sans SC", "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
    }
    [data-testid="stAppViewContainer"] { background: #f4f1e9; color: #17324d; }
    [data-testid="stHeader"] { background: transparent; }
    .block-container { max-width: 1180px; padding-top: 2rem; padding-bottom: 3rem; }
    .hero {
      background: linear-gradient(135deg, #17324d 0%, #214a67 100%);
      color: #fffdf7; border-radius: 22px; padding: 32px 36px; margin-bottom: 20px;
      box-shadow: 0 12px 32px rgba(23, 50, 77, .14);
    }
    .hero-kicker { color: #79c7bd; font-size: 14px; font-weight: 700; letter-spacing: .12em; }
    .hero h1 { font-size: clamp(30px, 5vw, 52px); line-height: 1.12; margin: 8px 0 12px; }
    .hero p { max-width: 760px; margin: 0; color: rgba(255,255,255,.78); font-size: 17px; }
    .system-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin-top:24px; }
    .system-card { border:1px solid rgba(255,255,255,.17); border-radius:14px; padding:14px 16px; background:rgba(255,255,255,.06); }
    .system-card b { color:#fff; display:block; margin-bottom:4px; }
    .system-card span { color:rgba(255,255,255,.72); font-size:13px; }
    div[data-testid="stMetric"] { background:#fffdf7; border:1px solid #d9ddd7; padding:16px; border-radius:14px; }
    div[data-testid="stMetricValue"] { color:#0f766e; }
    div[data-testid="stTabs"] button { font-weight:700; }
    .result-box { border-left:4px solid #0f766e; background:#fffdf7; padding:16px 18px; border-radius:10px; margin-top:8px; }
    .privacy { background:#e7f1ef; border:1px solid #b9d9d4; color:#17324d; padding:12px 16px; border-radius:12px; }
    .footer { color:#607181; font-size:13px; border-top:1px solid #d9ddd7; margin-top:28px; padding-top:18px; }
    @media (max-width: 760px) {
      .block-container { padding: 1rem; }
      .hero { padding:24px 20px; }
      .system-grid { grid-template-columns:1fr; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <section class="hero">
      <div class="hero-kicker">COORDINATE CONVERTER · OFFLINE ALGORITHM</div>
      <h1>坐标系转换工具</h1>
      <p>WGS84、GCJ-02、BD-09 三套坐标互转。支持单点校验与 CSV 批量处理，不调用高德、百度或其他地图 API。</p>
      <div class="system-grid">
        <div class="system-card"><b>WGS84</b><span>GPS 与国际通用地理坐标</span></div>
        <div class="system-card"><b>GCJ-02</b><span>高德、腾讯等中国大陆互联网地图</span></div>
        <div class="system-card"><b>BD-09</b><span>百度地图在 GCJ-02 基础上的二次偏移</span></div>
      </div>
    </section>
    """,
    unsafe_allow_html=True,
)

with st.expander("为什么同一地点会偏移几百米？", expanded=False):
    st.markdown(
        """
        - **WGS84** 是卫星定位常见输出；**GCJ-02** 是中国大陆互联网地图常用的加偏坐标；**BD-09** 是百度在 GCJ-02 上进一步处理的坐标。
        - 把 WGS84 点直接叠到 GCJ-02 底图，常会出现数百米错位；GCJ-02 与 BD-09 混用也会继续偏移。这是坐标基准不一致，不是地图“画歪了”。
        - 本工具采用公开常用离线公式，并用迭代方式反算 GCJ-02 → WGS84。适合数据清洗和互联网地图制图，不替代测绘级成果。
        """
    )

single_tab, batch_tab = st.tabs(["单点转换", "批量 CSV"])


def _target_options(source: CoordinateSystem) -> list[CoordinateSystem]:
    return [system for system in SYSTEMS if system != source]


def _show_issues(issues) -> None:
    for issue in issues:
        if issue.level == "error":
            st.error(issue.message)
        elif issue.level == "warning":
            st.warning(issue.message)
        else:
            st.info(issue.message)


with single_tab:
    st.subheader("输入一个点，立即换算")
    control_left, control_right = st.columns(2)
    with control_left:
        single_source: CoordinateSystem = st.selectbox(
            "原坐标系",
            SYSTEMS,
            format_func=lambda value: SYSTEM_LABELS[value],
            key="single_source",
        )
    with control_right:
        single_target: CoordinateSystem = st.selectbox(
            "目标坐标系",
            _target_options(single_source),
            format_func=lambda value: SYSTEM_LABELS[value],
            key="single_target",
        )

    if "single_lon" not in st.session_state:
        st.session_state.single_lon = 116.397128
    if "single_lat" not in st.session_state:
        st.session_state.single_lat = 39.908722

    point_left, point_right = st.columns(2)
    with point_left:
        st.number_input("经度（Longitude）", format="%.8f", step=0.000001, key="single_lon")
    with point_right:
        st.number_input("纬度（Latitude）", format="%.8f", step=0.000001, key="single_lat")

    if st.button("转换坐标", type="primary", width="stretch"):
        validation = validate_coordinate(st.session_state.single_lon, st.session_state.single_lat, single_source)
        _show_issues(validation.issues)
        if not validation.has_error and validation.coordinate is not None:
            converted = convert_coordinate(validation.coordinate, single_source, single_target)
            result_left, result_right = st.columns(2)
            result_left.metric(f"{SYSTEM_LABELS[single_target]} 经度", f"{converted.lon:.8f}")
            result_right.metric(f"{SYSTEM_LABELS[single_target]} 纬度", f"{converted.lat:.8f}")
            st.markdown(
                f'<div class="result-box"><b>可复制结果</b><br>{converted.lon:.8f}, {converted.lat:.8f}</div>',
                unsafe_allow_html=True,
            )
            single_frame = pd.DataFrame(
                [
                    {
                        "source_system": single_source,
                        "source_lon": validation.coordinate.lon,
                        "source_lat": validation.coordinate.lat,
                        "target_system": single_target,
                        "target_lon": round(converted.lon, 8),
                        "target_lat": round(converted.lat, 8),
                    }
                ]
            )
            st.download_button(
                "下载这个点（CSV）",
                dataframe_to_excel_csv(single_frame),
                file_name=f"coordinate_{single_source}_to_{single_target}.csv",
                mime="text/csv",
            )
        elif any(issue.code == "LIKELY_SWAPPED" for issue in validation.issues):
            if st.button("交换经纬度后重试"):
                old_lon = st.session_state.single_lon
                st.session_state.single_lon = st.session_state.single_lat
                st.session_state.single_lat = old_lon
                st.rerun()

with batch_tab:
    st.subheader("上传 CSV，批量校验与转换")
    st.markdown(
        '<div class="privacy"><b>隐私说明：</b>上传文件会发送到部署该应用的 Streamlit 服务器内存中处理；本代码不落盘保存，也不转发给第三方地图服务。敏感数据请先脱敏。</div>',
        unsafe_allow_html=True,
    )
    st.write("")
    upload_left, upload_right = st.columns([3, 1])
    with upload_left:
        uploaded = st.file_uploader(
            "上传 CSV 文件",
            type=["csv"],
            max_upload_size=100,
            help="支持 UTF-8/UTF-8 BOM/GB18030，最大 100 MB。",
        )
    with upload_right:
        use_sample = st.checkbox("使用内置示例", value=False)
        st.download_button(
            "下载示例 CSV",
            SAMPLE_BYTES,
            file_name=SAMPLE_DOWNLOAD_NAME,
            mime="text/csv",
            width="stretch",
        )

    csv_bytes: bytes | None = None
    source_name = ""
    if use_sample:
        csv_bytes = SAMPLE_BYTES
        source_name = SAMPLE_DOWNLOAD_NAME
    elif uploaded is not None:
        csv_bytes = uploaded.getvalue()
        source_name = uploaded.name

    if csv_bytes is not None:
        try:
            frame, encoding = read_csv_bytes(csv_bytes)
        except Exception as exc:
            st.error(f"读取失败：{exc}")
        else:
            if frame.empty:
                st.warning("文件只有表头或没有数据行。")
            elif len(frame.columns) < 2:
                st.error("至少需要两列，分别作为经度和纬度。")
            else:
                st.caption(f"已读取 {source_name} · {len(frame):,} 行 · {len(frame.columns)} 列 · 编码 {encoding}")
                setting_left, setting_middle, setting_right = st.columns([1, 1, 2])
                with setting_left:
                    batch_source: CoordinateSystem = st.selectbox(
                        "原坐标系",
                        SYSTEMS,
                        format_func=lambda value: SYSTEM_LABELS[value],
                        key="batch_source",
                    )
                with setting_middle:
                    batch_target: CoordinateSystem = st.selectbox(
                        "目标坐标系",
                        _target_options(batch_source),
                        format_func=lambda value: SYSTEM_LABELS[value],
                        key="batch_target",
                    )

                detected_lon, detected_lat = detect_coordinate_columns(list(frame.columns), batch_source)
                columns = list(frame.columns)
                file_signature = hashlib.sha256(csv_bytes).hexdigest()
                with setting_right:
                    column_left, column_right = st.columns(2)
                    with column_left:
                        lon_column = st.selectbox(
                            "经度列",
                            columns,
                            index=columns.index(detected_lon) if detected_lon in columns else 0,
                        )
                    with column_right:
                        lat_default = columns.index(detected_lat) if detected_lat in columns else min(1, len(columns) - 1)
                        lat_column = st.selectbox("纬度列", columns, index=lat_default)

                if lon_column == lat_column:
                    st.error("经度列和纬度列不能是同一列。")
                elif st.button("开始批量转换", type="primary", width="stretch"):
                    result, summary = process_dataframe(
                        frame,
                        lon_column,
                        lat_column,
                        batch_source,
                        batch_target,
                    )
                    st.session_state.batch_result = result
                    st.session_state.batch_summary = summary
                    st.session_state.batch_download_name = f"converted_{Path(source_name).stem}_{batch_target}.csv"
                    st.session_state.batch_signature = (
                        file_signature,
                        lon_column,
                        lat_column,
                        batch_source,
                        batch_target,
                    )

                current_signature = (
                    file_signature,
                    lon_column,
                    lat_column,
                    batch_source,
                    batch_target,
                )
                if (
                    "batch_result" in st.session_state
                    and "batch_summary" in st.session_state
                    and st.session_state.get("batch_signature") == current_signature
                ):
                    result: pd.DataFrame = st.session_state.batch_result
                    summary: BatchSummary = st.session_state.batch_summary
                    metric_cols = st.columns(4)
                    metric_cols[0].metric("总行数", f"{summary.total:,}")
                    metric_cols[1].metric("成功", f"{summary.success:,}")
                    metric_cols[2].metric("警告", f"{summary.warnings:,}")
                    metric_cols[3].metric("错误", f"{summary.errors:,}")

                    st.dataframe(result.head(30), width="stretch", hide_index=True)
                    st.caption("预览前 30 行；下载文件包含全部数据、转换状态和异常说明。海上点位无法仅凭经纬度判断，需结合行政区或海陆边界另行核验。")
                    st.download_button(
                        "下载全部转换结果",
                        dataframe_to_excel_csv(result),
                        file_name=st.session_state.batch_download_name,
                        mime="text/csv",
                        type="primary",
                        width="stretch",
                    )

st.markdown(
    """
    <div class="footer">
      算法说明：采用公开常用的 WGS84 / GCJ-02 / BD-09 离线换算公式；中国大陆范围外不对 WGS84 与 GCJ-02 加偏。<br>
      部署说明：应用无需密钥和外部 API，可直接部署到 Streamlit Community Cloud。
    </div>
    """,
    unsafe_allow_html=True,
)
