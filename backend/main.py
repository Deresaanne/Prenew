"""
Minimal FastAPI backend for the CSV / insights / upload demo site.

Endpoints:
    GET  /csv                -> returns the contents of data/influencers.csv as JSON
    GET  /csv/download       -> returns the raw CSV file for download
    POST /upload             -> accepts a .txt file and saves it to uploads/
    GET  /insights           -> returns the latest insights .txt as JSON (name + text)
    GET  /insights/download  -> downloads the latest insights .txt file
    GET  /insights/filters   -> returns the unique primary_game / country values,
                                for populating the UI's filter dropdowns
    POST /insights/generate  -> regenerates insights.txt on demand, using the
                                top_n / group_by / filter_value chosen in the UI
"""

import csv
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from insights_engine import (
    DEFAULT_TOP_N,
    GROUP_BY_CHOICES,
    compute_insights,
    load_rows,
    unique_values,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = BASE_DIR / "uploads"
CSV_PATH = DATA_DIR / "influencers.csv"
GENERATED_INSIGHTS_NAME = "insights.txt"

DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = FastAPI(title="Simple CSV / Insights Site")

# Allow the frontend (served from a different origin/port, e.g. a static
# file server on :5500 or opened directly as a file) to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/csv")
def get_csv():
    """Read data/influencers.csv and return it as JSON (list of row dicts)."""
    if not CSV_PATH.exists():
        raise HTTPException(status_code=404, detail="influencers.csv not found on server")

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    return {"count": len(rows), "rows": rows}


@app.get("/csv/download")
def download_csv():
    """Let the browser download the raw CSV file."""
    if not CSV_PATH.exists():
        raise HTTPException(status_code=404, detail="influencers.csv not found on server")

    return FileResponse(
        path=CSV_PATH,
        filename="influencers.csv",
        media_type="text/csv",
    )


@app.post("/upload")
async def upload_txt(file: UploadFile = File(...)):
    """Accept a .txt file upload and save it to uploads/."""
    if not file.filename.lower().endswith(".txt"):
        raise HTTPException(status_code=400, detail="Only .txt files are accepted")

    dest_path = UPLOAD_DIR / os.path.basename(file.filename)

    contents = await file.read()
    with open(dest_path, "wb") as out:
        out.write(contents)

    return {"filename": dest_path.name, "size_bytes": len(contents), "saved_to": str(dest_path)}


def _latest_txt_file() -> Path | None:
    """Return the most recently modified .txt file in uploads/, or None."""
    txt_files = list(UPLOAD_DIR.glob("*.txt"))
    if not txt_files:
        return None
    return max(txt_files, key=lambda p: p.stat().st_mtime)


@app.get("/insights")
def get_insights():
    """Return the latest uploaded insights .txt file as JSON (filename + text content)."""
    latest = _latest_txt_file()
    if latest is None:
        raise HTTPException(status_code=404, detail="No insights file has been uploaded yet")

    content = latest.read_text(encoding="utf-8")
    return {"filename": latest.name, "content": content}


@app.delete("/insights")
def reset_insights():
    """Remove the generated insights output, if one exists."""
    generated_path = UPLOAD_DIR / GENERATED_INSIGHTS_NAME
    generated_path.unlink(missing_ok=True)
    return {"cleared": True}


@app.get("/insights/download")
def download_insights():
    """Let the browser download the latest uploaded insights .txt file."""
    latest = _latest_txt_file()
    if latest is None:
        raise HTTPException(status_code=404, detail="No insights file has been uploaded yet")

    return FileResponse(
        path=latest,
        filename=latest.name,
        media_type="text/plain",
    )


@app.get("/insights/filters")
def get_insight_filters():
    """
    Return the unique primary_game and country values from the CSV, so the
    UI can populate its "filter to a specific game/country" dropdown.
    """
    if not CSV_PATH.exists():
        raise HTTPException(status_code=404, detail="influencers.csv not found on server")

    rows = load_rows(CSV_PATH)
    return {
        "primary_game": unique_values(rows, "primary_game"),
        "country": unique_values(rows, "country"),
    }


class GenerateInsightsRequest(BaseModel):
    top_n: int = DEFAULT_TOP_N
    group_by: str = "none"
    filter_value: Optional[str] = None


@app.post("/insights/generate")
def generate_insights(request: GenerateInsightsRequest):
    """
    Regenerate insights.txt on demand, using parameters chosen in the UI:
      - top_n: how many influencers to include (overall, or per group)
      - group_by: "none" | "primary_game" | "country"
      - filter_value: when group_by is set, restrict to just this one value
                       (e.g. group_by="primary_game", filter_value="Valorant")
    Saves the result to uploads/insights.txt (overwriting any previous file
    with that name) and returns its content, same shape as GET /insights.
    """
    if request.group_by not in GROUP_BY_CHOICES:
        raise HTTPException(
            status_code=400,
            detail=f"group_by must be one of {GROUP_BY_CHOICES}",
        )
    if request.top_n < 1:
        raise HTTPException(status_code=400, detail="top_n must be at least 1")

    if not CSV_PATH.exists():
        raise HTTPException(status_code=404, detail="influencers.csv not found on server")

    rows = load_rows(CSV_PATH)
    content = compute_insights(
        rows,
        top_n=request.top_n,
        group_by=request.group_by,
        filter_value=request.filter_value,
    )

    dest_path = UPLOAD_DIR / GENERATED_INSIGHTS_NAME
    dest_path.write_text(content, encoding="utf-8")

    return {"filename": dest_path.name, "content": content}


app.mount(
    "/",
    StaticFiles(directory=BASE_DIR.parent / "frontend", html=True),
    name="frontend",
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
