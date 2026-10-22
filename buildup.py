"""
Build-Up Plan engine — a day-by-day ramp from first catch play to the first bullpen.
Mirrors the workbook's Build-Up tabs cell for cell (Reference tab ▸ Build-Up Engine Settings).
Throw counts are solved from the same Distance × Intensity workload model as the Throw Log,
so the plan's ACWR stays in the 0.8–1.3 sweet spot.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import model as m

# ───────── Build-Up Engine Settings (Reference tab) ─────────
STARTING_POINTS = {   # name: (start weekly load, starting progress 0–1, recommended minimum window days)
    "Auto (from Throw Log)": None,
    "From scratch": (80, 0.0, 84),
    "Already throwing (60–90 ft)": (130, 0.2, 56),
    "Already long tossing (120 ft+)": (180, 0.4, 42),
}
AUTO_MIN_WINDOW_ACTIVE, AUTO_MIN_WINDOW_RESTART = 42, 84
PEAK_WEEKLY_LOAD = 260
MAX_WEEKLY_GROWTH = 1.15
DELOAD_EVERY = 4
DELOAD_SHARE = 0.85
MIN_MAIN_THROWS = 20
MAX_THROWS_COMPRESSION = 45
MAX_THROWS_RECOVERY = 35
SIXTH_DAY_PROGRESS = 0.55
MAX_DAYS_OFF_HISTORY = 5
MAX_THROWS_LONG_TOSS = 70
# Day of plan week (slot 0 = start-date weekday) → (load share, default session)
WEEK_SHARES = [
    (0.12, "Recovery catch"),
    (0.27, "Big long-toss day"),
    (0.00, "Off"),
    (0.24, "Build day (long toss → compression + flat ground later)"),
    (0.10, "Recovery catch"),
    (0.27, "Long toss (+ flat ground later)"),
    (0.07, "Off early; light catch once progress passes the 6th-day threshold"),
]
MAX_PLAN_DAYS = 140
LOW_ACWR, HIGH_ACWR = 0.8, 1.3

DEFAULTS = dict(start=None, first_pen=None, pen_pitches=20, pen_velo_low=84, pen_velo_high=86,
                starting_point="Auto (from Throw Log)", max_distance=180, volume=1.0)


def _r(x):
    return m.excel_round(x)


def _i(x):
    """Pretty int for plan text."""
    return str(int(x)) if float(x).is_integer() else str(x)


def _intensity(deficit):
    return m.intensity_factor(max(deficit, 0))


def build(avg_velo, settings: dict, overrides: dict | None = None, daily_log: dict | None = None) -> dict:
    """
    avg_velo  — his Avg Top Velo (Roster)
    settings  — start, first_pen (dates), pen_pitches, pen_velo_low/high, starting_point, max_distance, volume
    overrides — {date: dict(off=bool, throws=int|None, distance=ft|None, velo_low=mph|None, velo_high=mph|None)}
    daily_log — {date: Throw Log workload} for this pitcher (drives Auto starting point + early ACWR)
    """
    s = {**DEFAULTS, **{k: v for k, v in settings.items() if v is not None}}
    ov = overrides or {}
    log = daily_log or {}
    D5, D6, D7 = avg_velo, s["start"], s["first_pen"]
    D8, D9, E9 = float(s["pen_pitches"]), float(s["pen_velo_low"]), float(s["pen_velo_high"])
    D10, D11, D12 = s["starting_point"], float(s["max_distance"]), float(s["volume"])
    out = dict(settings=s, days=[], weeks=[], summary={}, messages=[])
    if not D6 or not D7 or D5 in (None, 0) or (isinstance(D5, float) and math.isnan(D5)):
        out["messages"].append(("warn", "Pick a player who has an Avg Top Velo, and fill in the start and first-bullpen dates."
                                if D6 and D7 else "Fill in the start and first-bullpen dates."))
        return out
    D5 = float(D5)

    def logsum(a: date, b: date):
        return sum(v for d, v in log.items() if a <= d <= b)

    G4 = (D7 - D6).days
    G5 = math.ceil((G4 - 7) / 7 - 1e-12) if G4 > 7 else (G4 - 7) // 7
    before = [d for d, v in log.items() if d < D6 and v > 0]
    K5 = (D6 - max(before)).days if before else None
    week_loads = [logsum(D6 - timedelta(days=7 * k), D6 - timedelta(days=7 * (k - 1) + 1)) for k in (1, 2, 3, 4)]
    K10 = (week_loads[0] / 7) / (sum(week_loads) / 28) if sum(week_loads) else None
    G11 = logsum(D6 - timedelta(days=28), D6 - timedelta(days=1))
    K12 = 1 if (K5 is not None and K5 <= MAX_DAYS_OFF_HISTORY and G11 > 0) else 0
    G8 = PEAK_WEEKLY_LOAD * D12
    scratch = STARTING_POINTS["From scratch"]
    if K12:
        G6 = min(G8, G11 / 4)
    else:
        G6 = (scratch[0] if D10 == "Auto (from Throw Log)" else STARTING_POINTS[D10][0]) * D12
    if D10 == "Auto (from Throw Log)":
        G7 = min(0.55, max(0, (G6 - scratch[0] * D12) / max(1, G8 - scratch[0] * D12) * 0.55)) if K12 else 0
    else:
        G7 = STARTING_POINTS[D10][1]
    try:
        G9 = min(MAX_WEEKLY_GROWTH, max(1, (G8 / G6) ** (1 / max(1, G5 - 1))))
    except (ZeroDivisionError, ValueError):
        G9 = 1
    try:
        G10 = min(1, G6 * G9 ** (G5 - 1) / G8)
    except (ZeroDivisionError, OverflowError):
        G10 = 1
    plan_mode = "Continue from his load" if K12 else ("Restart (off too long)" if G11 > 0 else "Fresh start")

    n = min(G4, MAX_PLAN_DAYS)
    rows = []
    for L in range(0, n + 1):
        A = D6 + timedelta(days=L)
        o = ov.get(A, {}) or {}
        J_off = bool(o.get("off"))
        K = o.get("throws")
        AO, AP, AQ = o.get("distance"), o.get("velo_low"), o.get("velo_high")
        C = G4 - L
        M, N = L // 7 + 1, L % 7
        O = min(1, G7 + (1 - G7) * L / max(1, G4 - 8))
        R = _r((60 + (D11 - 60) * min(1, O / 0.75)) / 15) * 15
        S = _r((60 + (R - 60) * 0.8) / 15) * 15
        # base session
        if C == 0:
            T = "Bullpen"
        elif C in (7, 1, 5):
            T = "Recovery/Easy Catch"
        elif C == 6:
            T = "Compression/Pulldowns"
        elif C in (4, 2):
            T = "Long Toss"
        elif C == 3 or N == 2:
            T = "No Throw"
        elif N == 6:
            T = "No Throw" if O < SIXTH_DAY_PROGRESS else "Recovery/Easy Catch"
        elif N in (0, 4):
            T = "Recovery/Easy Catch"
        elif N == 1:
            T = "Long Toss" if R > 75 else "Recovery/Easy Catch"
        elif N == 3:
            T = ("Long Toss" if S > 75 else "Recovery/Easy Catch") if O < 0.5 else "Compression/Pulldowns"
        else:
            T = "Long Toss" if S > 75 else "Recovery/Easy Catch"
        # distance
        if AO:
            U = float(AO)
        elif C == 0 or C == 6:
            U = 90
        elif C in (7, 1):
            U = 75
        elif C == 5:
            U = 60
        elif C == 4:
            U = min(150, _r(0.75 * D11 / 15) * 15)
        elif C == 2:
            U = min(120, _r(0.67 * D11 / 15) * 15)
        elif C == 3 or N == 2:
            U = None
        elif N == 6:
            U = 60
        elif N == 0:
            U = 60 if O < 0.25 else 75
        elif N == 4:
            U = 60 if O < 0.5 else 75
        elif N == 1:
            U = R
        elif N == 3:
            U = S if O < 0.5 else 90
        else:
            U = S

        def deficits():
            if C == 0:
                return 10, 12
            if C in (7, 1):
                return 18, 22
            if C == 6:
                return 7, 9
            if C == 5:
                return 20, 24
            if C in (4, 2):
                return 10, 13
            if C == 3 or N == 2:
                return None, None
            if N == 6:
                return 20, 24
            if N == 0:
                return (20, 24) if O < 0.25 else (18, 22)
            if N == 4:
                return (20, 24) if O < 0.5 else (18, 22)
            if N == 1:
                return (18, 22) if O < 0.25 else ((13, 16) if O < 0.5 else (10, 12))
            if N == 3:
                return ((18, 22) if O < 0.25 else (13, 16)) if O < 0.5 else (7, 9)
            return (18, 22) if O < 0.25 else ((12, 15) if O < 0.5 else (10, 13))
        V, W = deficits()
        if AQ:
            V = D5 - float(AQ)
        elif AP:
            V = D5 - float(AP)
        if AP:
            W = D5 - float(AP)
        elif AQ:
            W = D5 - float(AQ)
        # 60' finish
        if C == 6:
            X = _r(25 * G10)
        elif C in (4, 2):
            X = _r(15 * G10)
        elif C <= 7:
            X = 0
        elif N == 1:
            X = 0 if O < 0.2 else (10 if O < 0.5 else 15)
        elif N == 3:
            X = (0 if O < 0.2 else 10) if O < 0.5 else (15 if O < 0.62 else (20 if O < 0.8 else 25))
        elif N == 5:
            X = 0 if O < 0.2 else (12 if O < 0.62 else (20 if O < 0.8 else 25))
        else:
            X = 0
        Y = Z = None
        if X:
            if C == 6:
                Y, Z = D5 - E9, D5 - D9
            elif C in (4, 2):
                Y, Z = 8, 10
            elif N == 1:
                Y, Z = (14, 18) if O < 0.5 else (10, 12)
            elif N == 3:
                Y, Z = (14, 18) if O < 0.5 else ((10, 12) if O < 0.62 else (7, 9))
            elif N == 5:
                Y, Z = (14, 18) if O < 0.5 else ((12, 15) if O < 0.62 else (7, 9))
        AL = m.lt_steps(T, U) if U is not None else 1
        AM = m.stepped_factor(U, AL) if U is not None else 0
        AN = m.interp_factor(U) if U is not None else 0
        AE = X * m.interp_factor(60) * _intensity((Y + Z) / 2) if X else 0
        AF = 0 if (U is None or T == "No Throw") else AM * _intensity((V + W) / 2)
        AC = D8 if C == 0 else 0
        AG = AC * m.MOUND_FACTOR["Bullpen"] * _intensity(D5 - (D9 + E9) / 2) if AC else 0
        if C == 0 or C == 6:
            AA = 25
        elif C in (7, 1, 5):
            AA = 30
        elif C in (4, 2):
            AA = 30 if AM == 0 else 30 * AN / AM
        else:
            AA = None
        AD = J_off or T == "No Throw"
        AK = 0 if (C <= 7 or T == "No Throw" or J_off) else WEEK_SHARES[N][0]
        rows.append(dict(L=L, date=A, C=C, M=M, N=N, O=O, T=T, U=U, V=V, W=W, X=X, Y=Y, Z=Z, AA=AA, AC=AC, AD=AD,
                         AE=AE, AF=AF, AG=AG, AK=AK, AL=AL, AM=AM, K=K, off=J_off,
                         ov_distance=AO, ov_velo_low=AP, ov_velo_high=AQ))

    # week targets need the whole week's active shares
    for r in rows:
        L, C, M, N = r["L"], r["C"], r["M"], r["N"]
        if C <= 7:
            P = None
        else:
            P = G6 * G9 ** (M - 1) * (DELOAD_SHARE if (M % DELOAD_EVERY == 0 and M <= G5 - 2) else 1)
        if P is None:
            Q = None
        else:
            wk = [x["AK"] for x in rows if 7 * (M - 1) <= x["L"] <= 7 * (M - 1) + 6]
            Q = 0 if sum(wk) == 0 else P * WEEK_SHARES[N][0] / sum(wk)
        T = r["T"]
        if T == "No Throw":
            AB = 0
        elif r["K"] not in (None, ""):
            AB = float(r["K"])
        elif r["AA"] is not None:
            AB = _r(r["AA"] * D12 * (1 if C == 0 else G10))
        else:
            cap = MAX_THROWS_RECOVERY if T == "Recovery/Easy Catch" else (MAX_THROWS_LONG_TOSS if T == "Long Toss" else MAX_THROWS_COMPRESSION)
            AB = min(cap, max(MIN_MAIN_THROWS, _r(max(0, (Q or 0) - r["AE"]) / r["AF"]) if r["AF"] else MIN_MAIN_THROWS))
        H = 0 if r["AD"] else AB * r["AF"] + r["AE"] + r["AG"]
        O = r["O"]
        if r["AD"]:
            E = "No Throw"
        elif C == 0:
            E = "High Bullpen"
        elif C == 6:
            E = "High Non-Bullpen"
        elif C in (4, 2):
            E = "Medium"
        elif T == "Recovery/Easy Catch":
            E = "Low"
        elif N == 1:
            E = "Low" if O < 0.4 else ("Medium" if O < 0.7 else "High Non-Bullpen")
        elif N == 3:
            E = "Medium" if O < 0.5 else "High Non-Bullpen"
        else:
            E = "Medium" if O < 0.62 else "High Non-Bullpen"
        if C == 0:
            phase = "First Bullpen"
        elif C <= 7:
            phase = "Taper"
        elif O < 0.2:
            phase = "Re-entry"
        elif O < 0.45:
            phase = "Base"
        elif O < 0.65:
            phase = "Extension"
        else:
            phase = "Flat Ground / Intent"
        if r["AD"]:
            G = "Off"
        else:
            U = r["U"]
            if r["AL"] > 1:
                G = f"Long toss out to {_i(U)} ft — {_i(AB)} throws ({m.step_split(U, AB, r['AL'])})"
            else:
                G = f"{_i(U)} ft × {_i(AB)}"
            G += f" @ {_i(_r(D5 - r['W']))}–{_i(_r(D5 - r['V']))} mph"
            if r["X"]:
                G += (" + flat ground at 60 ft × " if r["Y"] < 10 else " + 60 ft × ") + \
                     f"{_i(r['X'])} @ {_i(_r(D5 - r['Z']))}–{_i(_r(D5 - r['Y']))} mph"
            if r["AC"]:
                G += f" + MOUND × {_i(r['AC'])} pitches @ {_i(D9)}–{_i(E9)} mph"
        r.update(P=P, Q=Q, AB=AB, H=H, E=E, phase=phase, plan=G)

    # ACWR column
    for r in rows:
        L = r["L"]
        if L < 27 and K12 == 0:
            r["acwr"] = None
            r["acwr_txt"] = "Building"
            continue
        acute = sum(x["H"] for x in rows[max(0, L - 6):L + 1])
        chronic = sum(x["H"] for x in rows[max(0, L - 27):L + 1])
        if K12:
            if L < 6:
                acute += logsum(D6 + timedelta(days=L - 6), D6 - timedelta(days=1))
            if L < 27:
                chronic += logsum(D6 + timedelta(days=L - 27), D6 - timedelta(days=1))
        r["acwr"] = (acute / 7) / (chronic / 28) if chronic else None
        r["acwr_txt"] = "" if r["acwr"] is None else f"{r['acwr']:.2f}"

    days = [dict(date=r["date"], day=r["date"].strftime("%a"), days_to_pen=r["C"], phase=r["phase"], day_type=r["E"],
                 session=("No Throw" if r["AD"] else r["T"]), plan=r["plan"], workload=r["H"], acwr=r["acwr"],
                 acwr_txt=r["acwr_txt"], off=r["off"], throws_override=r["K"], distance_override=r["ov_distance"],
                 velo_low_override=r["ov_velo_low"], velo_high_override=r["ov_velo_high"], week=r["M"],
                 distance=r["U"], throws=r["AB"], target=r["Q"]) for r in rows]
    weeks, prev = [], None
    for b in range(1, 22):
        start = D6 + timedelta(days=7 * (b - 1))
        if start > D7:
            break
        wk = [d for d in days if d["week"] == b]
        load = sum(d["workload"] for d in wk)
        idx = min(7 * b, G4 + 1) - 1
        a = days[idx]["acwr"] if 0 <= idx < len(days) else None
        weeks.append(dict(week_of=start, week=b, throw_days=sum(1 for d in wk if d["workload"] > 0), workload=load,
                          change=(load / prev - 1) if prev else None, acwr_end=a,
                          acwr_end_txt=days[idx]["acwr_txt"] if 0 <= idx < len(days) else ""))
        prev = load

    numeric = [d["acwr"] for d in days if d["acwr"] is not None]
    min_window = (AUTO_MIN_WINDOW_ACTIVE if K12 else AUTO_MIN_WINDOW_RESTART) if D10 == "Auto (from Throw Log)" else STARTING_POINTS[D10][2]
    first_pen_acwr = days[G4]["acwr"] if G4 < len(days) else None
    out["summary"] = dict(window=G4, build_weeks=G5, start_load=G6, start_progress=G7, peak_load=G8, growth=G9,
                          taper_scale=G10, logged_28=G11, first_pen_acwr=first_pen_acwr,
                          max_acwr=max(numeric) if numeric else None, days_since_last=K5,
                          week_loads=week_loads, acwr_going_in=K10, plan_mode=plan_mode, history_counts=bool(K12),
                          min_window=min_window)
    above = sum(1 for a in numeric if a > HIGH_ACWR)
    below = sum(1 for a in numeric if a < LOW_ACWR)
    if G4 < min_window:
        out["messages"].append(("warn", f"⚠ {G4} days is shorter than the recommended {min_window} days for this starting point — "
                                         "expect ACWR spikes. Push the first pen back or change the Starting Point."))
    elif G4 > MAX_PLAN_DAYS:
        out["messages"].append(("warn", "⚠ The plan covers 140 days max — move the start date later."))
    elif above:
        out["messages"].append(("warn", f"⚠ {above} day(s) above 1.3 — see the ACWR column; use Make Off / Throws Override to smooth it out."))
    elif below:
        out["messages"].append(("ok", f"✓ No spikes above 1.3. {below} day(s) read below 0.8 — that's him stepping down from a heavier recent load, not a risk."))
    else:
        out["messages"].append(("ok", "✓ Every readable day sits in the 0.8–1.3 sweet spot, including the first pen."))
    gap_hi, gap_lo = D5 - E9, D5 - D9
    out["messages"].append(("info", f"First pen at {_i(D9)}–{_i(E9)} mph = {_i(_r(gap_hi))}–{_i(_r(gap_lo))} mph below his avg"
                                    + (" — the top end is in his max-effort band; consider lowering the pen velo for him." if gap_hi < 4 else ".")))
    if K12:
        out["messages"].append(("info", f"ℹ Built off his Throw Log: starts at his average week over the last 28 days ({_i(_r(G11 / 4))}/week)"
                                        + (" — capped at this plan's peak, a planned cut-back" if G11 / 4 > G8 else "")
                                        + ", and that history counts toward his ACWR from day 1."))
    elif G11 > 0:
        out["messages"].append(("info", f"ℹ He's been off {K5} days, more than the {MAX_DAYS_OFF_HISTORY} his history can cover — his old workload "
                                        "will expire out of the 28-day window, so the plan treats this as a restart and the ACWR reads from day 28."))
    else:
        out["messages"].append(("info", "ℹ No throwing logged for him in the 28 days before the start date — fresh start, ACWR reads from day 28."))
    out["days"], out["weeks"] = days, weeks
    return out
