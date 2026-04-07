from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

SwellType = Literal['manual', 'local', 'trade', 'natl']


class SwellInput(BaseModel):
    id: int = Field(..., ge=1, le=3)
    enabled: bool = True
    swell_type: SwellType = 'manual'
    wind_mph: float = Field(..., gt=0)
    wind_dir_from_deg: float = Field(..., ge=0, le=360)
    src_lat: float = Field(..., ge=-90, le=90)
    src_lon: float = Field(..., ge=-180, le=180)
    tgt_lat: float = Field(..., ge=-90, le=90)
    tgt_lon: float = Field(..., ge=-180, le=180)
    fetch_km: float = Field(..., gt=0)
    duration_hr: float = Field(..., gt=0)
    generation_midpoint_utc: Optional[datetime] = None
    decay_km: float = Field(1500.0, gt=0)
    spread_exponent_n: float = Field(4.0, gt=0)

    @field_validator('wind_dir_from_deg')
    @classmethod
    def normalize_dir(cls, v: float) -> float:
        return v % 360


class BatchRequest(BaseModel):
    swells: List[SwellInput] = Field(..., min_length=1, max_length=3)


class DispersionPoint(BaseModel):
    period_s: float
    group_velocity_ms: float
    travel_hr: float
    arrival_time_utc: Optional[datetime]
    wave_height_ft: float
    wave_height_m: float
    is_peak: bool


class PerSwellResponse(BaseModel):
    id: int
    enabled: bool
    swell_type: SwellType
    wave_to_deg: float
    swell_from_deg: float
    source_to_target_distance_km: float
    source_to_target_bearing_deg: float
    fetch_exit_lat: float
    fetch_exit_lon: float
    travel_distance_km: float
    off_axis_angle_deg: float
    angular_height_factor: float
    decay_height_factor: float
    fetch_hs_full_m: float
    fetch_tp_full_s: float
    required_duration_hr: float
    duration_growth_ratio: float
    duration_sufficient: bool
    hs_fetch_end_ft: float
    hs_after_angular_ft: float
    hs_at_target_ft: float
    hs_at_target_m: float
    tp_s: float
    bulk_group_velocity_ms: float
    bulk_travel_hr: float
    first_arrival_hr: float
    peak_arrival_hr: float
    last_arrival_hr: float
    first_arrival_time_utc: Optional[datetime]
    peak_arrival_time_utc: Optional[datetime]
    last_arrival_time_utc: Optional[datetime]
    bulk_arrival_time_utc: Optional[datetime]
    generation_midpoint_utc: Optional[datetime]
    dispersion: List[DispersionPoint]


class CombinedPoint(BaseModel):
    x: float
    x_iso_utc: Optional[str] = None
    combined_hs_ft: float


class BatchResponse(BaseModel):
    swells: List[PerSwellResponse]
    combined_timeline: List[CombinedPoint]
    x_axis_mode: Literal['arrival_time', 'travel_hours']
