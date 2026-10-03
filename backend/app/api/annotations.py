import uuid

from fastapi import APIRouter, HTTPException, Request, Response

from app.annotations import new_annotation, to_collection, to_feature, validate_geometry
from app.models import Annotation

router = APIRouter()


@router.get("/annotations")
def list_annotations(request: Request) -> dict:
    session = request.app.state.session_factory()
    try:
        rows = session.query(Annotation).order_by(Annotation.created_at).all()
        return to_collection(rows)
    finally:
        session.close()


@router.post("/annotations", status_code=201)
def create_annotation(body: dict, request: Request) -> dict:
    try:
        validate_geometry(body.get("geometry"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    row = new_annotation(uuid.uuid4().hex, body["geometry"], body.get("properties"))
    session = request.app.state.session_factory()
    try:
        session.add(row)
        session.commit()
        session.refresh(row)
        return to_feature(row)
    finally:
        session.close()


@router.delete("/annotations/{annotation_id}", status_code=204)
def delete_annotation(annotation_id: str, request: Request) -> Response:
    session = request.app.state.session_factory()
    try:
        row = session.get(Annotation, annotation_id)
        if row is None:
            raise HTTPException(status_code=404, detail="未知标注")
        session.delete(row)
        session.commit()
        return Response(status_code=204)
    finally:
        session.close()
