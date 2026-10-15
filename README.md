# AI 智能旅行规划系统

这是一个使用 Python 和 FastAPI 逐步开发的智能旅行规划项目。

## 当前能力

| HTTP 方法 | 路径 | 功能 |
| --- | --- | --- |
| GET | /health | 检查后端服务是否运行 |
| POST | /api/v1/trips/preview | 校验旅行需求并计算需求摘要 |
| POST | /api/v1/trips/generate | 调用大模型，生成并校验结构化旅行草案 |
| GET | /api/v1/pois/search | 查询高德地点记录与真实坐标 |
| GET | /api/v1/weather/current | 解析地区并查询实况天气 |
| GET | /api/v1/weather/forecast | 查询短期预报，检查可选目标日期的覆盖状态 |
| GET | /api/v1/weather/forecast-range | 检查旅行日期区间的预报覆盖，生成每日天气与规则建议 |

AI 草案中的活动建议与地图查询得到的可信地点记录分别管理。
天气日期没有预报时保留缺失状态，不用模型生成的内容填充供应商数据。

## 开发环境

- Windows 11
- Python 3.11
- Miniconda，环境名称为 ai-travel
- PyCharm

本次模型整理沿用当前 Python 和依赖版本，不需要升级或重新安装依赖。
涉及云端模型和高德的接口需要按 `backend/.env.example` 配置相应环境变量；
真实密钥放在本地 `backend/.env`，不要提交。

## 安装依赖

先准备好 ai-travel Conda 环境，然后在项目根目录执行：

```powershell
conda run --no-capture-output -n ai-travel python -m pip install -r .\backend\requirements.txt
```

## 启动后端

在项目根目录执行：

```powershell
Set-Location .\backend

conda run --no-capture-output -n ai-travel python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

API 文档地址：<http://127.0.0.1:8000/docs>。
接口路径、请求参数和响应业务字段以实际生成的 OpenAPI 文档为准。

## 模型组织与导入规则

```text
backend/app/models/
├── __init__.py   # 包说明，不集中导出全部模型
├── common.py     # 通用响应、错误、UTC 时间和公共日期规则
├── location.py   # 行政区、POI 查询和地点记录
├── weather.py    # 实况、预报、日期覆盖和每日天气建议
└── trip.py       # 旅行需求、预览、AI 草案和规划结果
```

当前共有 4 个业务模型文件、31 个手写类定义。
这里统计源码中的 `class`，不统计 Pydantic 在运行时生成的泛型具体类型。

业务模型按领域集中；一个文件可以管理多个具有独立业务含义的模型。
保留这些模型各自的字段、默认值、严格校验配置和验证器，
不使用一个统一配置的父类覆盖所有模型的输入转换策略。

直接从所属模块导入，例如：

```python
from app.models.common import ErrorResponse, ResponseMeta
from app.models.location import PoiSearchQuery
from app.models.trip import TripGenerationResponse, TripRequest
from app.models.weather import ForecastRangeQuery
```

模型依赖方向：

```text
trip -> weather -> location -> common
```

上层可以直接引用 `common` 和 `location`。
`MAX_TRIP_DAYS`、`calculate_day_count()` 和 `utc_now()` 放在 `common.py`，
使天气模型无需反向导入旅行模型。

## 统一响应

旅行、地点和天气业务接口使用 `ApiResponse[T]`：
`T` 指定 `data` 的业务模型，`data` 与 `meta` 都是必填字段。

现有响应名称作为类型别名保留，便于服务和路由继续使用：

| 所属模块 | 业务响应名称 | 通用响应类型 |
| --- | --- | --- |
| trip | TripPreviewResponse | ApiResponse[TripPreview] |
| trip | TripGenerationResponse | ApiResponse[TripDraft] |
| trip | TripPlanResponse | ApiResponse[TripPlan] |
| location | PoiSearchResponse | ApiResponse[PoiSearchResult] |
| weather | WeatherCurrentResponse | ApiResponse[CurrentWeather] |
| weather | WeatherForecastResponse | ApiResponse[ForecastLookupResult] |
| weather | WeatherForecastRangeResponse | ApiResponse[TripWeatherResult] |

类型别名复用同一个成功响应定义，不重复编写 `data` 和 `meta`。
Swagger 中的响应组件名称可能包含泛型类型，不作为接口稳定性约定。

错误响应继续使用 `ErrorResponse` 的 `error + meta` 结构；
省略错误响应的 `meta` 时仍自动创建 `ResponseMeta`。
健康检查继续使用原有的 `status + service` 结构。

## 后续开发衔接

- 旅行规划继续使用 `app.models.trip` 中的需求、草案和规划模型。
- 原 `train_plan.py` 中的 `TripPlanRequest`、`PlannedDay`、`TripPlan` 和 `TripPlanResponse` 已迁入旅行模块。本轮只迁移已有模型，尚未注册规划整合接口。
- 新增业务成功响应继续使用 `ApiResponse[T]`，不再单独增加响应文件。
- RAG 功能需要独立数据类型时，集中增加一个领域模块。
- 到数据库阶段再增加 `db_models.py` 管理数据库实体；接口模型与数据库实体分别管理。
- 旧模型模块已删除。新增代码和旧脚本都应使用上面的领域模块路径。

## 验证与契约

使用 Swagger UI 的“Try it out”核对接口：
<http://127.0.0.1:8000/docs>。

健康检查和旅行预览的请求示例、错误标识及人工核对方法见
[API 接口契约](docs/API_CONTRACT.md)。

2026-10-15 模型整理前后，复用现有离线测试均得到 `270 passed`。
30 个保留业务类的 JSON Schema 和校验配置、7 个已注册接口的展开契约，
以及嵌入提示词的 `TripDraft` Schema 均保持一致。
这些检查不代表已经调用真实云端模型或高德服务。
