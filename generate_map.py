#!/usr/bin/env python3
"""
Génère une carte Leaflet interactive avec curseur temporel à partir du CSV
produit par collector.py.

Usage:
    python generate_map.py --csv velocite_log.csv --stations stations.json --out carte_velocite.html
"""

import argparse
import csv
import json
from collections import defaultdict


def load_stations(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_log(path):
    """
    Renvoie:
      timestamps: liste triée de tous les timestamps (str ISO)
      data: dict timestamp -> dict station_id -> {mechanical, electrical, total, docks}
    """
    data = defaultdict(dict)
    timestamps = set()

    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts = row["timestamp_utc"]
            timestamps.add(ts)
            data[ts][row["station_id"]] = {
                "mechanical": int(row["mechanical"]),
                "electrical": int(row["electrical"]),
                "total": int(row["num_bikes_available"]),
                "docks": int(row["num_docks_available"]),
            }

    return sorted(timestamps), data


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8" />
<title>VéloCité Besançon — Carte animée</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<style>
  html, body { margin: 0; padding: 0; height: 100%; font-family: -apple-system, "Segoe UI", Roboto, sans-serif; }
  #map { position: absolute; top: 0; bottom: 96px; left: 0; right: 0; }
  #controls {
    position: absolute; bottom: 0; left: 0; right: 0; height: 96px;
    background: #14181f; color: #f0f0f0; display: flex; flex-direction: column;
    justify-content: center; padding: 10px 20px; box-sizing: border-box; gap: 8px;
    box-shadow: 0 -2px 10px rgba(0,0,0,0.3);
  }
  #timeLabel { font-size: 15px; font-weight: 600; text-align: center; }
  #slider { width: 100%; }
  #playBtn {
    position: absolute; left: 20px; top: 50%; transform: translateY(-50%);
    background: #2c7be5; color: white; border: none; border-radius: 6px;
    width: 40px; height: 40px; font-size: 16px; cursor: pointer;
  }
  .row { display: flex; align-items: center; gap: 12px; }
  .legend {
    position: absolute; top: 10px; right: 10px; background: white; padding: 10px 14px;
    border-radius: 8px; box-shadow: 0 1px 6px rgba(0,0,0,0.3); font-size: 13px; z-index: 1000;
  }
  #map { background: #f2f2f0; }
  .legend div { display: flex; align-items: center; gap: 6px; margin: 3px 0; }
  .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
</style>
</head>
<body>
<div id="map"></div>
<div class="legend">
  <strong>Vélos disponibles</strong>
  <div><span class="dot" style="background:#ff8fc7"></span> Mécanique</div>
  <div><span class="dot" style="background:#7fd4f5"></span> Électrique</div>
  <div style="margin-top:4px">Taille du cercle = total dispo</div>
</div>
<div id="controls">
  <div id="timeLabel">--</div>
  <div class="row">
    <button id="playBtn">▶</button>
    <input type="range" id="slider" min="0" max="0" value="0" step="1" style="margin-left:50px" />
  </div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const STATIONS = __STATIONS_JSON__;
const TIMESTAMPS = __TIMESTAMPS_JSON__;
const DATA = __DATA_JSON__;

const map = L.map('map').setView([47.238, 6.022], 14);
L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
  attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
  maxZoom: 19,
  subdomains: 'abcd'
}).addTo(map);

// Un marker composite par station : deux demi-cercles (méca / élec) approximés
// par deux cercles superposés avec rayon proportionnel, + tooltip texte.
const markers = {};

function radiusFor(count) {
  if (count <= 0) return 3;
  return 4 + Math.sqrt(count) * 3;
}

for (const [id, st] of Object.entries(STATIONS)) {
  const mechCircle = L.circleMarker([st.lat, st.lon], {
    radius: 4, color: '#ff8fc7', fillColor: '#ff8fc7', fillOpacity: 0.75, weight: 1
  }).addTo(map);
  const elecCircle = L.circleMarker([st.lat, st.lon], {
    radius: 4, color: '#7fd4f5', fillColor: '#7fd4f5', fillOpacity: 0.6, weight: 1
  }).addTo(map);
  const tooltip = L.tooltip({ direction: 'top', offset: [0, -6] });
  mechCircle.bindTooltip(tooltip);
  markers[id] = { mechCircle, elecCircle, name: st.name };
}

function fmtTimestamp(ts) {
  // ts est ISO UTC style 2026-08-14T18:00:00Z -> affichage local FR
  const d = new Date(ts);
  return d.toLocaleString('fr-FR', {
    weekday: 'short', day: '2-digit', month: '2-digit',
    hour: '2-digit', minute: '2-digit'
  });
}

function renderFrame(idx) {
  const ts = TIMESTAMPS[idx];
  document.getElementById('timeLabel').textContent = fmtTimestamp(ts);
  const frame = DATA[ts] || {};

  for (const [id, m] of Object.entries(markers)) {
    const d = frame[id];
    if (!d) {
      m.mechCircle.setRadius(3);
      m.elecCircle.setRadius(0);
      m.mechCircle.setTooltipContent(`${m.name}<br>Pas de données`);
      continue;
    }
    m.mechCircle.setRadius(radiusFor(d.mechanical));
    m.elecCircle.setRadius(radiusFor(d.electrical));
    m.mechCircle.setLatLng(m.mechCircle.getLatLng());
    m.mechCircle.setTooltipContent(
      `<strong>${m.name}</strong><br>` +
      `Méca: ${d.mechanical} · Élec: ${d.electrical}<br>` +
      `Total: ${d.total} · Places libres: ${d.docks}`
    );
  }
}

const slider = document.getElementById('slider');
slider.max = TIMESTAMPS.length - 1;

slider.addEventListener('input', () => renderFrame(parseInt(slider.value)));

let playing = false;
let playInterval = null;
const playBtn = document.getElementById('playBtn');

playBtn.addEventListener('click', () => {
  playing = !playing;
  playBtn.textContent = playing ? '⏸' : '▶';
  if (playing) {
    playInterval = setInterval(() => {
      let v = parseInt(slider.value) + 1;
      if (v > TIMESTAMPS.length - 1) v = 0;
      slider.value = v;
      renderFrame(v);
    }, 250);
  } else {
    clearInterval(playInterval);
  }
});

renderFrame(0);
</script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="velocite_log.csv")
    parser.add_argument("--stations", default="stations.json")
    parser.add_argument("--out", default="carte_velocite.html")
    args = parser.parse_args()

    stations = load_stations(args.stations)
    timestamps, data = load_log(args.csv)

    html = HTML_TEMPLATE
    html = html.replace("__STATIONS_JSON__", json.dumps(stations, ensure_ascii=False))
    html = html.replace("__TIMESTAMPS_JSON__", json.dumps(timestamps))
    html = html.replace("__DATA_JSON__", json.dumps(data, ensure_ascii=False))

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Carte générée: {args.out} ({len(timestamps)} instantanés, {len(stations)} stations)")


if __name__ == "__main__":
    main()
