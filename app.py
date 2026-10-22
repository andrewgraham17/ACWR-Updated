"""
K-State Baseball — Throw Log (Streamlit)
Run in VS Code:  press ▶ on run.py   — or —   streamlit run app.py
Everything saves automatically the moment it's entered.
Data is stored in Postgres when DATABASE_URL is set (see README), otherwise in data/throwing.db.
"""
from __future__ import annotations

import io
from functools import partial
import os
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import streamlit as st

import buildup as bu
import model as m
import storage as db

HERE = os.path.dirname(os.path.abspath(__file__))
PURPLE, DARK_GRAY, LIGHT_GRAY = "#330a57", "#a7a9ac", "#e2e3e4"
TAB_KEY = "player_tab"

st.set_page_config(page_title="K-State Throw Log", page_icon="⚾", layout="wide")
st.markdown(f"""<style>
.block-container {{ padding-top: 3.6rem; max-width: 1240px; }}
h1, h2, h3 {{ color: {PURPLE}; }}
div[data-testid="stMetric"] {{ background: rgba(51,10,87,.05); border-radius: 6px; padding: .5rem .9rem; }}
.jersey {{ background:{PURPLE}; color:#fff; font-weight:800; font-size:2.3rem; line-height:1; border-radius:6px;
  min-width:64px; height:64px; display:flex; align-items:center; justify-content:center; padding:0 8px; }}
.pname {{ font-size:1.9rem !important; font-weight:800; color:{PURPLE}; line-height:1.1; margin:0 0 .15rem 0; }}
.pmeta {{ color:#666; }}
.pill {{ display:inline-block; padding:3px 11px; border-radius:999px; font-weight:700; font-size:.85rem; white-space:nowrap; }}
.zone {{ padding:.65rem 1rem; border-radius:8px; margin:.2rem 0 .6rem 0; }}
.zone b {{ display:block; }}
.z-Undertrained {{ background:#e6eefb; color:#1d4f91; }} .z-Sweet {{ background:#e4f3e8; color:#1b6632; }}
.z-Caution {{ background:#fff2d1; color:#7d5300; }} .z-High {{ background:#fde6e6; color:#a3191c; }}
.z-Insufficient, .z-none {{ background:#eceaef; color:#3d3845; }}
.bu-warn {{ background:#fff2d1; color:#7d5300; padding:.6rem 1rem; border-radius:8px; margin:.2rem 0 .4rem 0; }}
.bu-ok {{ background:#e4f3e8; color:#1b6632; padding:.6rem 1rem; border-radius:8px; margin:.2rem 0 .4rem 0; }}
.bu-info {{ background:rgba(51,10,87,.05); color:#3d3845; padding:.5rem 1rem; border-radius:8px; margin:.2rem 0 .4rem 0; font-size:.92rem; }}
.plan {{ background:rgba(51,10,87,.06); border-radius:8px; padding:.6rem .9rem; margin-bottom:.45rem; }}
.saved {{ color:#1b6632; font-weight:700; font-size:.85rem; }}
.preview {{ background:rgba(51,10,87,.07); border-radius:8px; padding:.7rem 1rem; display:flex; gap:1.6rem; flex-wrap:wrap; align-items:baseline; }}
.preview .k {{ display:block; font-size:.72rem; text-transform:uppercase; letter-spacing:.07em; color:#666; }}
.preview .big {{ font-size:2rem; font-weight:800; color:{PURPLE}; line-height:1; }}
button[data-baseweb="tab"] p {{ font-size:.95rem; }}
</style>""", unsafe_allow_html=True)


# ───────────────────────── helpers ─────────────────────────
def chicago_today() -> date:
    return datetime.now(ZoneInfo("America/Chicago")).date()


def fmt(x, d=1, dash="—"):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return dash
    return f"{x:,.{d}f}"


def none_if_nan(v):
    return None if v is None or (isinstance(v, float) and pd.isna(v)) else v


def zkey(zone):
    return (zone or "none").split()[0]


def zshort(zone):
    return (zone or "").split(" (")[0].replace("Insufficient history", "Building history")


def pill(zone):
    return f'<span class="pill z-{zkey(zone)}">● {zshort(zone)}</span>'


def zone_box(zone, guidance):
    return f'<div class="zone z-{zkey(zone)}"><b>Zone: {zone}</b>{guidance}</div>'


def toast(msg):
    st.session_state.setdefault("_toasts", []).append(msg)


def bump(k):
    st.session_state[k] = st.session_state.get(k, 0) + 1


def stamp():
    return datetime.now().strftime("%-I:%M:%S %p") if os.name != "nt" else datetime.now().strftime("%I:%M:%S %p")


def calc_log(pid, avg):
    df = db.load_log(pid)
    calc = pd.DataFrame(m.calc_rows(df.to_dict("records"), avg), columns=list(m.calc_row({}, None).keys()))
    out = pd.concat([df.reset_index(drop=True), calc], axis=1)
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.date
    return out


def daily_of(pid, avg):
    return m.daily_totals(calc_log(pid, avg))


def tab_label(p):
    return f"{p['number']}  {p['name']}" if p.get("number") not in (None, "") else p["name"]


def to_time(s):
    if not s or (isinstance(s, float) and pd.isna(s)):
        return None
    h, mi = map(int, str(s)[:5].split(":"))
    return time(h, mi)


def time_txt(s):
    t = to_time(s)
    return t.strftime("%I:%M %p").lstrip("0") if t else ""


# ───────────────────────── first run ─────────────────────────
if db.is_empty():
    with st.spinner("Setting up the database with the staff's data (first run only, about 30 seconds)…"):
        db.seed_if_empty(os.path.join(HERE, "data", "ACWR Throwing Plan Fall 2026.xlsx"),
                         os.path.join(HERE, "data", "throw_log_backup_2026-10-22.xlsx"))

for msg in st.session_state.pop("_toasts", []):
    st.toast(msg, icon="✅")

players = db.load_players()

# ───────────────────────── sidebar ─────────────────────────
with st.sidebar:
    if os.path.exists(os.path.join(HERE, "assets", "baseball-wordmark.png")):
        st.image(os.path.join(HERE, "assets", "baseball-wordmark.png"), width="stretch")
    st.markdown("### Throw Log · Fall 2026")
    today = st.date_input("Today's date", value=chicago_today(), key="today", format="MM/DD/YYYY")
    st.caption(f"Everything you enter saves automatically. Saved in: {db.where_saved()}.")
    st.divider()
    with st.expander("Import / backup"):
        up = st.file_uploader("Restore an Excel backup from this app", type=["xlsx"], key="up_backup",
                              help="Replaces each player's throw log with the one in the backup, and loads roster velo and Build-Up plans.")
        if up is not None and st.button("Restore backup", type="primary"):
            n_p, n_r = db.import_backup(io.BytesIO(up.getvalue()))
            toast(f"Restored {n_p} players and {n_r} throw-log rows")
            st.rerun()
        upw = st.file_uploader("Import the ACWR Excel workbook", type=["xlsx"], key="up_wb",
                               help="Loads Roster velo and every Build-Up tab. Tick the box to also replace throw logs with the workbook's Throw Log tab.")
        with_log = st.checkbox("Also import the workbook's Throw Log tab", value=False, key="wb_log")
        if upw is not None and st.button("Import workbook"):
            n_p, n_r, n_b = db.import_workbook(io.BytesIO(upw.getvalue()), include_log=with_log)
            toast(f"Imported velo for {n_p} players, {n_r} throw-log rows and {n_b} Build-Up plans")
            st.rerun()
        if st.button("Prepare Excel backup"):
            frames = []
            for p in players.to_dict("records"):
                lg = calc_log(p["id"], none_if_nan(p["avg_top_velo"])).drop(columns=["id", "created"])
                lg.insert(0, "player", p["name"])
                frames.append(lg)
            st.session_state["_backup"] = db.export_backup(players, frames)
        if st.session_state.get("_backup"):
            st.download_button("Download backup (.xlsx)", st.session_state["_backup"],
                               file_name=f"throw_log_backup_{today.isoformat()}.xlsx", width="stretch")
    st.caption("Set Workload = Throws × Distance/Mound Factor × Intensity Factor. ACWR = 7-day avg ÷ 28-day avg. "
               "Coaching decision-support tool, not a medical instrument.")


# ═════════════════════════ THROW LOG ═════════════════════════
def ek(rid, f):
    return f"ed_{rid}_{f}"


EDIT_FIELDS = ["date", "session_type", "distance", "start_time", "end_time", "actual_throws", "velo_low", "velo_high",
               "warm_throws", "warm_velo_low", "warm_velo_high", "sixty_throws", "sixty_velo_low", "sixty_velo_high", "notes"]


def read_editor(rid, base: dict) -> dict:
    """Current editor values (only the widgets on screen) merged over the saved row."""
    rec = dict(base)
    for f in EDIT_FIELDS:
        k = ek(rid, f)
        if k in st.session_state:
            rec[f] = st.session_state[k]
    if st.session_state.get(ek(rid, "mode")) == "Time it":
        rec["actual_throws"] = None
    if rec.get("session_type") in m.MOUND_TYPES:
        rec["distance"] = None
    return rec


def save_editor(pid, rid):
    base = db.get_row(rid)
    if not base:
        return
    rec = read_editor(rid, base)
    db.update_row(rid, {f: rec.get(f) for f in EDIT_FIELDS})
    st.session_state[f"saved_{rid}"] = f"✓ Saved {stamp()}"


def new_session(pid, copy_from=None):
    rec = dict(copy_from or {"session_type": "Long Toss"})
    rec["date"] = st.session_state.get("today") or chicago_today()
    rec.pop("created", None)
    rid = db.add_row(pid, rec)
    st.session_state[f"edit_{pid}"] = rid
    st.session_state[f"saved_{rid}"] = "✓ New session created — fill it in, it saves as you go"
    st.session_state.pop(f"del_{pid}", None)


def close_editor(pid):
    st.session_state.pop(f"edit_{pid}", None)
    st.session_state.pop(f"del_{pid}", None)
    bump(f"logsel_{pid}")


def delete_session(pid, rid):
    db.delete_row(rid)
    close_editor(pid)
    toast("Session deleted")


def pick_row(pid, key, ids):
    rows = st.session_state[key].selection.rows
    if rows:
        st.session_state[f"edit_{pid}"] = ids[rows[0]]
        st.session_state.pop(f"del_{pid}", None)


def editor(p, avg):
    pid, rid = p["id"], st.session_state.get(f"edit_{p['id']}")
    r = db.get_row(rid) if rid else None
    if not r:
        return
    cb = dict(on_change=save_editor, args=(pid, rid))
    mound = r["session_type"] in m.MOUND_TYPES
    with st.container(border=True):
        h = st.columns([3, 2, 1, 1, 1], vertical_alignment="center")
        d = date.fromisoformat(r["date"]) if r.get("date") else None
        h[0].markdown(f"#### {d.strftime('%A, %b %-d') if d and os.name != 'nt' else (d.strftime('%A, %b %d') if d else 'New session')}")
        h[1].markdown(f"<span class='saved'>{st.session_state.get(f'saved_{rid}', '')}</span>", unsafe_allow_html=True)
        h[2].button("Copy as new", key=f"copy_{rid}", on_click=new_session, args=(pid, r), width="stretch")
        if st.session_state.get(f"del_{pid}"):
            h[3].button("Delete it", key=f"dely_{rid}", type="primary", on_click=delete_session, args=(pid, rid), width="stretch")
            h[4].button("Keep", key=f"deln_{rid}", on_click=lambda: st.session_state.pop(f"del_{pid}", None), width="stretch")
        else:
            h[3].button("Delete", key=f"del_{rid}", on_click=lambda: st.session_state.update({f"del_{pid}": True}), width="stretch")
            h[4].button("Done", key=f"done_{rid}", type="primary", on_click=close_editor, args=(pid,), width="stretch")

        c = st.columns([1.2, 1.6, 1.2, 2])
        c[0].date_input("Date", value=d, key=ek(rid, "date"), format="MM/DD/YYYY", **cb)
        c[1].selectbox("Session type", m.SESSION_TYPES, index=m.SESSION_TYPES.index(r["session_type"]) if r["session_type"] in m.SESSION_TYPES else 1,
                       key=ek(rid, "session_type"), **cb)
        stype = st.session_state.get(ek(rid, "session_type"), r["session_type"])
        mound, rest = stype in m.MOUND_TYPES, stype == "No Throw"
        if not rest:
            if mound:
                c[2].text_input("Distance", "Mound (60′6″)", disabled=True, key=ek(rid, "mound_note"),
                                help="Bullpen/Game use the flat Mound Factor instead of distance")
            else:
                c[2].number_input("Distance (ft)" + (" — farthest" if stype == "Long Toss" else ""), 0, 400,
                                  none_if_nan(r["distance"]) and int(r["distance"]), 5,
                                  key=ek(rid, "distance"), placeholder="e.g. 120", **cb,
                                  help="Long toss: the farthest he got. It's scored as the standard step-out "
                                       "(90, 120, 150 … every 30 ft), with more throws at the short steps.")
            default_mode = "Exact count" if (none_if_nan(r["actual_throws"]) is not None or (mound and not r["start_time"])) else "Time it"
            c[3].segmented_control("Throw count", ["Time it", "Exact count"], default=default_mode, required=True,
                                   key=ek(rid, "mode"), on_change=save_editor, args=(pid, rid),
                                   help="Time a group session (throws estimated from pace) or type the exact count")
            mode = st.session_state.get(ek(rid, "mode"), default_mode)
            c2 = st.columns(4)
            if mode == "Time it":
                c2[0].time_input("Start", value=to_time(r["start_time"]), key=ek(rid, "start_time"), step=60, **cb)
                c2[1].time_input("End", value=to_time(r["end_time"]), key=ek(rid, "end_time"), step=60, **cb)
            else:
                c2[0].number_input("Throws (live + in-game WU)" if stype == "Game" else "Actual throws", 0, 400,
                                   none_if_nan(r["actual_throws"]) and int(r["actual_throws"]), 1,
                                   key=ek(rid, "actual_throws"), placeholder="e.g. 25", **cb)
            c2[2].number_input("Velo low (mph)", 0.0, 110.0, none_if_nan(r["velo_low"]), 1.0, format="%.1f", key=ek(rid, "velo_low"), placeholder="e.g. 75", **cb)
            c2[3].number_input("Velo high (mph)", 0.0, 110.0, none_if_nan(r["velo_high"]), 1.0, format="%.1f", key=ek(rid, "velo_high"), placeholder="e.g. 81", **cb)
            e1, e2 = st.columns(2)
            with e1.expander("Pen warm-up before entering (game days)", expanded=stype == "Game" or none_if_nan(r["warm_throws"]) is not None):
                st.caption("Scored at the Bullpen Mound Factor.")
                w = st.columns(3)
                w[0].number_input("Throws", 0, 200, none_if_nan(r["warm_throws"]) and int(r["warm_throws"]), 1, key=ek(rid, "warm_throws"), **cb)
                w[1].number_input("Velo low", 0.0, 110.0, none_if_nan(r["warm_velo_low"]), 1.0, format="%.1f", key=ek(rid, "warm_velo_low"), **cb)
                w[2].number_input("Velo high", 0.0, 110.0, none_if_nan(r["warm_velo_high"]), 1.0, format="%.1f", key=ek(rid, "warm_velo_high"), **cb)
            with e2.expander("Finished working back in at 60′", expanded=none_if_nan(r["sixty_throws"]) is not None):
                st.caption("Same entry, scored at the 60 ft Distance Factor.")
                w = st.columns(3)
                w[0].number_input("Throws", 0, 200, none_if_nan(r["sixty_throws"]) and int(r["sixty_throws"]), 1, key=ek(rid, "sixty_throws"), **cb)
                w[1].number_input("Velo low", 0.0, 110.0, none_if_nan(r["sixty_velo_low"]), 1.0, format="%.1f", key=ek(rid, "sixty_velo_low"), **cb)
                w[2].number_input("Velo high", 0.0, 110.0, none_if_nan(r["sixty_velo_high"]), 1.0, format="%.1f", key=ek(rid, "sixty_velo_high"), **cb)
        else:
            st.caption("Rest day. It's saved so the day counts as zero in your log.")
        st.text_input("Notes (arm feel, RPE, etc.)", value=r["notes"] or "", key=ek(rid, "notes"), **cb)

        cur = read_editor(rid, r)
        if rest:
            st.markdown("<div class='preview'>Rest day: workload 0</div>", unsafe_allow_html=True)
        else:
            others = calc_log(pid, avg)
            outing_days = {d for d, st_, w, i in zip(others["date"], others["session_type"], others["workload_before_b2b"], others["id"])
                           if st_ in m.MOUND_TYPES and i != rid and not pd.isna(w) and w > 0}
            cur_day = cur.get("date") if isinstance(cur.get("date"), date) else (date.fromisoformat(cur["date"]) if cur.get("date") else None)
            cc = m.calc_row(cur, avg, m.b2b_multiplier(cur_day, cur.get("session_type"), outing_days))
            est = f" <span style='color:#666'>({fmt(cc['duration_min'], 0)} min)</span>" if cc["duration_min"] is not None and cur.get("actual_throws") is None else ""
            off = f" <span style='color:#666'>({fmt(cc['velo_deficit'])} mph off)</span>" if cc["velo_deficit"] is not None else ""
            steps = ""
            if cc["lt_steps"] > 1 and cc["throws_used"] is not None:
                steps = (f"<div style='flex-basis:100%;color:#666;font-size:.85rem'>Long-toss step-out: "
                         f"{m.step_split(cur.get('distance'), cc['throws_used'], cc['lt_steps'])}</div>")
            b2b = ""
            if (cc["b2b_multiplier"] or 1) > 1:
                b2b = (f"<div><span class='k'>Back-to-back</span><b style='color:#a3191c'>×{cc['b2b_multiplier']:g}</b> "
                       f"<span style='color:#666'>({fmt(cc['workload_before_b2b'])} before)</span></div>")
            hint = "" if cc["set_workload"] is not None else "<div style='flex-basis:100%;color:#666;font-size:.85rem'>Add throws (or start + end time) and velo to see the workload.</div>"
            st.markdown(f"""<div class='preview'>
              <div><span class='k'>Set Workload</span><span class='big'>{fmt(cc['set_workload'])}</span></div>
              <div><span class='k'>Throws</span><b>{fmt(cc['throws_used'], 0)}</b>{est}</div>
              <div><span class='k'>{'Mound' if mound else 'Distance'} factor</span><b>{fmt(cc['dist_mound_factor'], 2)}</b></div>
              <div><span class='k'>Intensity factor</span><b>{fmt(cc['intensity_factor'], 2)}</b>{off}</div>{b2b}{steps}{hint}</div>""", unsafe_allow_html=True)


def throw_log_tab(p, avg):
    pid = p["id"]
    a, b = st.columns([1, 3], vertical_alignment="center")
    a.button("＋ Log a session", type="primary", on_click=new_session, args=(pid,), key=f"new_{pid}", width="stretch")
    b.caption("Everything saves automatically as you type: press Enter or click out of a box.")
    editor(p, avg)

    st.markdown("### My throw log")
    log = calc_log(pid, avg)
    if log.empty:
        st.info("No sessions logged yet. Tap **＋ Log a session** after you throw. Your workload, ACWR and plan fill in from here.")
    else:
        view = pd.DataFrame({
            "Date": log["date"], "Session Type": log["session_type"], "Set Workload": log["set_workload"],
            "Distance": [("Mound" if s in m.MOUND_TYPES else ("" if pd.isna(d) else f"{d:.0f}" + (f" · {n} steps" if n > 1 else "")))
                         for s, d, n in zip(log["session_type"], log["distance"], log["lt_steps"])],
            "Start": log["start_time"].map(time_txt), "End": log["end_time"].map(time_txt), "Throws Used": log["throws_used"],
            "Velo": [("" if pd.isna(lo) else f"{lo:g}" + ("" if pd.isna(hi) else f"–{hi:g}")) for lo, hi in zip(log["velo_low"], log["velo_high"])],
            "Deficit": log["velo_deficit"], "Dist/Mound F.": log["dist_mound_factor"], "Intensity F.": log["intensity_factor"],
            "Pen WU": log["warm_throws"], "60′": log["sixty_throws"],
            "B2B ×": [("" if pd.isna(x) or x == 1 else f"×{x:g}") for x in log["b2b_multiplier"]], "Notes": log["notes"].fillna("")})
        ids = list(log["id"])
        key = f"logtable_{pid}_{st.session_state.get(f'logsel_{pid}', 0)}"
        st.dataframe(view, hide_index=True, width="stretch", height=min(520, 38 + 35 * len(view)),
                     on_select=partial(pick_row, pid, key, ids), selection_mode="single-row", key=key,
                     column_config={"Date": st.column_config.DateColumn(format="ddd MM/DD/YY"),
                                    "Set Workload": st.column_config.NumberColumn(format="%.1f"),
                                    "Throws Used": st.column_config.NumberColumn(format="%.0f"),
                                    "Deficit": st.column_config.NumberColumn(format="%.1f"),
                                    "Dist/Mound F.": st.column_config.NumberColumn(format="%.2f"),
                                    "Intensity F.": st.column_config.NumberColumn(format="%.1f"),
                                    "Pen WU": st.column_config.NumberColumn(format="%.0f"),
                                    "B2B ×": st.column_config.TextColumn(help="Back-to-back mound day: ×1.5 the day after an outing, ×1.25 with one day between"),
                                    "60′": st.column_config.NumberColumn(format="%.0f"),
                                    "Notes": st.column_config.TextColumn(width="large")})
        st.caption("Click a row (the box at its left edge) to edit it.")
    with st.expander("How to log (long toss, game days, 60′ finish)"):
        st.markdown("""
- **Long toss = one entry.** Distance = the farthest he got, throws = the total for the whole step-out. It's scored as the standard step-out (90, 120, 150 … every 30 ft up to that distance, more throws at the short steps).
- **Distance factor is smooth:** in-between distances fall on a straight line (75 ft = 1.15, 105 ft = 1.5, 135 ft = 1.95, 165 ft = 2.5).
- **Time it or count it.** Start/End time estimates throws from pace (Long Toss 3.5/min, Compression 3/min, Bullpen 2.5/min, Moderate 4/min, Recovery 5.5/min). An exact count always overrides.
- **Bullpen / Game:** no distance. A flat Mound Factor is used (Bullpen 3.0, Game 3.2). Enter the exact pitch count.
- **Back-to-back outings:** a Bullpen/Game day right after another outing is multiplied ×1.5 (×1.25 with one day in between). It shows in the *B2B ×* column.
- **Game day = one entry.** Throws = live pitches + in-game warm-ups (8 entering, +5 for each extra inning). Pen warm-ups before entering go in the *Pen warm-up* section.
- **Finished working back in at 60′?** Use the 60′ section on the same entry.
- **Velo:** enter a range, e.g. 70–74. The midpoint is compared to your Avg Top Velo to set intensity.""")


# ═════════════════════════ DASHBOARD ═════════════════════════
def dashboard_tab(p, avg, daily):
    as_of = st.date_input("As of date", value=today, key=f"asof_{p['id']}", format="MM/DD/YYYY")
    s = m.status(daily, as_of)
    c = st.columns(5)
    c[0].metric("Today's workload", fmt(s["today"]))
    c[1].metric("Acute · 7-day avg/day", fmt(s["acute"]))
    c[2].metric("Chronic · 28-day avg/day", fmt(s["chronic"]))
    c[3].metric("ACWR · acute ÷ chronic", fmt(s["acwr"], 2, "N/A"))
    c[4].metric("Spike · today ÷ chronic", fmt(s["spike"], 2, "N/A"))
    st.markdown(zone_box(s["zone"], s["guidance"]), unsafe_allow_html=True)
    if s["spike_flag"]:
        st.markdown(f"<div class='zone z-{'Sweet' if s['spike_flag'] == 'OK' else 'High'}'><b>Spike flag: {s['spike_flag']}</b></div>",
                    unsafe_allow_html=True)
    st.markdown("### 28-day trend")
    days = [as_of - timedelta(days=27 - i) for i in range(28)]
    trend = pd.DataFrame({"Day": [d.strftime("%m/%d") for d in days], "Weekday": [d.strftime("%a") for d in days],
                          "Daily Workload": [daily.get(d, 0.0) for d in days]})
    bars = alt.Chart(trend).mark_bar(color=DARK_GRAY, cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
        x=alt.X("Day:O", title=None, sort=None, axis=alt.Axis(labelAngle=-45)),
        y=alt.Y("Daily Workload:Q", title="Daily workload"),
        tooltip=["Weekday", "Day", alt.Tooltip("Daily Workload:Q", format=".1f")])
    lines = pd.DataFrame({"Line": [f"Acute (7d avg) {s['acute']:.1f}", f"Chronic (28d avg) {s['chronic']:.1f}"], "v": [s["acute"], s["chronic"]]})
    rules = alt.Chart(lines).mark_rule(strokeWidth=2.5).encode(
        y="v:Q", color=alt.Color("Line:N", scale=alt.Scale(range=[PURPLE, "#555555"]), legend=alt.Legend(title=None, orient="top")),
        strokeDash=alt.StrokeDash("Line:N", scale=alt.Scale(range=[[1, 0], [7, 5]]), legend=None))
    st.altair_chart((bars + rules).properties(height=300), width="stretch")

    st.markdown("### Weekly workload · last 12 weeks")
    wk = pd.DataFrame(m.weekly_table(daily, as_of))
    wk["Label"] = [f"{a:%m/%d}–{b:%m/%d}" for a, b in zip(wk["week_of"], wk["week_ending"])]
    wchart = alt.Chart(wk).mark_bar(color=PURPLE, cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
        x=alt.X("Label:O", title="7-day weeks ending on the As Of date", sort=None, axis=alt.Axis(labelAngle=-30)),
        y=alt.Y("workload:Q", title="Weekly workload"),
        tooltip=[alt.Tooltip("Label:N", title="Week"), alt.Tooltip("workload:Q", title="Workload", format=".1f"),
                 alt.Tooltip("throwing_days:Q", title="Throwing days"), alt.Tooltip("change:Q", title="vs prior week", format="+.0%")])
    st.altair_chart(wchart.properties(height=260), width="stretch")
    st.dataframe(pd.DataFrame({"Week of": wk["week_of"], "Week ending": wk["week_ending"], "Weekly workload": wk["workload"],
                               "Throwing days": wk["throwing_days"], "Change vs prior week": wk["change"]}),
                 hide_index=True, width="stretch",
                 column_config={"Week of": st.column_config.DateColumn(format="ddd MM/DD"),
                                "Week ending": st.column_config.DateColumn(format="ddd MM/DD"),
                                "Weekly workload": st.column_config.NumberColumn(format="%.1f"),
                                "Change vs prior week": st.column_config.NumberColumn(format="percent")})


# ═════════════════════════ DAY TYPE TEMPLATES ═════════════════════════
def templates_tab(p, avg):
    st.caption(f"Velo targets shown for **{p['name']}**" + (f" (Avg Top Velo {fmt(avg)} mph)." if avg else " (set your Avg Top Velo to see mph targets).") +
               " Workloads come from distance and mph-deficit bands, so they're the same for every pitcher. Low, Medium and High "
               "Non-Bullpen days finish at 60 ft working all pitches; High Bullpen and Game days skip that finish.")
    rows = m.template_rows(avg or 0)
    plans = {}
    for r in rows:
        plans.setdefault((r["category"], r["example"]), []).append(m.segment_text(r, avg))
    summ = m.template_summary(avg)
    st.markdown("### Day type quick reference")
    st.dataframe(pd.DataFrame([{"Day Type": s["day_type"], "Avg Projected Workload": s["avg"],
                                "Example 1": "  +  ".join(plans[(s["day_type"], 1)]), "Ex 1": s["ex1"],
                                "Example 2": "  +  ".join(plans[(s["day_type"], 2)]), "Ex 2": s["ex2"]} for s in summ]),
                 hide_index=True, width="stretch",
                 column_config={k: st.column_config.NumberColumn(format="%.1f") for k in ("Avg Projected Workload", "Ex 1", "Ex 2")}
                 | {"Example 1": st.column_config.TextColumn(width="large"), "Example 2": st.column_config.TextColumn(width="large")})
    st.caption("Long toss past 90 ft is a step-out: the distance is the farthest step and the throws are the total for all steps. "
               "The split is shown in the plan (e.g. 90×30 · 120×23), and its Distance Factor is the throw-weighted average of the steps.")
    st.markdown("### Segment detail")
    det = pd.DataFrame([{"Category": r["category"], "Ex": r["example"], "Seg": r["segment"], "Segment Type": r["segment_type"],
                         "Distance": "Mound" if r["distance"] is None else f"{r['distance']} ft",
                         "Throws": f"{r['throws_low']}–{r['throws_high']}", "Long-toss steps": r["step_text"],
                         "Deficit (mph)": f"{r['deficit_low']}–{r['deficit_high']}",
                         "Velo (mph)": f"{r['velo_low']:.0f}–{r['velo_high']:.0f}" if avg else "—",
                         "Dist/Mound F.": r["factor"], "Intensity F.": r["intensity"], "Projected Workload": r["workload"]} for r in rows])
    st.dataframe(det, hide_index=True, width="stretch",
                 column_config={k: st.column_config.NumberColumn(format="%.2f") for k in ("Dist/Mound F.", "Intensity F.", "Projected Workload")})
    st.caption("Deficit = mph below Avg Top Velo: 0–3 max effort (×2.0), 4–6 compete (×1.5), 7–9 building (×1.0), 10+ easy/recovery (×0.6).")


# ═════════════════════════ NEXT OUTING PLANNER ═════════════════════════
def save_planner(pid):
    k = lambda f: st.session_state.get(f"pl_{pid}_{f}")
    fields = {"target_type": k("type"), "target_date": k("date")}
    if f"pl_{pid}_pitches" in st.session_state:
        fields["planned_pitches"] = k("pitches")
    if f"pl_{pid}_innings" in st.session_state:
        fields["planned_innings"] = k("innings")
    db.update_player(pid, **fields)
    st.session_state[f"plsaved_{pid}"] = f"✓ Saved {stamp()}"


def save_overrides(pid, key, dates):
    for i, ch in st.session_state[key]["edited_rows"].items():
        if "override" in ch:
            db.save_override(pid, dates[int(i)], ch["override"])
    st.session_state[f"plsaved_{pid}"] = f"✓ Override saved {stamp()}"
    bump(f"plv_{pid}")


def clear_all_overrides(pid):
    db.clear_overrides(pid)
    bump(f"plv_{pid}")
    st.session_state[f"plsaved_{pid}"] = "✓ Overrides cleared"


def planner_tab(p, avg, daily):
    pid = p["id"]
    cb = dict(on_change=save_planner, args=(pid,))
    c = st.columns([1.4, 1.2, 1, 1, 1.4], vertical_alignment="bottom")
    ttype = c[0].selectbox("Next high-intent day", m.HIGH_INTENT_TYPES, key=f"pl_{pid}_type",
                           index=m.HIGH_INTENT_TYPES.index(p["target_type"]) if p["target_type"] in m.HIGH_INTENT_TYPES else 0, **cb)
    tdate = c[1].date_input("Date", value=p["target_date"], key=f"pl_{pid}_date", format="MM/DD/YYYY", **cb)
    pitches, innings = p["planned_pitches"], p["planned_innings"]
    if ttype == "Game":
        pitches = c[2].number_input("Planned pitches", 0, 150, pitches and int(pitches), 1, key=f"pl_{pid}_pitches", placeholder="optional", **cb)
        innings = c[3].number_input("Planned innings", 0.0, 9.0, innings, 1.0, format="%.1f", key=f"pl_{pid}_innings", placeholder="optional", **cb)
    c[4].markdown(f"<span class='saved'>{st.session_state.get(f'plsaved_{pid}', '')}</span>", unsafe_allow_html=True)

    s = m.status(daily, today)
    za = m.zone_adjustment(s["zone"])
    st.markdown("### Current status, last 7 / last 28 days")
    cc = st.columns(4)
    cc[0].metric("Acute · 7-day", fmt(s["acute"]))
    cc[1].metric("Chronic · 28-day", fmt(s["chronic"]))
    cc[2].metric("ACWR", fmt(s["acwr"], 2, "N/A"))
    cc[3].metric("Zone adjustment", f"{za:+d}" if za else "0")
    st.markdown(zone_box(s["zone"], s["guidance"]), unsafe_allow_html=True)

    if not tdate:
        st.info("Pick the date of your next Game outing or High Bullpen day to build the plan.")
        return
    if tdate <= today:
        st.warning("That date is today or already past. Update it to your **next** outing or bullpen day and the whole plan regenerates.")
        return
    plan = m.build_plan(daily, today, tdate, za, db.load_overrides(pid), avg)
    st.markdown("### Quick glance")
    if plan:
        r0 = plan[0]
        st.markdown(f"<div class='plan'><b>Tomorrow, {r0['date']:%a %m/%d}: {r0['final']}</b><br>{r0['plan']}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='plan'><b>Outing / bullpen day</b><br>{m.outing_text(ttype, tdate, avg, pitches, innings)}</div>",
                unsafe_allow_html=True)
    st.markdown("### This week's plan")
    if not plan:
        st.caption("Your High-Intent Day is tomorrow, so there are no days to plan in between.")
        return
    df = pd.DataFrame(plan)
    view = pd.DataFrame({"Date": df["date"], "Days until": df["days_until"], "Baseline": df["baseline"],
                         "Day type": df["final"], "override": df["override"], "Suggested plan (Example 1)": df["plan"]})
    key = f"plan_{pid}_{st.session_state.get(f'plv_{pid}', 0)}"
    st.data_editor(view, hide_index=True, width="stretch", key=key, on_change=save_overrides, args=(pid, key, list(df["date"])),
                   disabled=["Date", "Days until", "Baseline", "Day type", "Suggested plan (Example 1)"],
                   column_config={"Date": st.column_config.DateColumn(format="ddd MM/DD"),
                                  "override": st.column_config.SelectboxColumn("Manual override ✎", options=m.OVERRIDE_CHOICES, required=True,
                                                                               help="Pick a day type. It saves and every day after re-plans around it."),
                                  "Suggested plan (Example 1)": st.column_config.TextColumn(width="large")})
    a, b = st.columns([1, 3])
    a.button("Clear all overrides", key=f"clr_{pid}", on_click=clear_all_overrides, args=(pid,))
    if b.toggle("Show the math behind each day", key=f"math_{pid}"):
        st.dataframe(pd.DataFrame({"Date": df["date"], "Baseline tier": df["baseline_tier"], "Prior day type": df["prior_type"],
                                   "Prior planned": df["prior_planned"], "Prior actual": df["prior_actual"], "Actual/planned": df["ratio"],
                                   "Prior-day adj": df["prior_adj"], "Plan shift": df["plan_shift"], "Zone adj": df["zone_adj"],
                                   "Combined": df["combined"], "Clamped": df["clamped"], "Final tier": df["final_tier"]}),
                     hide_index=True, width="stretch",
                     column_config={"Date": st.column_config.DateColumn(format="ddd MM/DD"),
                                    "Prior planned": st.column_config.NumberColumn(format="%.1f"),
                                    "Prior actual": st.column_config.NumberColumn(format="%.1f"),
                                    "Actual/planned": st.column_config.NumberColumn(format="%.2f")})
    with st.expander("How the plan is built"):
        x, y = st.columns(2)
        x.dataframe(pd.DataFrame([{"Days until": k, "Default day type": v[0], "Why": v[1]} for k, v in m.TAPER_RULE.items()]), hide_index=True)
        y.dataframe(pd.DataFrame([{"(Days−6) mod 3": k, "Day type (6+ days out)": v[0], "Why": v[1]} for k, v in m.FAR_OUT_CYCLE.items()]), hide_index=True)
        st.markdown("""
- Each day starts from its baseline, then moves one tier (Low → Medium → High Non-Bullpen).
- **Prior-day plan shift:** if the day before ended harder or easier than its own baseline (for example from an override), that decides the adjustment on its own.
- Otherwise it takes the more conservative of: yesterday's actual logged workload vs. plan (more than 20% over = −1, more than 20% under = +1) and the zone (Caution/High Risk −1, Undertrained +1). A downgrade needs one signal; an upgrade needs both.
- The day before the high-intent day can only be downgraded. An upgrade out of Medium goes to High Non-Bullpen, never a bullpen.""")



# ═════════════════════════ BUILD-UP PLAN ═════════════════════════
def save_bu(pid, field, key):
    db.save_buildup(pid, **{field: st.session_state.get(key)})
    st.session_state[f"busaved_{pid}"] = f"✓ Saved {stamp()}"


def save_bu_days(pid, key, dates):
    for i, ch in st.session_state[key]["edited_rows"].items():
        f = {}
        for col, fld in (("Make off", "off"), ("Throws override", "throws"), ("Distance override", "distance"),
                         ("Velo low override", "velo_low"), ("Velo high override", "velo_high")):
            if col in ch:
                v = ch[col]
                f[fld] = bool(v) if fld == "off" else (None if v is None or (isinstance(v, float) and pd.isna(v)) else v)
        if f:
            db.save_buildup_day(pid, dates[int(i)], **f)
    st.session_state[f"busaved_{pid}"] = f"✓ Day change saved {stamp()} — the plan re-solved"
    bump(f"buv_{pid}")


def create_bu(pid):
    start = today + timedelta(days=1)
    db.save_buildup(pid, start=start, first_pen=start + timedelta(days=84), **{k: v for k, v in bu.DEFAULTS.items()
                                                                              if k not in ("start", "first_pen")})
    toast("Build-Up plan created — set his dates and the plan fills in")


def buildup_tab(p, avg, daily):
    pid = p["id"]
    cfg = db.load_buildup(pid)
    if not cfg:
        st.info("No Build-Up plan for him yet. A Build-Up plan lays out every day from his first catch play to his first "
                "bullpen, with throw counts solved from the workload model so his ACWR stays in the 0.8–1.3 sweet spot.")
        st.button("＋ Create a Build-Up plan", type="primary", on_click=create_bu, args=(pid,), key=f"bucreate_{pid}")
        return
    k = lambda f: f"bu_{pid}_{f}"
    cb = lambda f: dict(on_change=save_bu, args=(pid, f, k(f)))
    c = st.columns([1.2, 1.2, 1, 1, 1, 1.9], vertical_alignment="bottom")
    c[0].date_input("Start catch play", value=cfg["start"], key=k("start"), format="MM/DD/YYYY", **cb("start"))
    c[1].date_input("First bullpen", value=cfg["first_pen"], key=k("first_pen"), format="MM/DD/YYYY", **cb("first_pen"))
    c[2].number_input("First pen — pitches", 0, 80, int(cfg["pen_pitches"] or 20), 1, key=k("pen_pitches"), **cb("pen_pitches"))
    c[3].number_input("Pen velo low", 50.0, 105.0, float(cfg["pen_velo_low"] or 84), 1.0, format="%g", key=k("pen_velo_low"), **cb("pen_velo_low"))
    c[4].number_input("Pen velo high", 50.0, 105.0, float(cfg["pen_velo_high"] or 86), 1.0, format="%g", key=k("pen_velo_high"), **cb("pen_velo_high"))
    sp = list(bu.STARTING_POINTS)
    c[5].selectbox("Starting point", sp, index=sp.index(cfg["starting_point"]) if cfg["starting_point"] in sp else 0,
                   key=k("starting_point"), **cb("starting_point"),
                   help="Auto reads his last 4 weeks in the Throw Log: still throwing → continue from his load; off more than 5 days → restart.")
    c2 = st.columns([1.2, 1.2, 3.6], vertical_alignment="bottom")
    c2[0].number_input("Max long-toss distance (ft)", 60, 300, int(cfg["max_distance"] or 180), 15, key=k("max_distance"), **cb("max_distance"))
    c2[1].number_input("Volume level", 0.5, 1.5, float(cfg["volume"] or 1.0), 0.05, format="%.2f", key=k("volume"), **cb("volume"),
                       help="Scales every week's load (1.00 = the standard plan).")
    c2[2].markdown(f"<span class='saved'>{st.session_state.get(f'busaved_{pid}', '')}</span>", unsafe_allow_html=True)

    plan = bu.build(avg, cfg, db.load_buildup_days(pid), daily)
    for kind, msg in plan["messages"]:
        st.markdown(f"<div class='bu-{kind}'>{msg}</div>", unsafe_allow_html=True)
    if not plan["days"]:
        return
    sm = plan["summary"]
    mc = st.columns(6)
    mc[0].metric("Window", f"{sm['window']} days")
    mc[1].metric("Build weeks", sm["build_weeks"])
    mc[2].metric("Start load / week", fmt(sm["start_load"], 0))
    mc[3].metric("Weekly growth", f"+{(sm['growth'] - 1) * 100:.1f}%")
    mc[4].metric("First-pen ACWR", fmt(sm["first_pen_acwr"], 2, "—"))
    mc[5].metric("Highest ACWR", fmt(sm["max_acwr"], 2, "—"))
    with st.expander(f"His last 4 weeks in the Throw Log · {sm['plan_mode']}"):
        w = st.columns(6)
        w[0].metric("Days since last throw", "none logged" if sm["days_since_last"] is None else sm["days_since_last"])
        for i, v in enumerate(sm["week_loads"]):
            w[i + 1].metric(f"Week −{i + 1} load", fmt(v))
        w[5].metric("ACWR going in", fmt(sm["acwr_going_in"], 2, "—"))
        st.caption(f"Peak load/week {fmt(sm['peak_load'], 0)} · taper scale {fmt(sm['taper_scale'], 2)} · "
                   f"history counts in ACWR: {'yes' if sm['history_counts'] else 'no'}. "
                   "Every number here comes from the engine settings in buildup.py (the workbook's Reference tab).")

    st.markdown("### Week by week")
    wk = pd.DataFrame(plan["weeks"])
    wk["Week"] = [f"Wk {b} · {d:%m/%d}" for b, d in zip(wk["week"], wk["week_of"])]
    base = alt.Chart(wk).encode(x=alt.X("Week:O", sort=None, title=None, axis=alt.Axis(labelAngle=-30)))
    bars = base.mark_bar(color=DARK_GRAY, cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
        y=alt.Y("workload:Q", title="Weekly workload"),
        tooltip=["Week", alt.Tooltip("workload:Q", format=".1f", title="Workload"), alt.Tooltip("throw_days:Q", title="Throw days"),
                 alt.Tooltip("acwr_end:Q", format=".2f", title="ACWR at end of week")])
    line = base.mark_line(color=PURPLE, point=alt.OverlayMarkDef(color=PURPLE, filled=True, size=55), strokeWidth=2.5).encode(
        y=alt.Y("acwr_end:Q", title="ACWR at end of week", scale=alt.Scale(domain=[0, 1.8])))
    st.altair_chart(alt.layer(bars, line).resolve_scale(y="independent").properties(height=280), width="stretch")
    st.dataframe(pd.DataFrame({"Week of": wk["week_of"], "Week": wk["week"], "Throw days": wk["throw_days"],
                               "Weekly workload": wk["workload"], "Change vs prior week": wk["change"],
                               "ACWR at end of week": wk["acwr_end_txt"].replace("", "—")}),
                 hide_index=True, width="stretch",
                 column_config={"Week of": st.column_config.DateColumn(format="ddd MM/DD"),
                                "Weekly workload": st.column_config.NumberColumn(format="%.1f"),
                                "Change vs prior week": st.column_config.NumberColumn(format="percent")})

    st.markdown("### Day by day")
    st.caption("Tick **Make off** to skip a day (its share moves onto his other days that week). Type a **Distance** or **Velo** override "
               "and the throws re-solve to hold the day's workload, unless you also set **Throws override**. Changes save when you leave the cell.")
    dd = pd.DataFrame(plan["days"])
    view = pd.DataFrame({"Date": dd["date"], "Day": dd["day"], "To pen": dd["days_to_pen"], "Phase": dd["phase"],
                         "Day type": dd["day_type"], "Session": dd["session"], "Plan": dd["plan"], "Workload": dd["workload"],
                         "ACWR": dd["acwr_txt"], "Make off": dd["off"].astype(bool),
                         "Throws override": pd.to_numeric(dd["throws_override"], errors="coerce"),
                         "Distance override": pd.to_numeric(dd["distance_override"], errors="coerce"),
                         "Velo low override": pd.to_numeric(dd["velo_low_override"], errors="coerce"),
                         "Velo high override": pd.to_numeric(dd["velo_high_override"], errors="coerce")})
    key = f"budays_{pid}_{st.session_state.get(f'buv_{pid}', 0)}"
    st.data_editor(view, hide_index=True, width="stretch", height=min(760, 38 + 35 * len(view)), key=key,
                   on_change=save_bu_days, args=(pid, key, list(dd["date"])),
                   disabled=["Date", "Day", "To pen", "Phase", "Day type", "Session", "Plan", "Workload", "ACWR"],
                   column_config={"Date": st.column_config.DateColumn(format="ddd MM/DD"),
                                  "Plan": st.column_config.TextColumn(width="large"),
                                  "Workload": st.column_config.NumberColumn(format="%.1f"),
                                  "Make off": st.column_config.CheckboxColumn("Make off ✎"),
                                  "Throws override": st.column_config.NumberColumn("Throws ✎", min_value=0, max_value=150, step=1),
                                  "Distance override": st.column_config.NumberColumn("Distance ✎ (ft)", min_value=30, max_value=330, step=5),
                                  "Velo low override": st.column_config.NumberColumn("Velo low ✎", min_value=40, max_value=105, step=1),
                                  "Velo high override": st.column_config.NumberColumn("Velo high ✎", min_value=40, max_value=105, step=1)})
    a, b, c3 = st.columns([1.3, 1.1, 3])
    if a.button("Clear all day changes", key=f"buclr_{pid}"):
        db.clear_buildup_days(pid)
        bump(f"buv_{pid}")
        toast("Day changes cleared")
        st.rerun()
    if st.session_state.get(f"budel_{pid}"):
        if b.button("Delete it", type="primary", key=f"budely_{pid}"):
            db.delete_buildup(pid)
            st.session_state.pop(f"budel_{pid}", None)
            toast("Build-Up plan deleted")
            st.rerun()
        if c3.button("Keep", key=f"budeln_{pid}"):
            st.session_state.pop(f"budel_{pid}", None)
            st.rerun()
    elif b.button("Delete plan", key=f"budel_btn_{pid}"):
        st.session_state[f"budel_{pid}"] = True
        st.rerun()
    with st.expander("How the Build-Up plan works"):
        st.markdown(f"""
- The weekly workload starts at the **Start Weekly Load** for his starting point and grows each week (never faster than
  +{(bu.MAX_WEEKLY_GROWTH - 1) * 100:.0f}%) until it reaches **{bu.PEAK_WEEKLY_LOAD}** right before the taper week. Every {bu.DELOAD_EVERY}th week is a
  deload week ({bu.DELOAD_SHARE:.0%} of trend).
- Each day's target is that week's load times its load share ({", ".join(f"{s[0]:.0%}" for s in bu.WEEK_SHARES)} for days 1–7 of the plan week).
  Throw counts are solved from the target with the same Distance and Intensity Factors as the Throw Log, so a longer
  max distance means fewer throws, not more workload.
- The last 7 days are a fixed taper into the first bullpen.
- **Auto** starting point: if he's thrown in the last {bu.MAX_DAYS_OFF_HISTORY} days, the plan continues from his average week over the last 28 days
  and that history counts in the ACWR from day 1. Otherwise it's a restart and the ACWR reads from day 28.""")


# ═════════════════════════ PLAYER PAGE ═════════════════════════
def save_avg(pid):
    db.update_player(pid, avg_top_velo=st.session_state.get(f"avg_{pid}"))
    toast("Avg Top Velo saved")


def player_page(p):
    pid, avg = p["id"], none_if_nan(p["avg_top_velo"])
    daily = daily_of(pid, avg)
    s = m.status(daily, today)
    with st.container(border=True):
        h = st.columns([0.65, 2.4, 1.4, 1.15, 1.15, 1.25], vertical_alignment="center")
        h[0].markdown(f"<div class='jersey'>{p['number'] or ''}</div>", unsafe_allow_html=True)
        meta = " · ".join(x for x in (p.get("position"), p.get("year"), p.get("bt")) if x)
        h[1].markdown(f"<div class='pname'>{p['name']}</div><span class='pmeta'>{meta}</span>", unsafe_allow_html=True)
        h[2].number_input("Avg Top Velo (mph)", 40.0, 110.0, avg, 0.1, format="%.1f", key=f"avg_{pid}", placeholder="set this first",
                          on_change=save_avg, args=(pid,))
        h[3].metric("Today", fmt(s["today"]))
        h[4].metric("ACWR", fmt(s["acwr"], 2, "N/A"))
        h[5].markdown(f"<div style='font-size:.85rem;color:#666'>Zone</div>{pill(s['zone'])}", unsafe_allow_html=True)
    if not avg:
        st.warning("Enter your **Avg Top Velo** above (the average of your hardest, most competitive readings, not one peak). "
                   "Intensity and workload can't be calculated without it.")
    sub = st.segmented_control("Section", ["Throw Log", "Dashboard", "Day Type Templates", "Next Outing Planner", "Build-Up Plan"],
                               default="Throw Log", required=True, key="sub", label_visibility="collapsed")
    if sub == "Build-Up Plan":
        buildup_tab(p, avg, daily)
    elif sub == "Dashboard":
        dashboard_tab(p, avg, daily)
    elif sub == "Day Type Templates":
        templates_tab(p, avg)
    elif sub == "Next Outing Planner":
        planner_tab(p, avg, daily)
    else:
        throw_log_tab(p, avg)


# ═════════════════════════ TEAM ═════════════════════════
def open_player(key, labels):
    rows = st.session_state[key].selection.rows
    if rows:
        st.session_state[TAB_KEY] = labels[rows[0]]
        bump("teamsel")


def save_roster(key, ids):
    for i, ch in st.session_state[key]["edited_rows"].items():
        fields = {}
        for col, f in (("#", "number"), ("Position", "position"), ("Avg Top Velo", "avg_top_velo"), ("Peak Velo", "peak_velo")):
            if col in ch:
                fields[f] = ch[col]
        db.update_player(ids[int(i)], **fields)
    toast("Roster saved")


def team_page():
    st.markdown(f"### Staff overview · {today:%A, %b %d}")
    bus = db.all_buildups()
    rows = []
    for p in players.to_dict("records"):
        avg = none_if_nan(p["avg_top_velo"])
        daily = daily_of(p["id"], avg)
        s = m.status(daily, today)
        nxt = tmr = "—"
        td = p["target_date"] if isinstance(p["target_date"], date) else None
        if td and td > today:
            nxt = f"{p['target_type'] or 'Game'} · {td:%a %m/%d}"
            plan = m.build_plan(daily, today, td, m.zone_adjustment(s["zone"]), db.load_overrides(p["id"]), avg)
            tmr = plan[0]["final"] if plan else (p["target_type"] or "Game")
        zone = zshort(s["zone"])
        rows.append({"#": p["number"], "Player": p["name"], "Pos": p["position"], "Avg Top Velo": avg,
                     "Sessions": len(db.load_log(p["id"])), "Today": s["today"], "ACWR": s["acwr"],
                     "Zone": {"Sweet Spot": "🟢 ", "Caution": "🟡 ", "High Risk": "🔴 ", "Undertrained": "🔵 "}.get(zone, "⚪ ") + zone,
                     "Spike": "🔴 Spike" if s["spike_flag"] not in ("", "OK") else (s["spike_flag"] or "—"),
                     "Next high-intent day": nxt, "Tomorrow": tmr,
                     "Build-Up": (f"{bus[p['id']]['start']:%m/%d} → pen {bus[p['id']]['first_pen']:%m/%d}"
                                  if p["id"] in bus and bus[p["id"]].get("start") and bus[p["id"]].get("first_pen") else "—")})
    labels = [tab_label(p) for p in players.to_dict("records")]
    key = f"team_{st.session_state.get('teamsel', 0)}"
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=38 + 35 * len(rows), key=key,
                 on_select=partial(open_player, key, labels), selection_mode="single-row",
                 column_config={"Avg Top Velo": st.column_config.NumberColumn(format="%.1f"),
                                "Today": st.column_config.NumberColumn(format="%.1f"),
                                "ACWR": st.column_config.NumberColumn(format="%.2f")})
    st.caption("Click a player's row to open his tab.")

    st.markdown("### Roster")
    st.caption("**Avg Top Velo** drives the Intensity Factor: the average of several of his hardest, most competitive readings, "
               "not a single peak. Peak Velo is reference only. Edits save as soon as you leave the cell.")
    ros = pd.DataFrame({"#": players["number"], "Name": players["name"], "Position": players["position"],
                        "Avg Top Velo": players["avg_top_velo"], "Peak Velo": players["peak_velo"]})
    rkey = f"roster_{st.session_state.get('rosv', 0)}"
    st.data_editor(ros, hide_index=True, width="stretch", key=rkey, on_change=save_roster, args=(rkey, list(players["id"])),
                   disabled=["Name"], column_config={
                       "Avg Top Velo": st.column_config.NumberColumn("Avg Top Velo ✎", format="%.1f", min_value=40, max_value=110),
                       "Peak Velo": st.column_config.NumberColumn("Peak Velo ✎", format="%.1f", min_value=40, max_value=110),
                       "#": st.column_config.TextColumn("# ✎"), "Position": st.column_config.TextColumn("Position ✎")})
    a, b = st.columns(2)
    with a.form("add_player", clear_on_submit=True, border=True):
        st.markdown("**Add a player**")
        f = st.columns([1, 2.4, 1.2, 1.4])
        num = f[0].text_input("Jersey #")
        name = f[1].text_input("Name")
        pos = f[2].text_input("Position", "RHP")
        avg = f[3].number_input("Avg Top Velo", 40.0, 110.0, None, 0.1, format="%.1f")
        if st.form_submit_button("Add player", type="primary"):
            if name.strip():
                db.add_player(name, num.strip(), pos.strip() or "RHP", avg_top=avg)
                bump("rosv")
                toast(f"Added {name.strip()}")
                st.rerun()
            else:
                st.error("Type a name first.")
    with b.container(border=True):
        st.markdown("**Remove a player**")
        rm = st.selectbox("Player", ["—"] + list(players["name"]), key="rm_pick", label_visibility="collapsed")
        if rm != "—":
            if st.session_state.get("rm_confirm") == rm:
                x, y = st.columns(2)
                if x.button(f"Remove {rm}", type="primary"):
                    db.remove_player(players.loc[players["name"] == rm, "id"].iloc[0])
                    st.session_state.pop("rm_confirm", None)
                    toast(f"Removed {rm}. His log is kept and comes back if he's added again.")
                    st.rerun()
                if y.button("Keep"):
                    st.session_state.pop("rm_confirm", None)
                    st.rerun()
            elif st.button("Remove"):
                st.session_state["rm_confirm"] = rm
                st.rerun()
        st.caption("Removing hides his tab. His throw log is kept.")


# ═════════════════════════ LAYOUT ═════════════════════════
plist = players.to_dict("records")
labels = ["🏠 Team"] + [tab_label(p) for p in plist]
if st.session_state.get(TAB_KEY) not in labels:
    st.session_state.pop(TAB_KEY, None)
tabs = st.tabs(labels, key=TAB_KEY, on_change="rerun")
if tabs[0].open:
    with tabs[0]:
        team_page()
for tab, p in zip(tabs[1:], plist):
    if tab.open:
        with tab:
            player_page(p)
