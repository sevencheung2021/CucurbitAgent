import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from app.config import settings
from app.services.genome_catalog import GENOME_DIR_MAP
from app.services.rate_limit import enforce_download_rate_limit

router = APIRouter(prefix="/api/genomes", tags=["genomes"])


def _safe_under_root(root: Path, *parts: str) -> Path:
    """Resolve ``root / parts`` and reject path traversal outside ``root``."""
    root_resolved = root.resolve()
    target = root_resolved.joinpath(*parts).resolve()
    try:
        target.relative_to(root_resolved)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid path") from exc
    return target


@router.get("/catalog")
def get_catalog():
    return {"catalog": GENOME_DIR_MAP}


@router.get("/files")
def list_files(path_suffix: str = Query(...)):
    target = _safe_under_root(settings.genome_data_module, path_suffix)
    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail="Directory not found")
    files = sorted(
        [
            {"name": f, "size_bytes": os.path.getsize(target / f)}
            for f in os.listdir(target)
            if os.path.isfile(target / f)
        ],
        key=lambda x: x["name"],
    )
    return {"path_suffix": path_suffix, "files": files}


@router.get("/download")
def download_file(
    path_suffix: str = Query(...),
    filename: str = Query(...),
    request: Request = None,
):
    if request is not None:
        enforce_download_rate_limit(request)
    if Path(filename).name != filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    target = _safe_under_root(settings.genome_data_module, path_suffix, filename)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=str(target), filename=filename, media_type="application/octet-stream")
