from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .models import BatchRequest, BatchResponse
from .physics import compute_batch

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / 'static'
API_KEY = os.getenv('HENET_API_KEY')
CORS_ORIGINS = [o.strip() for o in os.getenv('CORS_ORIGINS', '*').split(',') if o.strip()]

app = FastAPI(title='Henet Wave API', version='1.0.0')
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS if CORS_ORIGINS != ['*'] else ['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

if STATIC_DIR.exists():
    app.mount('/static', StaticFiles(directory=str(STATIC_DIR)), name='static')


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if not API_KEY:
        return
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail='Invalid API key')


@app.get('/health')
def health() -> dict:
    return {'status': 'ok'}


@app.post('/api/v1/calculate', response_model=BatchResponse, dependencies=[Depends(require_api_key)])
def calculate(req: BatchRequest) -> BatchResponse:
    swells, combined, x_mode = compute_batch(req.swells)
    return BatchResponse(swells=swells, combined_timeline=combined, x_axis_mode=x_mode)


@app.get('/')
def root() -> FileResponse:
    return FileResponse(STATIC_DIR / 'index.html')
