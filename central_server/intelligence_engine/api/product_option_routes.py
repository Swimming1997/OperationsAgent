from intelligence_engine.api.product_common import *


router = APIRouter(prefix="/api")


@router.get("/product/options", response_model=ProductOptions)
def get_product_options():
    return _product_options()


@router.get("/product/options/roles")
def get_role_options():
    return _product_options().roles


@router.get("/product/options/platforms")
def get_platform_options():
    return _product_options().platforms


@router.get("/product/options/feed-types")
def get_feed_type_options():
    return _product_options().feed_types


@router.get("/product/options/task-template-types")
def get_task_template_type_options():
    return _product_options().task_template_types


@router.get("/product/options/workflow-statuses")
def get_workflow_status_options():
    return _product_options().workflow_statuses


@router.get("/product/options/candidate-buckets")
def get_candidate_bucket_options():
    return _product_options().candidate_buckets


def _split_enum_filter(raw: str | None, enum_cls) -> list[str] | None:
    if not raw:
        return None
    allowed = {item.value for item in enum_cls}
    values = [item.strip() for item in raw.split(",") if item.strip()]
    invalid = [item for item in values if item not in allowed]
    if invalid:
        raise HTTPException(status_code=422, detail=f"Invalid filter value: {', '.join(invalid)}")
    return values or None


@router.get("/product/options/account-statuses")
def get_account_status_options():
    return _product_options().account_statuses


@router.get("/product/options/agent-statuses")
def get_agent_status_options():
    return _product_options().agent_statuses
