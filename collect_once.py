#!/usr/bin/env python3
"""
Collecteur VéloCité Besançon — UN SEUL passage (pensé pour GitHub Actions).
Interroge le flux GBFS une fois, ajoute une ligne par station au CSV,
et crée le référentiel des stations s'il n'existe pas encore.
"""

import csv
import json
import os
from datetime import datetime, timezone

import requests

GBFS_STATUS_URL = "https://api.cyclocity.fr/contracts/besancon/gbfs/v2/station_status.json"
GBFS_INFO_URL = "https://api.cyclocity.fr/contracts/besancon/gbfs/v2/station_information.json"

DATA_DIR = os.environ.get("DATA_DIR", "data")
CSV_PATH = os.path.join(DATA_DIR, "velocite_log.csv")
STATIONS_PATH = os.path.join(DATA_DIR, "stations.json")

REQUEST_TIMEOUT = 15

CSV_FIELDS = [
    "timestamp_utc",
    "station_id",
    "num_bikes_available",
    "mechanical",
    "electrical",
    "num_docks_available",
    "is_renting",
    "is_returning",
]


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_json(url):
    resp = requests.get(url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def ensure_station_reference():
    if os.path.exists(STATIONS_PATH):
        return
    info = fetch_json(GBFS_INFO_URL)
    stations = {}
    for s in info["data"]["stations"]:
        if not s.get("name"):
            continue
        stations[s["station_id"]] = {
            "name": s["name"],
            "lat": s["lat"],
            "lon": s["lon"],
            "capacity": s.get("capacity", 0),
        }
    with open(STATIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(stations, f, ensure_ascii=False, indent=2)
    print(f"Référentiel stations créé ({len(stations)} stations).")


def poll_once():
    status = fetch_json(GBFS_STATUS_URL)
    ts = now_iso()

    file_exists = os.path.exists(CSV_PATH)
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if not file_exists:
            writer.writeheader()

        n = 0
        for st in status["data"]["stations"]:
            mech = 0
            elec = 0
            for vt in st.get("vehicle_types_available", []):
                if vt["vehicle_type_id"] == "mechanical":
                    mech = vt["count"]
                elif vt["vehicle_type_id"] == "electrical":
                    elec = vt["count"]

            writer.writerow({
                "timestamp_utc": ts,
                "station_id": st["station_id"],
                "num_bikes_available": st.get("num_bikes_available", 0),
                "mechanical": mech,
                "electrical": elec,
                "num_docks_available": st.get("num_docks_available", 0),
                "is_renting": st.get("is_renting", False),
                "is_returning": st.get("is_returning", False),
            })
            n += 1

    print(f"[{ts}] {n} stations enregistrées dans {CSV_PATH}")


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    ensure_station_reference()
    poll_once()


if __name__ == "__main__":
    main()
