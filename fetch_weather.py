#!/usr/bin/env python3
"""Holt Wetter- und Seegangsdaten von Open-Meteo fuer die Sardinien-Reise
und schreibt data/latest.json (vollstaendig) und data/latest.md (kompakt).
Nur Standardbibliothek, laeuft in GitHub Actions."""
import json
import statistics
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

# Name, Region, Land-Lat, Land-Lon, See-Lat, See-Lon (None = kein Seepunkt)
POINTS = [
    ("La Maddalena", "Norden", 41.215, 9.410, 41.30, 9.30),
    ("Santa Teresa", "Norden", 41.240, 9.190, 41.32, 9.17),
    ("Bonifacio", "Korsika", 41.388, 9.160, 41.32, 9.17),
    ("Palau", "Norden", 41.180, 9.385, 41.30, 9.30),
    ("Luogosanto", "Gallura Inland", 41.047, 9.205, None, None),
    ("Posada", "Nordost", 40.632, 9.720, 40.62, 9.80),
    ("Cala Gonone", "Osten", 40.281, 9.630, 40.20, 9.70),
    ("Dorgali/Tiscali", "Osten", 40.291, 9.588, None, None),
    ("Gorropu", "Osten Berge", 40.160, 9.500, None, None),
    ("Golgo/Goloritze", "Osten", 40.130, 9.640, 40.20, 9.70),
    ("Arbatax/S.M.Navarrese", "Ogliastra", 39.920, 9.700, 39.93, 9.76),
    ("Costa Rei", "Suedost", 39.250, 9.580, 39.25, 9.66),
    ("Villasimius", "Suedost", 39.140, 9.520, 39.08, 9.55),
    ("Cagliari", "Sueden", 39.210, 9.150, 39.17, 9.22),
    ("Chia", "Sueden", 38.890, 8.880, 38.85, 8.88),
    ("Barumini", "Inland", 39.700, 8.990, None, None),
    ("Carloforte", "Suedwest", 39.140, 8.310, 39.12, 8.15),
    ("Masua/Porto Flavia", "Suedwest", 39.330, 8.420, 39.33, 8.36),
    ("Costa Verde", "Suedwest", 39.540, 8.460, 39.55, 8.38),
    ("Sinis", "Westen", 39.950, 8.410, 39.95, 8.33),
    ("Bosa", "Westen", 40.298, 8.500, 40.30, 8.40),
    ("Alghero", "Nordwest", 40.558, 8.320, 40.55, 8.25),
]
DAYS = 10
TZ = "Europe/Rome"
UA = {"User-Agent": "sardinien-wetter (GitHub Actions; private trip planning)"}


def get(url, params):
    q = urllib.parse.urlencode(params, safe=",")
    req = urllib.request.Request(f"{url}?{q}", headers=UA)
    with urllib.request.urlopen(req, timeout=90) as r:
        data = json.loads(r.read().decode())
    return data if isinstance(data, list) else [data]


def compass(deg):
    if deg is None:
        return "-"
    return ["N", "NO", "O", "SO", "S", "SW", "W", "NW"][round((deg % 360) / 45) % 8]


def rnd(x, n=0):
    if x is None:
        return None
    return round(x, n) if n else int(round(x))


def main():
    lat = ",".join(str(p[2]) for p in POINTS)
    lon = ",".join(str(p[3]) for p in POINTS)
    base = {"latitude": lat, "longitude": lon, "timezone": TZ, "forecast_days": DAYS}

    mix = get("https://api.open-meteo.com/v1/forecast", {**base, "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,wind_gusts_10m_max,wind_direction_10m_dominant,sunshine_duration"})
    models = ["ecmwf_ifs025", "icon_seamless", "gfs_seamless", "ukmo_seamless"]
    mm = get("https://api.open-meteo.com/v1/forecast", {**base, "daily": "precipitation_sum,wind_gusts_10m_max", "models": ",".join(models)})
    ens = get("https://ensemble-api.open-meteo.com/v1/ensemble", {**base, "daily": "precipitation_sum,wind_gusts_10m_max", "models": "ecmwf_ifs025"})

    sea = [p for p in POINTS if p[4] is not None]
    mbase = {"latitude": ",".join(str(p[4]) for p in sea), "longitude": ",".join(str(p[5]) for p in sea), "timezone": TZ, "forecast_days": DAYS, "daily": "wave_height_max"}
    marine = get("https://marine-api.open-meteo.com/v1/marine", mbase)
    try:
        marine_ec = get("https://marine-api.open-meteo.com/v1/marine", {**mbase, "models": "ecmwf_wam025"})
    except Exception:
        marine_ec = [None] * len(sea)

    out = {"generated_utc": datetime.now(timezone.utc).isoformat(timespec="minutes"), "source": "Open-Meteo (best match, ECMWF IFS, ICON, GFS, UKMO, ECMWF-Ensemble 51, Wellen Meteo-France + ECMWF WAM)", "points": []}
    si = 0
    for i, p in enumerate(POINTS):
        d, m, e = mix[i]["daily"], mm[i]["daily"], ens[i]["daily"]
        w = we = None
        if p[4] is not None:
            w = marine[si]["daily"]
            we = marine_ec[si]["daily"] if marine_ec[si] else None
            si += 1
        pk = [k for k in e if k.startswith("precipitation_sum")]
        gk = [k for k in e if k.startswith("wind_gusts_10m_max")]
        days = []
        for j, t in enumerate(d["time"]):
            P = [e[k][j] for k in pk if e[k][j] is not None]
            G = [e[k][j] for k in gk if e[k][j] is not None]
            pct = lambda arr, f: round(100 * sum(1 for x in arr if f(x)) / len(arr)) if arr else None
            days.append({
                "date": t,
                "wc": d["weather_code"][j],
                "tmax": rnd(d["temperature_2m_max"][j]), "tmin": rnd(d["temperature_2m_min"][j]),
                "rain_mix": rnd(d["precipitation_sum"][j], 1),
                "rain": {mo: rnd(m.get(f"precipitation_sum_{mo}", [None] * 99)[j], 1) for mo in models},
                "gust_mix": rnd(d["wind_gusts_10m_max"][j]), "dir": compass(d["wind_direction_10m_dominant"][j]),
                "gust": {mo: rnd(m.get(f"wind_gusts_10m_max_{mo}", [None] * 99)[j]) for mo in models},
                "sun_h": rnd((d["sunshine_duration"][j] or 0) / 3600, 1),
                "ens_p1": pct(P, lambda x: x >= 1), "ens_p5": pct(P, lambda x: x >= 5), "ens_p20": pct(P, lambda x: x >= 20),
                "ens_gust_med": rnd(statistics.median(G)) if G else None, "ens_g60": pct(G, lambda x: x >= 60),
                "wave": rnd(w["wave_height_max"][j], 1) if w else None,
                "wave_ecmwf": rnd(we["wave_height_max"][j], 1) if we and j < len(we["wave_height_max"]) else None,
            })
        out["points"].append({"name": p[0], "region": p[1], "lat": p[2], "lon": p[3], "sea": [p[4], p[5]] if p[4] else None, "days": days})

    with open("data/latest.json", "w") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    berlin = datetime.now(timezone.utc) + timedelta(hours=2)
    lines = [f"# Sardinien Wetter – Stand {berlin:%d.%m.%Y %H:%M} MESZ", "",
             "Quelle: " + out["source"], "",
             "Spalten: Datum | Tmax/Tmin °C | Regen mm Mix (ECMWF/ICON/GFS/UKMO) | Ensemble P>=1/5/20 mm % | Böen km/h Mix Richtung (ECMWF/ICON/GFS/UKMO) | Ens. Böen-Median, P>=60 % | Sonne h | Welle m (MF/ECMWF)", ""]
    for pt in out["points"]:
        lines.append(f"## {pt['name']} ({pt['region']})")
        for x in pt["days"]:
            r = "/".join("-" if x["rain"][mo] is None else str(x["rain"][mo]) for mo in models)
            g = "/".join("-" if x["gust"][mo] is None else str(x["gust"][mo]) for mo in models)
            wv = "-" if x["wave"] is None else f"{x['wave']}/{'-' if x['wave_ecmwf'] is None else x['wave_ecmwf']}"
            lines.append(f"{x['date'][5:]} | {x['tmax']}/{x['tmin']} | {x['rain_mix']} ({r}) | {x['ens_p1']}/{x['ens_p5']}/{x['ens_p20']} | {x['gust_mix']} {x['dir']} ({g}) | {x['ens_gust_med']}, {x['ens_g60']} | {x['sun_h']} | {wv}")
        lines.append("")
    with open("data/latest.md", "w") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
