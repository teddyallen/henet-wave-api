from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional, Tuple

from .models import CombinedPoint, DispersionPoint, PerSwellResponse, SwellInput

PI = math.pi
G = 9.80665
EARTH_R = 6371.0
M_TO_FT = 3.28084
MPH_TO_MS = 0.44704


def rad(d: float) -> float:
    return d * PI / 180.0


def deg(r: float) -> float:
    return r * 180.0 / PI


def wrap360(a: float) -> float:
    return (a % 360 + 360) % 360


def smallest_angle(a: float, b: float) -> float:
    return ((a - b + 180) % 360 + 360) % 360 - 180


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = rad(lat1), rad(lat2)
    dp = rad(lat2 - lat1)
    dl = rad(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    return EARTH_R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2, dl = rad(lat1), rad(lat2), rad(lon2 - lon1)
    y = math.sin(dl) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dl)
    return wrap360(deg(math.atan2(y, x)))


def dest_point(lat: float, lon: float, brng: float, dist_km: float) -> Tuple[float, float]:
    phi1, lam1, th, delta = rad(lat), rad(lon), rad(brng), dist_km / EARTH_R
    phi2 = math.asin(math.sin(phi1) * math.cos(delta) + math.cos(phi1) * math.sin(delta) * math.cos(th))
    lam2 = lam1 + math.atan2(
        math.sin(th) * math.sin(delta) * math.cos(phi1),
        math.cos(delta) - math.sin(phi1) * math.sin(phi2),
    )
    return deg(phi2), ((deg(lam2) + 540) % 360) - 180


def wave_growth(wind_mph: float, fetch_km: float, duration_hr: float) -> dict:
    u = wind_mph * MPH_TO_MS
    f = fetch_km * 1000.0
    x = G * f / (u * u)
    hs_fetch = 0.0016 * math.sqrt(x) * u * u / G
    tp_fetch = 0.2857 * (x ** (1 / 3)) * u / G
    cg = G * tp_fetch / (4 * PI)
    req_hr = (f / cg) / 3600.0
    ratio = min(1.0, duration_hr / req_hr) if req_hr > 0 else 1.0
    return {
        'X': x,
        'Hs_fetch': hs_fetch,
        'Tp_fetch': tp_fetch,
        'Hs0': hs_fetch * math.sqrt(ratio),
        'Tp': tp_fetch * (ratio ** 0.25),
        'req_hr': req_hr,
        'ratio': ratio,
        'sufficient': duration_hr >= req_hr,
    }


def angular_correction(wave_to: float, src_to_bearing: float, n: float = 4.0) -> dict:
    dtheta = smallest_angle(src_to_bearing, wave_to)
    abs_dt = abs(dtheta)
    ef = 0.0 if abs_dt > 90 else math.cos(rad(abs_dt)) ** n
    return {'angle': dtheta, 'ef': ef, 'hf': math.sqrt(max(ef, 0.0))}


def decay_correction(dist_km: float, decay_km: float = 1500.0) -> dict:
    return {
        'ef': math.exp(-dist_km / decay_km),
        'hf': math.exp(-dist_km / (2 * decay_km)),
    }


def group_vel(tp: float) -> float:
    return G * tp / (4 * PI)


def get_spectrum_config(swell_type: str = 'manual') -> dict:
    st = (swell_type or 'manual').lower()
    if st == 'local':
        return {'tminF': 0.55, 'tmaxF': 1.18, 'maxPeriod': 10.5, 'gamma': 2.0, 'sigmaA': 0.07, 'sigmaB': 0.09}
    if st == 'trade':
        return {'tminF': 0.65, 'tmaxF': 1.22, 'maxPeriod': 14.0, 'gamma': 2.8, 'sigmaA': 0.07, 'sigmaB': 0.09}
    if st == 'natl':
        return {'tminF': 0.72, 'tmaxF': 1.35, 'maxPeriod': 22.0, 'gamma': 3.8, 'sigmaA': 0.07, 'sigmaB': 0.10}
    return {'tminF': 0.60, 'tmaxF': 1.28, 'maxPeriod': 18.0, 'gamma': 2.5, 'sigmaA': 0.07, 'sigmaB': 0.09}


def build_spectrum(tp: float, swell_type: str = 'manual', n: int = 17) -> List[Tuple[float, float]]:
    cfg = get_spectrum_config(swell_type)
    fp = 1.0 / max(tp, 0.1)
    tmin = max(2.5, cfg['tminF'] * tp)
    tmax_raw = cfg['tmaxF'] * tp
    tmax = min(tmax_raw, cfg['maxPeriod']) if cfg['maxPeriod'] is not None else tmax_raw
    tmin_eff = min(tmin, tmax * 0.96)
    periods = [tmin_eff + i * (tmax - tmin_eff) / (n - 1) for i in range(n)]

    sf = []
    for t in periods:
        f = 1.0 / max(t, 0.1)
        sigma = cfg['sigmaA'] if f <= fp else cfg['sigmaB']
        r = math.exp(-((f - fp) ** 2) / (2 * sigma * sigma * fp * fp))
        gamma_term = cfg['gamma'] ** r
        core = (f ** -5.0) * math.exp(-1.25 * ((fp / f) ** 4)) * gamma_term
        s_t = core / (t * t)
        sf.append(max(s_t, 0.0))

    smax = max(sf) if sf else 1.0
    weights = [v / smax for v in sf]
    return list(zip(periods, weights))


def compute_swell(inp: SwellInput) -> PerSwellResponse:
    wave_to = wrap360(inp.wind_dir_from_deg + 180.0)
    growth = wave_growth(inp.wind_mph, inp.fetch_km, inp.duration_hr)

    ctr_dist = haversine(inp.src_lat, inp.src_lon, inp.tgt_lat, inp.tgt_lon)
    ctr_brng = bearing(inp.src_lat, inp.src_lon, inp.tgt_lat, inp.tgt_lon)
    ex_lat, ex_lon = dest_point(inp.src_lat, inp.src_lon, wave_to, inp.fetch_km / 2.0)
    trav_dist = haversine(ex_lat, ex_lon, inp.tgt_lat, inp.tgt_lon)
    trav_brng = bearing(ex_lat, ex_lon, inp.tgt_lat, inp.tgt_lon)

    ang = angular_correction(wave_to, trav_brng, inp.spread_exponent_n)
    dec = decay_correction(trav_dist, inp.decay_km)

    tp = growth['Tp']
    cg = group_vel(tp)
    travel_hr = (trav_dist * 1000.0 / cg) / 3600.0 if cg > 0 else 0.0
    hs_end_m = growth['Hs0']
    hs_ang_m = hs_end_m * ang['hf']
    hs_tgt_m = hs_ang_m * dec['hf']

    spectrum = build_spectrum(tp, inp.swell_type, n=17)
    rows = []
    peak_idx = 0
    peak_w = -1.0
    for idx, (period_s, w) in enumerate(spectrum):
        if w > peak_w:
            peak_w = w
            peak_idx = idx
        cg_i = group_vel(period_s)
        thr = (trav_dist * 1000.0 / cg_i) / 3600.0 if cg_i > 0 else 0.0
        h_m = hs_tgt_m * math.sqrt(max(w, 0.0))
        arr_time = None
        if inp.generation_midpoint_utc is not None:
            gen = inp.generation_midpoint_utc
            if gen.tzinfo is None:
                gen = gen.replace(tzinfo=timezone.utc)
            arr_time = gen + timedelta(hours=thr)
        rows.append((period_s, w, cg_i, thr, arr_time, h_m))

    first_ar = min(r[3] for r in rows)
    peak_ar = rows[peak_idx][3]
    last_ar = max(r[3] for r in rows)
    genmid = inp.generation_midpoint_utc
    if genmid is not None and genmid.tzinfo is None:
        genmid = genmid.replace(tzinfo=timezone.utc)

    disp = [
        DispersionPoint(
            period_s=round(period_s, 3),
            group_velocity_ms=round(cg_i, 4),
            travel_hr=round(thr, 4),
            arrival_time_utc=arr_time,
            wave_height_ft=round(h_m * M_TO_FT, 4),
            wave_height_m=round(h_m, 4),
            is_peak=(i == peak_idx),
        )
        for i, (period_s, _w, cg_i, thr, arr_time, h_m) in enumerate(rows)
    ]

    def dt_at(hours: float) -> Optional[datetime]:
        return genmid + timedelta(hours=hours) if genmid is not None else None

    return PerSwellResponse(
        id=inp.id,
        enabled=inp.enabled,
        swell_type=inp.swell_type,
        wave_to_deg=round(trav_brng, 3),
        swell_from_deg=round(wrap360(trav_brng + 180.0), 3),
        source_to_target_distance_km=round(ctr_dist, 3),
        source_to_target_bearing_deg=round(ctr_brng, 3),
        fetch_exit_lat=round(ex_lat, 5),
        fetch_exit_lon=round(ex_lon, 5),
        travel_distance_km=round(trav_dist, 3),
        off_axis_angle_deg=round(ang['angle'], 3),
        angular_height_factor=round(ang['hf'], 6),
        decay_height_factor=round(dec['hf'], 6),
        fetch_hs_full_m=round(growth['Hs_fetch'], 6),
        fetch_tp_full_s=round(growth['Tp_fetch'], 6),
        required_duration_hr=round(growth['req_hr'], 6),
        duration_growth_ratio=round(growth['ratio'], 6),
        duration_sufficient=bool(growth['sufficient']),
        hs_fetch_end_ft=round(hs_end_m * M_TO_FT, 4),
        hs_after_angular_ft=round(hs_ang_m * M_TO_FT, 4),
        hs_at_target_ft=round(hs_tgt_m * M_TO_FT, 4),
        hs_at_target_m=round(hs_tgt_m, 4),
        tp_s=round(tp, 4),
        bulk_group_velocity_ms=round(cg, 4),
        bulk_travel_hr=round(travel_hr, 4),
        first_arrival_hr=round(first_ar, 4),
        peak_arrival_hr=round(peak_ar, 4),
        last_arrival_hr=round(last_ar, 4),
        first_arrival_time_utc=dt_at(first_ar),
        peak_arrival_time_utc=dt_at(peak_ar),
        last_arrival_time_utc=dt_at(last_ar),
        bulk_arrival_time_utc=dt_at(travel_hr),
        generation_midpoint_utc=genmid,
        dispersion=disp,
    )


def interp_series(points: List[Tuple[float, float]], x: float) -> float:
    if not points:
        return 0.0
    if x < points[0][0] or x > points[-1][0]:
        return 0.0
    if x == points[0][0]:
        return points[0][1]
    if x == points[-1][0]:
        return points[-1][1]
    for i in range(1, len(points)):
        x0, y0 = points[i - 1]
        x1, y1 = points[i]
        if x <= x1:
            if x1 == x0:
                return y1
            t = (x - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)
    return 0.0


def compute_batch(swells: Iterable[SwellInput]) -> Tuple[List[PerSwellResponse], List[CombinedPoint], str]:
    active_inputs = [s for s in swells if s.enabled]
    results = [compute_swell(s) for s in active_inputs]
    if not results:
        return [], [], 'travel_hours'

    use_arrival = all(all(dp.arrival_time_utc is not None for dp in r.dispersion) for r in results)
    x_mode = 'arrival_time' if use_arrival else 'travel_hours'

    all_x = set()
    series = []
    for r in results:
        if use_arrival:
            pts = sorted((dp.arrival_time_utc.timestamp(), dp.wave_height_ft) for dp in r.dispersion if dp.arrival_time_utc)
        else:
            pts = sorted((dp.travel_hr, dp.wave_height_ft) for dp in r.dispersion)
        series.append(pts)
        all_x.update(x for x, _ in pts)

    combined = []
    for x in sorted(all_x):
        hs_sq = 0.0
        for pts in series:
            h = interp_series(pts, x)
            hs_sq += h * h
        combined_hs = math.sqrt(hs_sq)
        combined.append(
            CombinedPoint(
                x=round(x, 6),
                x_iso_utc=(datetime.fromtimestamp(x, tz=timezone.utc).isoformat() if use_arrival else None),
                combined_hs_ft=round(combined_hs, 4),
            )
        )
    return results, combined, x_mode
