# AI 智能旅行规划系统：API 接口契约

| 文档属性 | 内容 |
| --- | --- |
| 文档编号 | ATPS-API-001 |
| 文档版本 | 0.1.1 |
| 编写日期 | 2026-10-11 |
| 最近修订 | 2026-10-15 |
| 对应阶段 | 第二阶段：FastAPI 接口与 Pydantic 数据模型 |
| 文档状态 | 已完成离线回归与契约核对；Swagger 人工核对记录待补充 |
| 本地开发地址 | http://127.0.0.1:8000 |
| 业务接口前缀 | /api/v1 |

## 1. 文档范围

本文定义健康检查接口和旅行需求预览接口的请求、响应、
校验规则及验收方法。本文件尚未完整描述草案生成、地点和天气接口，
这些接口的当前参数以应用生成的 OpenAPI 文档为准。

旅行需求预览接口负责校验用户输入，并返回需求摘要。

当前预览结果中的城市名称来自用户输入，预算来自用户提出的预算。
景点、地址、坐标、路线、天气和实际费用等数据，由后续功能接入。

本文中的示例响应表示预期结构。实际运行结果需要在文档末尾登记。

## 2. 通用约定

### 2.1 请求格式

旅行预览接口使用 JSON 请求体。

请求头：

```http
Content-Type: application/json
```

调用方应使用下列约定：

- 日期使用 `YYYY-MM-DD` 字符串，例如 `2026-11-01`。
- 人数、房间数和金额使用 JSON 整数。
- 金额单位为人民币分。
- 不传入模型未定义的字段。

当前日期字段由 Pydantic 的默认日期解析规则处理。
客户端统一使用上述日期字符串格式；
当前后端尚未额外实现仅允许该字符串格式的校验器。

### 2.2 预算口径

`budget_cents` 表示：

> 全体出行人员、整次旅行的总预算，单位为人民币分。

例如：

- `600000` 表示人民币 6000 元。
- 两个人出行时，`600000` 仍表示两个人合计的总预算。
- 该字段是用户提出的预算，不代表系统计算出的旅行费用。

### 2.3 响应元信息

旅行预览的成功响应和请求校验错误响应均包含 `meta`：

| 字段 | JSON 类型 | 含义 |
| --- | --- | --- |
| request_id | string | 后端生成的 UUID 字符串 |
| warnings | array[string] | 响应提示列表，当前预览接口返回空列表 |

示例中的 `request_id` 仅说明格式。
核对实际响应时检查其格式，不要求与示例值一致。

## 3. 接口列表

| HTTP 方法 | 路径 | 功能 | 主要响应状态 |
| --- | --- | --- | --- |
| GET | /health | 检查后端服务是否运行 | 200 |
| POST | /api/v1/trips/preview | 校验并预览旅行需求 | 200、422 |

开发辅助地址：

- Swagger UI：`/docs`
- OpenAPI 描述：`/openapi.json`

## 4. 健康检查

### 4.1 请求

```http
GET /health
```

请求体：无。

### 4.2 成功响应

HTTP 状态码：`200`

```json
{
  "status": "ok",
  "service": "ai-travel-planner"
}
```

该接口表示应用能够处理健康检查请求。

模型服务、地图服务、数据库等后续能力需要分别验证。

## 5. 旅行需求预览

### 5.1 请求

```http
POST /api/v1/trips/preview
Content-Type: application/json
```

### 5.2 请求字段

“必填”表示调用方必须提供该字段。
非必填字段在省略时采用默认值。

| 字段 | JSON 类型 | 必填 | 默认值 | 约束或含义 |
| --- | --- | --- | --- | --- |
| destination | string | 是 | 无 | 去除首尾空白后，长度为 1～50 个字符 |
| start_date | string | 是 | 无 | 开始日期，调用方使用 YYYY-MM-DD |
| end_date | string | 是 | 无 | 结束日期，调用方使用 YYYY-MM-DD |
| travelers | integer | 是 | 无 | 1～20 人，严格整数 |
| budget_cents | integer | 是 | 无 | 大于 0，全体人员整次旅行的总预算，单位为分 |
| transportation | string | 否 | public_transit | 市内交通偏好，取值见枚举表 |
| accommodation_preference | string | 否 | economy | 住宿偏好，取值见枚举表 |
| room_count | integer | 否 | 1 | 1～20 间，严格整数，并满足跨字段规则 |
| preferences | array[string] | 否 | [] | 兴趣偏好，最多 10 项；当前未额外限制每项文本长度或禁止空字符串 |
| pace | string | 否 | relaxed | 游玩节奏，取值见枚举表 |

严格整数字段包括：

- `travelers`
- `budget_cents`
- `room_count`

例如，`true`、`"2"`、`2.0` 均不能代替这些字段要求的整数。

非必填字段表示可以省略，不表示可以统一传入 `null`。

### 5.3 枚举取值

| 字段 | 允许取值 | 含义 |
| --- | --- | --- |
| transportation | public_transit、driving、walking | 公共交通、自驾、步行 |
| accommodation_preference | economy、comfort、luxury | 经济型、舒适型、高档型 |
| pace | relaxed、balanced、intensive | 轻松、均衡、紧凑 |

### 5.4 跨字段规则

1. 结束日期不得早于开始日期。
2. 旅行天数包含开始日和结束日。
3. 当前支持 1～7 天的旅行需求。
4. 房间数不得超过出行人数。

旅行天数由后端计算：

```text
旅行天数 = 结束日期与开始日期的间隔天数 + 1
```

例如：

- 2026-11-01 至 2026-11-01：1 天。
- 2026-11-01 至 2026-11-03：3 天。
- 2026-11-01 至 2026-11-07：7 天。

调用方不应提交额外的 `days` 或 `day_count` 请求字段。

当前日期规则也允许过去日期，只要日期顺序和旅行天数满足约束。

房间数规则是当前产品输入规则。
酒店实际可入住人数和房型要求，需要在接入外部数据后另行处理。

### 5.5 正常请求示例

```json
{
  "destination": " 北京 ",
  "start_date": "2026-11-01",
  "end_date": "2026-11-03",
  "travelers": 2,
  "budget_cents": 600000,
  "transportation": "public_transit",
  "accommodation_preference": "economy",
  "room_count": 1,
  "preferences": ["历史文化", "美食"],
  "pace": "relaxed"
}
```

### 5.6 成功响应示例

HTTP 状态码：`200`

```json
{
  "data": {
    "destination": "北京",
    "start_date": "2026-11-01",
    "end_date": "2026-11-03",
    "day_count": 3,
    "travelers": 2,
    "room_count": 1,
    "requested_budget_cents": 600000,
    "currency": "CNY"
  },
  "meta": {
    "request_id": "e54c5234-0b78-4692-9fda-b28a508260d5",
    "warnings": []
  }
}
```

当前预览响应回传下表中的需求摘要字段：

| 字段 | JSON 类型 | 含义 |
| --- | --- | --- |
| data.destination | string | 去除首尾空白后的用户输入城市名称 |
| data.start_date | string | 开始日期 |
| data.end_date | string | 结束日期 |
| data.day_count | integer | 后端计算的旅行天数 |
| data.travelers | integer | 出行人数 |
| data.room_count | integer | 希望预订的房间数 |
| data.requested_budget_cents | integer | 用户提出的总预算，单位为分 |
| data.currency | string | 当前固定为 CNY |

请求字段使用 `budget_cents`。
响应字段使用 `requested_budget_cents`，强调它是用户提出的预算。

## 6. 请求校验错误

### 6.1 响应结构

请求体 JSON 语法错误、字段校验失败或跨字段规则失败时，
返回统一的请求校验错误。

HTTP 状态码：`422`

日期倒置示例：

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "请求参数校验失败",
    "details": [
      {
        "field": "end_date",
        "reason": "date_order_invalid"
      }
    ]
  },
  "meta": {
    "request_id": "e54c5234-0b78-4692-9fda-b28a508260d5",
    "warnings": []
  }
}
```

| 字段 | 含义 |
| --- | --- |
| error.code | 错误大类，当前请求校验错误为 VALIDATION_ERROR |
| error.message | 总体错误说明 |
| error.details | 一个或多个具体输入错误 |
| error.details[].field | 错误字段或位置 |
| error.details[].reason | 供程序识别的原因标识 |

多个字段同时不合法时，`details` 可以包含多项。
调用方应按字段处理错误，不依赖列表中的固定排列顺序。

### 6.2 当前错误原因

| reason | 含义或示例 |
| --- | --- |
| required | 缺少必填字段 |
| unexpected_field | 请求中存在未定义字段，例如 days |
| integer_required | 严格整数字段收到布尔值、字符串或浮点数 |
| value_too_small | 数值未满足下限，例如人数为 0、预算为 0 |
| value_too_large | 数值超过上限，例如人数为 21 |
| text_too_short | 文本未满足最小长度，例如城市名称为空 |
| text_too_long | 文本超过最大长度 |
| invalid_choice | 枚举取值不合法，例如 transportation 为 teleport |
| invalid_json | 请求体不是合法 JSON，field 为 body |
| date_order_invalid | 结束日期早于开始日期，field 为 end_date |
| trip_too_long | 旅行超过 7 天，field 为 end_date |
| room_count_exceeds_travelers | 房间数超过人数，field 为 room_count |
| invalid_value | 当前尚未单独映射的其他校验错误 |

当前错误响应仅包含明确选择的字段和原因，
不会直接返回校验器的原始输入值或内部异常上下文。

### 6.3 其他 HTTP 错误

当前统一处理的是请求校验错误。

不存在的路径通常返回 `404`：

```json
{
  "detail": "Not Found"
}
```

已存在路径使用不支持的 HTTP 方法，通常返回 `405`：

```json
{
  "detail": "Method Not Allowed"
}
```

当前这两类响应使用框架默认结构。

后端输出不符合响应模型等服务端代码问题，
不应归类为用户输入校验失败。

## 7. 实现调用关系

正常请求：

```text
HTTP 请求
→ TripRequest 字段与跨字段校验
→ preview_trip()
→ TripService.preview()
→ TripPreviewResponse
→ 200：data + meta
```

输入校验失败：

```text
HTTP 请求
→ JSON 解析或 TripRequest 校验失败
→ RequestValidationError
→ request_validation_error_handler()
→ ErrorResponse
→ 422：error + meta
```

输入校验失败时，`TripService.preview()` 不执行。

依赖提供函数可能在框架处理请求期间执行，
因此后续也应避免在依赖提供函数中发起不必要的外部调用。

## 8. 阶段验收标准

### 8.1 自动化测试基线

旅行预览接口测试共 12 个用例：

| 类别 | 数量 | 检查内容 |
| --- | --- | --- |
| 正常请求 | 3 | 三天、同一天、七天；响应正确，preview 调用一次 |
| 单项输入异常 | 7 | 人数、预算、日期、房间数和未知字段；返回统一错误 |
| 多字段异常 | 1 | 返回全部字段错误 |
| JSON 语法异常 | 1 | 返回 body / invalid_json |

所有异常用例均检查 `preview()` 调用次数为 0。

在后端目录执行：

```powershell
conda run --no-capture-output -n ai-travel python -m pytest tests/integration/test_trip_preview.py -q
```

预期结果：

```text
12 passed
```

预期结果不代替实际执行记录。

### 8.2 文档与接口核对

- OpenAPI 中预览接口的 200 响应对应 `TripPreviewResponse` 类型别名，即 `ApiResponse[TripPreview]`；内部组件名称由框架生成，不作为稳定契约。
- OpenAPI 中预览接口的 422 响应引用 ErrorResponse。
- OpenAPI 中 TripRequest 的必填字段与本文一致。
- 本文正常请求示例返回 200，day_count 为 3。
- 将示例 end_date 改为 2026-10-31 后，返回统一的 422 错误。
- 实际响应中的 request_id 是有效 UUID 字符串。

### 8.3 实际验收记录

填写本人已经执行的结果。
如果上一小步已经完成自动化测试，可以登记那次结果。

| 验收项 | 实际结果 | 执行日期 |
| --- | --- | --- |
| 12 个自动化测试 | 待记录 | 待记录 |
| OpenAPI 响应模型和必填字段核对 | 待记录 | 待记录 |
| 正常请求示例 | 待记录 | 待记录 |
| 日期倒置请求示例 | 待记录 | 待记录 |

核对完成后，将文档状态更新为“已完成本地核对”。

### 8.4 模型重构离线验收记录

执行日期：2026-10-15。

| 验收项 | 实际结果 |
| --- | --- |
| 迁移前、迁移后复用现有离线用例 | 两次均为 270 passed |
| 4 个领域模块及 FastAPI OpenAPI 生成 | 通过，无循环导入 |
| 30 个保留业务类的 JSON Schema 与 model_config | 与迁移前一致 |
| 7 个已注册接口的展开契约 | 与迁移前一致；比较时忽略文档标题和描述 |
| 提示词中的 TripDraft Schema 文本 | 与迁移前一致 |
| 业务类代码正文 | 原样迁移，验证器与默认值保留 |
| 旧模型模块导入 | 已清理 |
| 新增测试文件或验证脚本 | 无；已有文件仅同步模型导入 |

离线用例使用模拟的上游结果，不调用真实大模型或高德服务。
本表不替代 8.3 中需要本人在 Swagger 核对并登记的记录。
测试依赖另有一条既有的 AnyIO 别名弃用提醒，不影响此次用例通过。

## 9. 后续维护规则

### 9.1 接口维护

接口变更时，同步检查：

1. 请求模型和响应模型。
2. 路由中的 OpenAPI 响应声明。
3. API 集成测试。
4. 本文中的字段、示例和错误原因。

新增 LLM、地图或历史接口时，
在实际实现并完成验证后，再补充对应接口契约。

### 9.2 模型归属与兼容性约定

业务模型统一从以下模块导入：

| 模块 | 内容 |
| --- | --- |
| `app.models.common` | `ResponseMeta`、`ApiResponse[T]`、错误模型、公共日期规则和 UTC 时间函数 |
| `app.models.location` | 行政区解析、地点搜索与 POI 记录 |
| `app.models.weather` | 实况、预报、日期覆盖和每日天气建议 |
| `app.models.trip` | 旅行请求、预览、草案与已有规划模型 |

`__init__.py` 只保留包说明，不集中导入各领域模型。
依赖方向为 `trip -> weather -> location -> common`，上层也可以直接引用公共和地点模块。

7 个成功响应名称改为领域模块中的类型别名，共用 `ApiResponse[T]`。
`data` 与 `meta` 仍为必填字段，业务 JSON 不增加或删除字段；
`ErrorResponse` 继续使用 `error + meta`，保留自动生成元信息的默认行为。
业务模型各自原有的严格校验配置保持不变。

`MAX_TRIP_DAYS`、`calculate_day_count()` 和 `utc_now()` 位于公共模块，
避免天气日期区间反向依赖旅行模型。

原 `train_plan.py` 的 4 个规划模型名称已迁入 `trip.py`，
其中 `TripPlanResponse` 使用通用响应别名。
已有规划整合模型不表示本轮新增了相应 API；以实际注册路由为准。

后续新增功能遵循以下规则：

1. 优先向现有领域模块增加必要的业务类型。
2. 新的成功响应复用 `ApiResponse[T]`，不单独建立响应文件。
3. 不从已删除的旧模块导入，也不增加长期转发模块。
4. RAG 确实需要独立类型时增加一个领域模块；数据库阶段再增加 `db_models.py`。

## 10. 修订记录

| 版本 | 日期 | 内容 |
| --- | --- | --- |
| 0.1.0 | 2026-10-11 | 建立健康检查和旅行预览接口契约，记录统一校验错误和阶段验收方法 |
| 0.1.1 | 2026-10-15 | 记录四个领域模块、通用响应与旧导入迁移，补充离线回归和兼容性核对结果 |
