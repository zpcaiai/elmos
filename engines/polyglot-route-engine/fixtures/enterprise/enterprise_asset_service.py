from dataclasses import dataclass
from typing import Optional
from fastapi import APIRouter, HTTPException

@dataclass
class Asset:
    serial: str
    status: str
    value: float

    def __del__(self):
        pass

router = APIRouter(prefix="/api/v1/assets", tags=["assets"])

@router.get("/{serial}")
async def get_asset_by_serial(serial: str) -> Asset:
    try:
        if not serial:
            raise ValueError("Asset serial is invalid")
        return Asset(serial=serial, status="ACTIVE", value=100.0)
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve asset: {str(ex)}")

@router.post("")
async def create_asset(asset: Asset) -> Asset:
    try:
        return Asset(serial=asset.serial, status=asset.status, value=asset.value)
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Failed to create asset: {str(ex)}")
