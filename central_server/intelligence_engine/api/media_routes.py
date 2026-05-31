from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from intelligence_engine.db.models import ContentIdentity, ContentSnapshot
from intelligence_engine.db.session import get_db
from intelligence_engine.services.media_service import MediaService

router = APIRouter(prefix="/api/media", tags=["media"])


@router.get("/cover/{content_id}")
def get_cover_image(
    content_id: str,
    e: int = Query(..., description="expiry unix timestamp"),
    s: str = Query(..., description="HMAC signature"),
    db: Session = Depends(get_db),
):
    media = MediaService()
    if not media.verify_cover_token(content_id, e, s):
        raise HTTPException(status_code=403, detail="invalid or expired media signature")

    content = db.get(ContentIdentity, content_id)
    if not content or not content.latest_snapshot_id:
        raise HTTPException(status_code=404, detail="content or snapshot not found")

    snapshot = db.get(ContentSnapshot, content.latest_snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="snapshot not found")

    local_path = media.resolve_local_cover_path(snapshot.stored_cover_path)
    if local_path:
        return FileResponse(
            local_path,
            media_type=media.guess_media_type(local_path),
            headers={"Cache-Control": "public, max-age=3600"},
        )

    metadata = content.metadata_json if isinstance(content.metadata_json, dict) else {}
    for cover_url in media.iter_cover_candidate_urls(snapshot, metadata):
        if not media.is_allowed_media_url(cover_url):
            continue
        remote = media.fetch_remote_cover(cover_url)
        if not remote:
            continue
        data, content_type = remote
        return Response(
            content=data,
            media_type=content_type,
            headers={"Cache-Control": "public, max-age=3600"},
        )

    raise HTTPException(status_code=404, detail="cover fetch failed")
