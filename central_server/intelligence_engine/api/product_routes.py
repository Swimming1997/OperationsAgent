from fastapi import APIRouter

from intelligence_engine.api.product_account_monitor_routes import router as account_monitor_router
from intelligence_engine.api.product_account_routes import router as account_router
from intelligence_engine.api.product_benchmark_routes import router as benchmark_router
from intelligence_engine.api.product_intelligence_routes import router as intelligence_router
from intelligence_engine.api.product_keyword_rule_routes import router as keyword_rule_router
from intelligence_engine.api.product_me_routes import router as me_router
from intelligence_engine.api.product_option_routes import router as option_router
from intelligence_engine.api.product_organization_routes import router as organization_router
from intelligence_engine.api.product_reference_library_routes import router as reference_library_router
from intelligence_engine.api.product_rule_xhs_routes import router as rule_xhs_router
from intelligence_engine.api.product_task_routes import router as task_router

router = APIRouter()

for subrouter in (
    organization_router,
    me_router,
    account_router,
    account_monitor_router,
    benchmark_router,
    task_router,
    keyword_rule_router,
    option_router,
    intelligence_router,
    reference_library_router,
    rule_xhs_router,
):
    router.include_router(subrouter)
