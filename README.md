# 坐标系转换工具（Streamlit）

一个可直接部署到 Streamlit Community Cloud 的中文坐标转换工具，支持：

- WGS84 ⇄ GCJ-02 ⇄ BD-09 单点互转
- CSV 批量上传、自动识别经纬度列和结果下载
- 经纬度写反、越界、空值、非数字、`0,0` 与中国大陆范围外点位提示
- 完全离线换算，不调用高德、百度或其他第三方地图 API
- UTF-8 BOM 结果文件，便于 Excel 直接打开中文

## 项目结构

```text
streamlit-coordinate-converter/
├─ streamlit_app.py           # Streamlit 入口
├─ coordinate_transform.py    # 转换算法与校验
├─ csv_helpers.py             # CSV 读写与批量处理
├─ requirements.txt
├─ .streamlit/config.toml
├─ sample_data/coordinate_sample.csv
├─ tests/
└─ .github/workflows/test.yml
```

## 本地运行

建议使用 Python 3.12。

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
streamlit run streamlit_app.py
```

浏览器会打开 `http://localhost:8501`。

## 上传 GitHub

1. 在 GitHub 新建一个空仓库，例如 `coordinate-converter-streamlit`。
2. 在本项目目录执行：

```bash
git init
git add .
git commit -m "Add Streamlit coordinate converter"
git branch -M main
git remote add origin https://github.com/你的用户名/coordinate-converter-streamlit.git
git push -u origin main
```

也可以在 GitHub 网页端选择 **Add file → Upload files**，把本目录内的所有文件上传；注意同时上传 `.streamlit` 和 `.github` 这两个隐藏目录。

## 部署到 Streamlit Community Cloud

1. 登录 [Streamlit Community Cloud](https://share.streamlit.io/)，连接 GitHub 账号。
2. 选择 **Create app**，指定刚才的仓库、`main` 分支。
3. 入口文件填写 `streamlit_app.py`。
4. 在高级设置中选择 Python 3.12，无需填写 Secrets。
5. 点击部署。以后推送到 GitHub，应用会自动重新部署。

官方参考：

- [应用文件组织](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/file-organization)
- [依赖管理](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies)
- [连接 GitHub](https://docs.streamlit.io/deploy/streamlit-community-cloud/get-started/connect-your-github-account)
- [部署应用](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)

## CSV 格式

至少包含一列经度和一列纬度。工具会优先识别 `lon_wgs84 / lat_wgs84`、`lng / lat`、`经度 / 纬度` 等常见列名，也允许手动选择。

```csv
name,lon_wgs84,lat_wgs84
天安门,116.397128,39.908722
上海外滩,121.490317,31.236305
```

输出会追加目标经纬度、`转换状态` 和 `异常说明`。错误行不会换算，但会原样保留，便于回查。

示例数据同时保存在英文文件名中并内置于代码。即使部署时漏传 `sample_data` 目录，应用仍可正常启动和下载示例，不会因示例文件缺失而中断。

## 隐私与精度说明

- 在 Community Cloud 上，上传文件会进入 Streamlit 应用服务器内存；本代码不主动落盘，也不转发给第三方 API。涉及个人或敏感位置的数据应先脱敏。
- 本工具采用公开常用的离线换算公式，适合互联网地图制图与常规数据清洗，不替代测绘级或法定坐标转换成果。
- “中国大陆范围外”判断是常用粗略外包范围；仅凭经纬度无法可靠识别海上点位或行政区归属。
