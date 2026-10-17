from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.v1.llm import require_admin
from app.retrieval.errors import StorageError
from app.schemas.runs import RunList, RunOut
from app.services import run_service

router = APIRouter(prefix="/runs", tags=["runs"], dependencies=[Depends(require_admin)])


@router.get("", response_model=RunList)
def list_runs(limit: int = Query(20, ge=1, le=100)) -> RunList:
    try:
        runs = run_service.list_runs(limit)
    except StorageError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.public_message) from exc
    return RunList(runs=runs, count=len(runs))


@router.get("/{run_id}", response_model=RunOut)
def get_run(run_id: str) -> RunOut:
    try:
        run = run_service.get_run(run_id)
    except StorageError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.public_message) from exc
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return RunOut(**run)
