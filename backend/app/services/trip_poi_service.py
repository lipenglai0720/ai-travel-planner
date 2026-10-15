"""为已有旅行规划按活动查询真实地点候选。"""

from app.clients.amap import AmapError
from app.models.location import (
    DistrictQuery,
    DistrictResult,
    PoiSearchQuery,
    PoiSearchResult,
)
from app.models.trip import (
    ActivityPoiCandidates,
    PoiCandidateStatus,
    PoiKeywordSource,
    TripPlanRequest,
    TripPoiPlan,
    TripPoiPlanRequest,
)
from app.services.poi_service import PoiService
from app.services.trip_planning_service import TripPlanningService


# 规则只生成搜索关键词，不代表已经确定了活动地点。
KEYWORD_RULES = (
    (("美术", "艺术", "画展"), "美术馆"),
    (("博物", "历史", "文化", "文物", "展览"), "博物馆"),
    (("公园", "自然", "绿地", "植物"), "公园"),
    (("美食", "小吃", "餐饮", "午餐", "晚餐", "早餐"), "餐厅"),
    (("古镇", "古街", "老街", "街区", "步行"), "步行街"),
)


def _build_keyword(title: str) -> tuple[str, PoiKeywordSource]:
    """优先匹配类别规则；未匹配时使用已校验的活动标题。"""

    for hints, keyword in KEYWORD_RULES:
        if any(hint in title for hint in hints):
            return keyword, "project_rules"

    return title, "activity_title"


class TripPoiService:
    """组合旅行规划与 POI 搜索，并限制单次请求的查询量。"""

    def __init__(
        self,
        planning_service: TripPlanningService,
        poi_service: PoiService,
    ) -> None:
        self._planning_service = planning_service
        self._poi_service = poi_service

    def create_plan(self, request: TripPoiPlanRequest) -> TripPoiPlan:
        """生成规划，再查询地点候选。

        模型生成错误继续由已有处理器处理。
        已识别的高德失败保留原规划，并写入对应候选状态。
        """

        base_request = TripPlanRequest.model_validate(
            request.model_dump(include=set(TripPlanRequest.model_fields)),
        )
        plan = self._planning_service.create_plan(base_request)

        # POI 搜索独立解析行政区，使关闭天气时也能限定搜索地区。
        region: DistrictResult | None = None
        region_error_code: str | None = None

        try:
            region = self._poi_service.resolve_district(
                DistrictQuery(
                    keyword=request.destination,
                    province_adcode=request.province_adcode,
                ),
            )
        except AmapError as exc:
            region_error_code = exc.code

        # 字典仅在本次规划内复用结果，不跨请求保存。
        # 行政区在本次规划中固定，因此使用关键词作为键。
        results_by_keyword: dict[str, PoiSearchResult] = {}
        query_count = 0
        stop_new_queries = False
        activity_pois: list[ActivityPoiCandidates] = []

        for day in plan.days:
            for activity in day.activities:
                keyword, keyword_source = _build_keyword(activity.title)
                result: PoiSearchResult | None = None
                reason_code: str | None = None
                status: PoiCandidateStatus

                if region is None:
                    status = "failed"
                    reason_code = region_error_code

                elif keyword in results_by_keyword:
                    # 成功的空结果也复用，避免反复查询同一个关键词。
                    result = results_by_keyword[keyword]
                    status = "found" if result.pois else "empty"

                elif stop_new_queries:
                    status = "skipped"
                    reason_code = "poi_service_unavailable"

                elif query_count >= request.max_poi_queries:
                    status = "skipped"
                    reason_code = "query_limit_reached"

                else:
                    query_count += 1

                    try:
                        raw_result = self._poi_service.search(
                            PoiSearchQuery(
                                city=region.region.adcode,
                                keyword=keyword,
                            ),
                        )
                    except AmapError as exc:
                        status = "failed"
                        reason_code = exc.code

                        # 遇到一次已识别失败后停止新关键词查询，
                        # 避免网络故障时连续等待；已有结果仍可复用。
                        stop_new_queries = True

                    else:
                        # 按 POI ID 去重，保留供应商返回的顺序。
                        # 截取候选数量，不宣称首条就是最佳或最终地点。
                        unique_pois = {}
                        for poi in raw_result.pois:
                            unique_pois.setdefault(poi.poi_id, poi)

                        result = PoiSearchResult(
                            city=raw_result.city,
                            keyword=raw_result.keyword,
                            source=raw_result.source,
                            coordinate_system=raw_result.coordinate_system,
                            queried_at=raw_result.queried_at,
                            pois=list(unique_pois.values())[:request.poi_limit],
                        )
                        results_by_keyword[keyword] = result
                        status = "found" if result.pois else "empty"

                activity_pois.append(
                    ActivityPoiCandidates(
                        travel_date=day.date,
                        period=activity.period,
                        keyword=keyword,
                        keyword_source=keyword_source,
                        status=status,
                        search_result=result,
                        reason_code=reason_code,
                    ),
                )

        # model_dump() 默认保留 Python 日期对象。
        # 使用正常构造路径，执行原规划和新关联规则的全部校验。
        return TripPoiPlan(
            **plan.model_dump(),
            poi_region=region,
            poi_query_count=query_count,
            activity_pois=activity_pois,
        )