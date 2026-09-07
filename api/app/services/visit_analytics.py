import hashlib
import math
import os
import sqlite3
from datetime import datetime, timezone

import httpx

from app.config import settings

BVRC_HQ_LAT = settings.bvrc_hq_lat
BVRC_HQ_LON = settings.bvrc_hq_lon


def _init_db(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS visits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            visit_ts TEXT NOT NULL,
            visit_date TEXT NOT NULL,
            country TEXT,
            country_code TEXT,
            lat REAL,
            lon REAL,
            ip_hash TEXT,
            session_id TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS visit_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    # One-time import from old v28 DB (sibling of platform, not under science/).
    from app.config import BASE_DIR
    legacy_v28_db = BASE_DIR.parent / "SNP" / "visit_analytics.db"
    row = conn.execute("SELECT value FROM visit_meta WHERE key='legacy_migrated'").fetchone()
    if not row and legacy_v28_db.exists():
        try:
            vconn = sqlite3.connect(legacy_v28_db)
            legacy_row = vconn.execute("SELECT value FROM visit_meta WHERE key='legacy_count'").fetchone()
            if legacy_row:
                conn.execute(
                    "INSERT OR REPLACE INTO visit_meta (key, value) VALUES ('legacy_count', ?)",
                    (str(legacy_row[0]),),
                )
            conn.execute(
                "INSERT OR REPLACE INTO visit_meta (key, value) VALUES ('legacy_migrated', '1')",
            )
            vconn.close()
        except Exception:
            pass
    conn.commit()


def _lookup_geo(ip: str):
    if not ip or ip in ("127.0.0.1", "::1") or ip.startswith("192.168.") or ip.startswith("10."):
        return {
            "country": "China",
            "country_code": "CN",
            "lat": BVRC_HQ_LAT,
            "lon": BVRC_HQ_LON,
            "city": "Local",
        }
    try:
        with httpx.Client(timeout=4.0) as client:
            resp = client.get(
                f"http://ip-api.com/json/{ip}",
                params={"fields": "status,country,countryCode,lat,lon,city"},
            )
            data = resp.json()
            if data.get("status") == "success":
                return {
                    "country": data.get("country") or "Unknown",
                    "country_code": data.get("countryCode") or "",
                    "lat": data.get("lat"),
                    "lon": data.get("lon"),
                    "city": data.get("city") or "",
                }
    except Exception:
        pass
    return None


def record_visit(ip: str, session_id=None):
    settings.visit_db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.visit_db_path)
    _init_db(conn)
    geo = _lookup_geo(ip) or {
        "country": "Unknown",
        "country_code": "",
        "lat": BVRC_HQ_LAT,
        "lon": BVRC_HQ_LON,
        "city": "",
    }
    now = datetime.now(timezone.utc)
    ip_hash = hashlib.sha256(ip.encode()).hexdigest()[:16]
    conn.execute(
        "INSERT INTO visits (visit_ts, visit_date, country, country_code, lat, lon, ip_hash, session_id) VALUES (?,?,?,?,?,?,?,?)",
        (
            now.isoformat(),
            now.strftime("%Y-%m-%d"),
            geo.get("country"),
            geo.get("country_code"),
            geo.get("lat"),
            geo.get("lon"),
            ip_hash,
            session_id,
        ),
    )
    conn.commit()
    conn.close()


def get_visit_stats() -> dict:
    settings.visit_db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.visit_db_path)
    _init_db(conn)
    legacy_row = conn.execute("SELECT value FROM visit_meta WHERE key='legacy_count'").fetchone()
    legacy_count = int(legacy_row[0]) if legacy_row else 0
    db_count = conn.execute("SELECT COUNT(*) FROM visits").fetchone()[0]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_count = conn.execute(
        "SELECT COUNT(*) FROM visits WHERE visit_date = ?", (today,)
    ).fetchone()[0]
    countries = conn.execute(
        "SELECT COUNT(DISTINCT country) FROM visits WHERE country IS NOT NULL AND country != ''"
    ).fetchone()[0]
    rows = conn.execute(
        """
        SELECT country, MAX(country_code) AS country_code,
               AVG(lat) AS lat, AVG(lon) AS lon, COUNT(*) AS visits
        FROM visits
        WHERE country IS NOT NULL AND country != '' AND lat IS NOT NULL AND lon IS NOT NULL
        GROUP BY country
        ORDER BY visits DESC
        LIMIT 50
        """
    ).fetchall()
    conn.close()
    by_country = [
        {
            "country": r[0],
            "country_code": r[1],
            "lat": r[2],
            "lon": r[3],
            "visits": r[4],
        }
        for r in rows
    ]
    return {
        "total": legacy_count + db_count,
        "today": today_count,
        "countries": countries,
        "by_country": by_country,
        "hq": {"lat": BVRC_HQ_LAT, "lon": BVRC_HQ_LON, "label": "BVRC HQ"},
    }


def build_footer_map_html(stats: dict) -> str:
    try:
        import plotly.graph_objects as go
    except ImportError:
        return (
            '<div style="height:135px;display:flex;align-items:center;justify-content:center;'
            'color:#64748B;font-size:12px;">Map requires plotly</div>'
        )

    df_rows = stats.get("by_country") or []
    if not df_rows:
        return (
            '<div style="height:135px;display:flex;align-items:center;justify-content:center;'
            'color:#64748B;font-size:12px;">No visitor data yet</div>'
        )

    sizes = [max(8, min(36, 8 + math.sqrt(v.get("visits", 1)) * 5)) for v in df_rows]
    fig = go.Figure()
    fig.add_trace(
        go.Scattergeo(
            lat=[BVRC_HQ_LAT],
            lon=[BVRC_HQ_LON],
            mode="markers",
            marker=dict(size=12, color="#ffffff", symbol="star", line=dict(width=1, color="#b01a75")),
            hovertext=["BVRC HQ, Beijing"],
            hoverinfo="text",
        )
    )
    fig.add_trace(
        go.Scattergeo(
            lat=[r["lat"] for r in df_rows],
            lon=[r["lon"] for r in df_rows],
            mode="markers",
            marker=dict(
                size=sizes,
                color="rgba(220, 53, 69, 0.62)",
                line=dict(width=1, color="rgba(255, 255, 255, 0.55)"),
            ),
            text=[f"{r['country']}: {int(r['visits'])}" for r in df_rows],
            hoverinfo="text",
        )
    )
    fig.update_geos(
        projection_type="natural earth",
        showland=True,
        landcolor="#e8f0ed",
        showocean=True,
        oceancolor="#d4e8e2",
        showcountries=True,
        countrycolor="#b8ccc4",
        bgcolor="rgba(0,0,0,0)",
        lataxis_range=[-60, 80],
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        height=135,
        showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig.to_html(
        full_html=False,
        include_plotlyjs=True,
        config={"displayModeBar": False},
        default_height="135px",
        default_width="100%",
    )
