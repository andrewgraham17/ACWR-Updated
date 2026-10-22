"""
K-State Baseball — Throwing Workload Model (calculation engine)

Every constant and rule below is copied from the Fall 2026 ACWR workbook
(Reference tab, Day Type Templates tab, Next Outing Planner tab).
To re-tune the model, edit the values in this file — nowhere else.
The Build-Up engine lives in buildup.py and uses the same functions.
"""
from __future__ import annotations

import math
from datetime import date, time, timedelta

# ─────────────────────────────────────────────────────────────
# REFERENCE TABLES  (Reference tab)
# ─────────────────────────────────────────────────────────────

# Distance Factor — smooth: in-between distances fall on a straight line between these points.
# 60 ft and shorter all score 1.0; 210 ft and beyond all score 3.5.
DISTANCE_TABLE = [
    (60, 1.0, "Warm-up / catch play — 60 ft and shorter all score 1.0"),
    (90, 1.3, "Building distance (75 ft = 1.15, halfway between 60 and 90)"),
    (120, 1.7, "Extension / stretch (105 ft = 1.5)"),
    (150, 2.2, "Long toss (135 ft = 1.95)"),
    (180, 2.8, "Max long toss (165 ft = 2.5)"),
    (210, 3.5, "Pulldowns / max distance — 210 ft and beyond all score 3.5"),
]

# Intensity Factor — (min mph below Avg Top Velo, factor, description)
INTENSITY_TABLE = [
    (0, 2.0, "Max effort — at or near Avg Top Velo (about 0–3 mph off)"),
    (4, 1.5, "Compete / high intent (about 4–6 mph off)"),
    (7, 1.0, "Building (about 7–9 mph off)"),
    (10, 0.6, "Easy / recovery catch (10+ mph off)"),
]

# ACWR zones — (min ACWR, zone, guidance)
ZONE_TABLE = [
    (0.0, "Undertrained", "Below 0.8 — there is room to progress distance/intensity next session."),
    (0.8, "Sweet Spot", "0.8–1.3 — ideal loading zone; maintain the planned progression."),
    (1.31, "Caution", "1.3–1.5 — hold volume/intensity flat; add a recovery day this week."),
    (1.51, "High Risk", "Above 1.5 — mandatory easy/rest day next session; cut weekly volume 20–30%."),
]
INSUFFICIENT_ZONE = "Insufficient history (need ~28 days logged)"
INSUFFICIENT_GUIDANCE = (
    "Log at least 28 days of throws for a reliable trend. Meanwhile, rely on RPE "
    "and arm feedback before adding volume."
)

SESSION_TYPES = [
    "No Throw",
    "Long Toss",
    "Compression/Pulldowns",
    "Bullpen",
    "Moderate",
    "Game",
    "Recovery/Easy Catch",
]

# Throw rate (throws / minute) — used to estimate throw count from clock time
THROW_RATE = {
    "No Throw": 0,
    "Long Toss": 3.5,
    "Compression/Pulldowns": 3,
    "Bullpen": 2.5,
    "Moderate": 4,
    "Game": 0,
    "Recovery/Easy Catch": 5.5,
}

# Mound Factor — used INSTEAD of Distance Factor for Bullpen & Game
MOUND_FACTOR = {"Bullpen": 3.0, "Game": 3.2}
MOUND_TYPES = ("Bullpen", "Game")

# Back-to-back mound days — a Bullpen/Game day thrown right after another outing
B2B_NEXT_DAY = 1.5      # outing the day after another outing
B2B_ONE_GAP = 1.25      # outing with one day between it and the last outing

# Periodization Rule — default day type by days until next High-Intent Day
TAPER_RULE = {
    0: ("Game", "The High-Intent Day itself — fixed by the schedule (Game or High Bullpen), not a training choice."),
    1: ("Low", "Day before he pitches: stay loose and protect freshness — never build here."),
    2: ("Medium", "Two days out: moderate catch play while yesterday's work clears."),
    3: ("High Bullpen", "Classic starter bullpen day — enough runway to recover before the next outing."),
    4: ("Medium", "Build day — moderate long toss/pulldowns, not yet max effort."),
    5: ("Low", "Start of taper week: 5 days out, base/recovery work before the build back up."),
}
# Far-out build cycle — (days-6) MOD 3
FAR_OUT_CYCLE = {
    0: ("Medium", "Build day in the repeating base cycle."),
    1: ("High Non-Bullpen", "Compete/high-intent day in the repeating base cycle."),
    2: ("Low", "Recovery day in the repeating base cycle — spaced so it never lands two days running."),
}

DAY_TYPES = ["Low", "Medium", "High Non-Bullpen", "High Bullpen", "Game"]
OVERRIDE_CHOICES = ["(none)", "No Throw", "Low", "Medium", "High Non-Bullpen", "High Bullpen", "Game"]
HIGH_INTENT_TYPES = ["Game", "High Bullpen", "Low Bullpen"]

PLANNER_MAX_DAYS = 42          # the workbook plans up to 42 days ahead
RATIO_HIGH, RATIO_LOW = 1.2, 0.8   # prior-day actual/planned thresholds (±20 %)
SPIKE_THRESHOLD = 1.5

# ─────────────────────────────────────────────────────────────
# DAY TYPE TEMPLATES  (Day Type Templates tab)
# (category, example#, segment#, segment type, distance ft or None=mound,
#  throws low, throws high, deficit low, deficit high)
# Long Toss past 90 ft is a step-out: distance = farthest step, throws = total for all steps.
# ─────────────────────────────────────────────────────────────
TEMPLATE_SEGMENTS = [
    ("Low", 1, 1, "Long Toss", 90, 45, 55, 14, 18),
    ("Low", 1, 2, "Flat Ground", 60, 15, 25, 12, 14),
    ("Low", 2, 1, "Long Toss", 75, 35, 45, 15, 19),
    ("Low", 2, 2, "Flat Ground", 60, 15, 20, 13, 15),
    ("Medium", 1, 1, "Long Toss", 120, 45, 60, 7, 9),
    ("Medium", 1, 2, "Flat Ground", 60, 15, 20, 5, 7),
    ("Medium", 2, 1, "Compression/Pulldowns", 90, 30, 40, 7, 9),
    ("Medium", 2, 2, "Flat Ground", 60, 15, 20, 5, 7),
    ("High Non-Bullpen", 1, 1, "Long Toss", 150, 40, 55, 7, 9),
    ("High Non-Bullpen", 1, 2, "Compression/Pulldowns", 120, 20, 30, 0, 3),
    ("High Non-Bullpen", 1, 3, "Flat Ground", 60, 15, 20, 4, 6),
    ("High Non-Bullpen", 2, 1, "Long Toss", 180, 40, 55, 4, 6),
    ("High Non-Bullpen", 2, 2, "Compression/Pulldowns", 90, 15, 20, 0, 3),
    ("High Non-Bullpen", 2, 3, "Flat Ground", 60, 15, 20, 4, 6),
    ("High Bullpen", 1, 1, "Long Toss", 90, 20, 30, 7, 9),
    ("High Bullpen", 1, 2, "Bullpen", None, 25, 35, 0, 3),
    ("High Bullpen", 2, 1, "Long Toss", 120, 15, 25, 7, 9),
    ("High Bullpen", 2, 2, "Bullpen", None, 20, 25, 0, 3),
    ("Game", 1, 1, "Bullpen", None, 15, 20, 3, 6),
    ("Game", 1, 2, "Game", None, 20, 30, 0, 3),
    ("Game", 2, 1, "Bullpen", None, 20, 25, 3, 6),
    ("Game", 2, 2, "Game", None, 60, 80, 0, 3),
]


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────
def _blank(v) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    if isinstance(v, str) and v.strip() == "":
        return True
    try:
        import pandas as pd
        if v is pd.NaT or (not isinstance(v, (str, bytes)) and pd.isna(v)):
            return True
    except Exception:
        pass
    return False


def excel_round(x: float, digits: int = 0) -> float:
    """Excel ROUND (half away from zero) — Python's round() is banker's rounding."""
    m = 10 ** digits
    return math.copysign(math.floor(abs(x) * m + 0.5), x) / m


def _vlookup(x, table):
    """Approximate-match VLOOKUP: row with the largest key <= x (None if below first key)."""
    hit = None
    for row in table:
        if x >= row[0]:
            hit = row
        else:
            break
    return hit


def interp_factor(distance_ft) -> float:
    """Distance Factor on a straight line between the table points (clamped 60–210 ft)."""
    pts = DISTANCE_TABLE
    d = max(pts[0][0], min(pts[-1][0], float(distance_ft)))
    i = 0
    for j, p in enumerate(pts):
        if p[0] <= d:
            i = j
    i = min(i, len(pts) - 2)
    (x0, y0, _), (x1, y1, _) = pts[i], pts[i + 1]
    return y0 + (d - x0) * (y1 - y0) / (x1 - x0)


def lt_steps(session_type, distance_ft) -> int:
    """Long toss past 90 ft is scored as a step-out every 30 ft: 90, 120, 150 … up to his farthest distance."""
    if session_type == "Long Toss" and not _blank(distance_ft) and float(distance_ft) > 90:
        return 1 + math.ceil((float(distance_ft) - 90) / 30 - 1e-12)
    return 1


def _step_dist(distance_ft, k):
    return min(float(distance_ft), 60 + 30 * k)


def stepped_factor(distance_ft, steps: int) -> float:
    """Throw-weighted average Distance Factor of the step-out (more throws at the short steps)."""
    if steps <= 1:
        return interp_factor(distance_ft)
    total = sum((steps - k + 3) * interp_factor(_step_dist(distance_ft, k)) for k in range(1, min(steps, 8) + 1))
    return total / (steps * (steps + 5) / 2)


def step_split(distance_ft, throws, steps: int) -> str:
    """'90×30 · 120×23' — how a long-toss throw total splits across the steps."""
    if steps <= 1:
        return ""
    denom = steps * (steps + 5) / 2
    parts, prev = [], 0
    for k in range(1, min(steps, 8) + 1):
        cum = excel_round(throws * (k * (steps + 3) - k * (k + 1) / 2) / denom)
        d = _step_dist(distance_ft, k)
        parts.append(f"{int(d) if float(d).is_integer() else d}×{int(cum - prev)}")
        prev = cum
    return " · ".join(parts)


def distance_factor(distance_ft, session_type=None):
    """Distance Factor for a flat-ground set (long toss uses the step-out average)."""
    if _blank(distance_ft):
        return None
    return stepped_factor(distance_ft, lt_steps(session_type, distance_ft))


def intensity_factor(deficit):
    if _blank(deficit):
        return None
    return _vlookup(max(float(deficit), 0), INTENSITY_TABLE)[1]


def velo_mid(lo, hi):
    if _blank(lo):
        return None
    if _blank(hi):
        return float(lo)
    return (float(lo) + float(hi)) / 2


def _to_minutes(t):
    if _blank(t):
        return None
    if isinstance(t, time):
        return t.hour * 60 + t.minute + t.second / 60
    if isinstance(t, str):
        parts = t.strip().split(":")
        return int(parts[0]) * 60 + int(parts[1]) + (int(parts[2]) / 60 if len(parts) > 2 else 0)
    if hasattr(t, "hour"):
        return t.hour * 60 + t.minute
    return None


def _duration(s, e):
    """(End − Start) × 1440 exactly as Excel computes it (times stored as fractions of a day)."""
    return (e / 1440 - s / 1440) * 1440


# ─────────────────────────────────────────────────────────────
# THROW LOG ROW CALCULATION  (Throw Log columns G, I, L–Q, U–W, AA–AG)
# ─────────────────────────────────────────────────────────────
def calc_row(r: dict, avg_top, b2b=None) -> dict:
    """One Throw Log row. `b2b` is the back-to-back multiplier (see calc_rows); None = not applied."""
    stype = r.get("session_type")
    avg_top = None if _blank(avg_top) or float(avg_top) == 0 else float(avg_top)

    # Duration (min)
    s, e = _to_minutes(r.get("start_time")), _to_minutes(r.get("end_time"))
    duration = _duration(s, e) if (s is not None and e is not None) else None

    # Throws used in calc — Actual Throw Count overrides the time estimate
    if not _blank(r.get("actual_throws")):
        throws = float(r["actual_throws"])
    elif duration is not None:
        throws = excel_round(duration * THROW_RATE.get(stype, 0))
    else:
        throws = None

    mid = velo_mid(r.get("velo_low"), r.get("velo_high"))
    deficit = (avg_top - mid) if (mid is not None and avg_top is not None) else None

    steps = 1
    if stype in MOUND_TYPES:
        factor = MOUND_FACTOR[stype]
    else:
        steps = lt_steps(stype, r.get("distance"))
        factor = distance_factor(r.get("distance"), stype)
    intensity = intensity_factor(deficit)

    # Warm-up / bullpen segment (always scored at Bullpen Mound Factor)
    w_mid = velo_mid(r.get("warm_velo_low"), r.get("warm_velo_high"))
    w_def = (avg_top - w_mid) if (w_mid is not None and avg_top is not None) else None
    w_int = intensity_factor(w_def)

    # 60' working-back-in segment (always scored at the 60 ft Distance Factor)
    s_mid = velo_mid(r.get("sixty_velo_low"), r.get("sixty_velo_high"))
    s_def = (avg_top - s_mid) if (s_mid is not None and avg_top is not None) else None
    s_int = intensity_factor(s_def)

    main_ok = throws is not None and factor is not None and intensity is not None
    warm_ok = not _blank(r.get("warm_throws")) and w_int is not None
    sixty_ok = not _blank(r.get("sixty_throws")) and s_int is not None

    if not (main_ok or warm_ok or sixty_ok):
        before = None
    else:
        before = (
            (throws * factor * intensity if main_ok else 0)
            + (float(r["warm_throws"]) * MOUND_FACTOR["Bullpen"] * w_int if warm_ok else 0)
            + (float(r["sixty_throws"]) * interp_factor(60) * s_int if sixty_ok else 0)
        )
    mult = b2b if stype in MOUND_TYPES else None
    workload = None if before is None else before * (mult or 1)

    return {
        "duration_min": duration,
        "throws_used": throws,
        "velo_mid": mid,
        "avg_top_velo": avg_top,
        "velo_deficit": deficit,
        "lt_steps": steps,
        "dist_mound_factor": factor,
        "intensity_factor": intensity,
        "warm_velo_mid": w_mid,
        "warm_deficit": w_def,
        "warm_intensity": w_int,
        "sixty_velo_mid": s_mid,
        "sixty_deficit": s_def,
        "sixty_intensity": s_int,
        "workload_before_b2b": before,
        "b2b_multiplier": mult,
        "set_workload": workload,
    }


def _as_date(d):
    if _blank(d):
        return None
    if isinstance(d, date) and not hasattr(d, "hour"):
        return d
    if hasattr(d, "date"):
        return d.date()
    return date.fromisoformat(str(d)[:10])


def b2b_multiplier(day, session_type, outing_days) -> float | None:
    """Back-to-back rule: `outing_days` = dates with a Bullpen/Game row whose workload is > 0."""
    if session_type not in MOUND_TYPES or day is None:
        return None
    if day - timedelta(days=1) in outing_days:
        return B2B_NEXT_DAY
    if day - timedelta(days=2) in outing_days:
        return B2B_ONE_GAP
    return 1.0


def calc_rows(records: list[dict], avg_top) -> list[dict]:
    """Calculate a player's whole log, including the back-to-back mound-day multiplier."""
    first = [calc_row(r, avg_top) for r in records]
    outing_days = {_as_date(r.get("date")) for r, c in zip(records, first)
                   if r.get("session_type") in MOUND_TYPES and (c["workload_before_b2b"] or 0) > 0}
    return [calc_row(r, avg_top, b2b_multiplier(_as_date(r.get("date")), r.get("session_type"), outing_days))
            for r in records]


def daily_totals(log_df) -> dict:
    """{date: summed Set Workload} for one player's calculated log."""
    out: dict = {}
    if log_df is None or len(log_df) == 0:
        return out
    for d, w in zip(log_df["date"], log_df["set_workload"]):
        if _blank(d) or _blank(w):
            continue
        d = d if isinstance(d, date) else d.date()
        out[d] = out.get(d, 0.0) + float(w)
    return out


# ─────────────────────────────────────────────────────────────
# DASHBOARD  (Dashboard tab)
# ─────────────────────────────────────────────────────────────
def zone_for(acwr, chronic):
    if not chronic or acwr is None:
        return INSUFFICIENT_ZONE, INSUFFICIENT_GUIDANCE
    r = _vlookup(acwr, ZONE_TABLE)
    return (r[1], r[2]) if r else ("Insufficient history", "")


def status(daily: dict, as_of: date) -> dict:
    def window(n):
        return sum(daily.get(as_of - timedelta(days=i), 0.0) for i in range(n))

    today = daily.get(as_of, 0.0)
    acute = window(7) / 7
    chronic = window(28) / 28
    acwr = acute / chronic if chronic else None
    zone, guidance = zone_for(acwr, chronic)
    spike = today / chronic if chronic else None
    if spike is None:
        spike_flag = ""
    elif spike > SPIKE_THRESHOLD:
        spike_flag = "High single-day spike — mandatory easy/rest day next session"
    else:
        spike_flag = "OK"
    return dict(today=today, acute=acute, chronic=chronic, acwr=acwr,
                zone=zone, guidance=guidance, spike=spike, spike_flag=spike_flag)


def weekly_table(daily: dict, as_of: date, weeks: int = 12) -> list[dict]:
    """Weekly workload for the last `weeks` 7-day weeks ending on `as_of` (Dashboard rows 52–63)."""
    rows, prev = [], None
    for i in range(weeks - 1, -1, -1):
        end = as_of - timedelta(days=7 * i)
        start = end - timedelta(days=6)
        days = [start + timedelta(days=k) for k in range(7)]
        load = sum(daily.get(d, 0.0) for d in days)
        rows.append(dict(week_of=start, week_ending=end, workload=load,
                         throwing_days=sum(1 for d in days if daily.get(d, 0.0) > 0),
                         change=(load / prev - 1) if prev else None))
        prev = load
    return rows


def zone_adjustment(zone: str) -> int:
    if zone in ("Caution", "High Risk"):
        return -1
    if zone == "Undertrained":
        return 1
    return 0


# ─────────────────────────────────────────────────────────────
# DAY TYPE TEMPLATES
# ─────────────────────────────────────────────────────────────
def segment_factor(seg_type, distance):
    if seg_type in MOUND_TYPES:
        return MOUND_FACTOR[seg_type]
    return distance_factor(distance, seg_type)


def template_rows(avg_top):
    rows = []
    for cat, ex, sg, st, dist, tlo, thi, dlo, dhi in TEMPLATE_SEGMENTS:
        tmid, dmid = (tlo + thi) / 2, (dlo + dhi) / 2
        f = segment_factor(st, dist)
        i = intensity_factor(dmid)
        steps = lt_steps(st, dist)
        rows.append(dict(
            category=cat, example=ex, segment=sg, segment_type=st, distance=dist,
            throws_low=tlo, throws_high=thi, throws_mid=tmid,
            deficit_low=dlo, deficit_high=dhi, deficit_mid=dmid,
            velo_low=excel_round(avg_top - dhi) if avg_top else None,
            velo_high=excel_round(avg_top - dlo) if avg_top else None,
            factor=f, intensity=i, workload=tmid * f * i,
            steps=steps, step_text=step_split(dist, tmid, steps),
        ))
    return rows


def _fmt_num(x):
    return str(int(x)) if x is not None and float(x).is_integer() else str(x)


def segment_text(seg, avg_top):
    steps = lt_steps(seg.get("segment_type"), seg["distance"]) if seg.get("segment_type") else 1
    if steps > 1:
        tmid = (seg["throws_low"] + seg["throws_high"]) / 2
        txt = (f'Long toss out to {seg["distance"]} ft — {seg["throws_low"]}-{seg["throws_high"]} throws '
               f'({step_split(seg["distance"], tmid, steps)})')
    else:
        where = "Mound" if seg["distance"] is None else f'{seg["distance"]} ft'
        txt = f'{where} — {seg["throws_low"]}-{seg["throws_high"]} throws'
    if avg_top:
        txt += f' @ {_fmt_num(excel_round(avg_top - seg["deficit_high"]))}-{_fmt_num(excel_round(avg_top - seg["deficit_low"]))} mph'
    return txt


def plan_text(day_type: str, avg_top, example: int = 1) -> str:
    if day_type == "No Throw":
        return "Full rest — no throwing today."
    if day_type == "Game":
        return "Game — see Reference tab for warm-up rules"
    segs = [dict(segment_type=st, distance=d, throws_low=tl, throws_high=th, deficit_low=dl, deficit_high=dh)
            for c, ex, _, st, d, tl, th, dl, dh in TEMPLATE_SEGMENTS if c == day_type and ex == example]
    if not segs:
        return ""
    return "  +  ".join(segment_text(s, avg_top) for s in segs)


def template_summary(avg_top=None):
    rows = template_rows(avg_top or 0)
    ex_tot: dict = {}
    for r in rows:
        ex_tot[(r["category"], r["example"])] = ex_tot.get((r["category"], r["example"]), 0) + r["workload"]
    summary = []
    for cat in DAY_TYPES:
        summary.append(dict(
            day_type=cat,
            ex1=ex_tot[(cat, 1)], ex2=ex_tot[(cat, 2)],
            avg=(ex_tot[(cat, 1)] + ex_tot[(cat, 2)]) / 2,
        ))
    return summary


TEMPLATE_AVG = {r["day_type"]: r["avg"] for r in template_summary()}


# ─────────────────────────────────────────────────────────────
# NEXT OUTING PLANNER  (Next Outing Planner tab)
# ─────────────────────────────────────────────────────────────
def baseline_day_type(days_until: int) -> str:
    if days_until <= 5:
        return TAPER_RULE.get(days_until, ("Low",))[0]
    return FAR_OUT_CYCLE[(days_until - 6) % 3][0]


def tier(day_type: str) -> int:
    if day_type == "No Throw":
        return 0
    if day_type == "Low":
        return 1
    if day_type == "Medium":
        return 2
    if day_type in ("High Non-Bullpen", "High Bullpen"):
        return 3
    return 4


TIER_TO_TYPE = {1: "Low", 2: "Medium", 3: "High Non-Bullpen"}


def build_plan(daily: dict, today: date, target: date, zone_adj: int,
               overrides: dict, avg_top) -> list[dict]:
    rows = []
    prev = None
    for i in range(1, PLANNER_MAX_DAYS + 1):
        d = today + timedelta(days=i)
        if d >= target:
            break
        c = (target - d).days
        ov = overrides.get(d)
        ov = ov if ov and ov in OVERRIDE_CHOICES and ov != "(none)" else None
        base = ov or baseline_day_type(c)
        e = tier(base)
        prior_date = d - timedelta(days=1)
        g = c + 1
        prior_type = baseline_day_type(g) if prev is None else prev["final"]
        planned = TEMPLATE_AVG.get(prior_type)
        actual = daily.get(prior_date, 0.0)
        ratio = 1.0 if (not planned or not actual) else actual / planned
        l_adj = -1 if ratio > RATIO_HIGH else (1 if ratio < RATIO_LOW else 0)
        if prev is None:
            m_shift = 0
        else:
            pt, pb = tier(prev["final"]), tier(baseline_day_type(prev["days_until"]))
            m_shift = 0 if pt == pb else (-1 if pt > pb else 1)
        combined = m_shift if m_shift != 0 else min(l_adj, zone_adj)
        clamped = min(combined, 0) if c == 1 else combined
        q = min(3, max(1, e + clamped))
        final = ov or (base if q == e else TIER_TO_TYPE[q])
        row = dict(
            date=d, day=d.strftime("%a"), days_until=c, baseline=base, baseline_tier=e,
            prior_date=prior_date, prior_days_until=g, prior_type=prior_type,
            prior_planned=planned, prior_actual=actual, ratio=ratio,
            prior_adj=l_adj, plan_shift=m_shift, zone_adj=zone_adj,
            combined=combined, clamped=clamped, final_tier=q, final=final,
            plan=plan_text(final, avg_top), override=ov or "(none)",
        )
        rows.append(row)
        prev = row
    return rows


def outing_text(target_type, target, avg_top, pitches=None, innings=None) -> str:
    head = f'({target.strftime("%a")} {target.month}/{target.day} — {target_type}) '
    if target_type == "Game":
        has_p, has_i = not _blank(pitches), not _blank(innings)
        if not has_p and not has_i:
            return head + "Enter planned pitches/innings above — velo can't be predicted for a live game."
        if has_p and has_i:
            return head + f"Planned: {_fmt_num(pitches)} pitches over {_fmt_num(innings)} innings"
        return head + (f"Planned: {_fmt_num(pitches)} pitches" if has_p else f"Planned: {_fmt_num(innings)} innings")
    # The workbook shows the Low example for a Low Bullpen target (it no longer has its own template)
    return head + plan_text("Low" if target_type == "Low Bullpen" else target_type, avg_top)
