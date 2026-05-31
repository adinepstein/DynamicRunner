from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(tags=["auth"])


@router.get("/me")
def me(request: Request) -> dict[str, str]:
    return {"uid": request.state.uid}
