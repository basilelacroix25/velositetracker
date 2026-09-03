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
  #map { position: absolute; top: 0; bottom: 96px; left: 0; right: 0; background: #f2f2f0; }
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
    min-width: 168px;
  }
  .legend div.row2 { display: flex; align-items: center; gap: 6px; margin: 3px 0; }
  .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
  .mode-group { margin-top: 8px; padding-top: 8px; border-top: 1px solid #e2e2e2; }
  .mode-group label { display: block; font-size: 12.5px; margin: 3px 0; cursor: pointer; }
  .spark-title { font-size: 11px; color: #666; margin-top: 6px; margin-bottom: 2px; }
  .spark-empty { font-size: 11px; color: #999; font-style: italic; }
  .tooltip-body { font-size: 13px; line-height: 1.4; }
  .circulation-panel {
    position: absolute; top: 10px; left: 10px; background: white; padding: 10px 14px;
    border-radius: 8px; box-shadow: 0 1px 6px rgba(0,0,0,0.3); font-size: 13px; z-index: 1000;
    width: 230px;
  }
  .circulation-panel .subtitle { font-size: 11px; color: #666; margin: 2px 0 6px; line-height: 1.3; }
</style>
</head>
<body>
<div id="map"></div>
<div class="circulation-panel">
  <strong>Vélos en circulation</strong>
  <div class="subtitle">Estimation sur 24h glissantes — plus la courbe est haute, plus il y a de vélos hors des stations</div>
  <div id="circulationChart"></div>
</div>
<div class="legend">
  <strong>Vélos disponibles</strong>
  <div class="row2"><span class="dot" style="background:#ff8fc7"></span> Mécanique</div>
  <div class="row2"><span class="dot" style="background:#7fd4f5"></span> Électrique</div>
  <div class="row2"><span class="dot" style="background:#fff; border:2px solid #111; box-sizing:border-box; width:8px; height:8px;"></span> Station vide</div>
  <div style="margin-top:4px; font-size:12px; color:#555;">Anneau extérieur = total<br>Cercle intérieur = la plus petite des deux valeurs</div>
  <div class="mode-group">
    <label><input type="radio" name="mode" value="both" checked> Tout (fusionné)</label>
    <label><input type="radio" name="mode" value="elec"> Électrique seul</label>
    <label><input type="radio" name="mode" value="mech"> Mécanique seul</label>
  </div>
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

const MECH_COLOR = '#ff8fc7';
const ELEC_COLOR = '#7fd4f5';
const WINDOW_MS = 24 * 3600 * 1000; // fenêtre du mini-graphique : 24h

const map = L.map('map').setView([47.238, 6.022], 14);
L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
  attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
  maxZoom: 19,
  subdomains: 'abcd'
}).addTo(map);

let currentIndex = 0;
let MODE = 'both'; // 'both' | 'elec' | 'mech'

// Taille = base + valeur × facteur (échelle linéaire, pas un simple plancher)
// afin de garantir un écart visible entre l'anneau extérieur et le cercle
// intérieur dès que les deux catégories diffèrent — même sur de petites
// valeurs (ex: total=3, plus petite=1 → rayons 9 et 5, pas 3 et 3).
const RADIUS_BASE = 3;
const RADIUS_SCALE = 2;
function radiusFor(count) {
  return RADIUS_BASE + count * RADIUS_SCALE;
}

function fmtTimestamp(ts) {
  const d = new Date(ts);
  return d.toLocaleString('fr-FR', {
    weekday: 'short', day: '2-digit', month: '2-digit',
    hour: '2-digit', minute: '2-digit'
  });
}

// Construit un mini sparkline SVG (méca + élec) sur les 24h précédant idx
function buildSparkline(stationId, idx) {
  const endTs = TIMESTAMPS[idx];
  const endTime = Date.parse(endTs);
  const points = [];

  for (let i = idx; i >= 0; i--) {
    const ts = TIMESTAMPS[i];
    const t = Date.parse(ts);
    if (endTime - t > WINDOW_MS) break;
    const d = (DATA[ts] || {})[stationId];
    if (d) points.push({ t, mech: d.mechanical, elec: d.electrical });
  }
  points.reverse();

  if (points.length < 2) {
    return '<div class="spark-empty">Historique insuffisant (&lt; 24h de données)</div>';
  }

  const W = 160, H = 46, PAD = 3;
  let maxVal = 1;
  for (const p of points) maxVal = Math.max(maxVal, p.mech, p.elec);

  const xStep = (W - 2 * PAD) / (points.length - 1);
  const yFor = (v) => H - PAD - (v / maxVal) * (H - 2 * PAD);

  const mechPts = points.map((p, i) => `${(PAD + i * xStep).toFixed(1)},${yFor(p.mech).toFixed(1)}`).join(' ');
  const elecPts = points.map((p, i) => `${(PAD + i * xStep).toFixed(1)},${yFor(p.elec).toFixed(1)}`).join(' ');
  const zeroY = yFor(0).toFixed(1);

  return `
    <div class="spark-title">Vélos dispo — 24h précédentes</div>
    <svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
      <line x1="${PAD}" y1="${zeroY}" x2="${W - PAD}" y2="${zeroY}"
            stroke="#bbb" stroke-width="1" stroke-dasharray="3,2" />
      <text x="${W - PAD}" y="${Number(zeroY) - 2}" font-size="8" fill="#999" text-anchor="end">station vide</text>
      <polyline points="${mechPts}" fill="none" stroke="${MECH_COLOR}" stroke-width="2" />
      <polyline points="${elecPts}" fill="none" stroke="${ELEC_COLOR}" stroke-width="2" />
    </svg>`;
}

function tooltipHtml(stationId, name) {
  const ts = TIMESTAMPS[currentIndex];
  const d = (DATA[ts] || {})[stationId];
  const header = d
    ? `Méca: ${d.mechanical} · Élec: ${d.electrical}<br>Total: ${d.total} · Places libres: ${d.docks}`
    : 'Pas de données à cet instant';
  return `<div class="tooltip-body"><strong>${name}</strong><br>${header}${buildSparkline(stationId, currentIndex)}</div>`;
}

// Graphique global : nombre estimé de vélos "en circulation" (hors stations),
// calculé comme (pic de vélos docké sur la fenêtre 24h) - (vélos dockés à l'instant t).
// C'est une estimation : on ne connaît pas la taille exacte de la flotte, donc
// on utilise le pic observé sur la fenêtre comme référence approximative
// (généralement atteint la nuit, quand quasi personne ne roule).
function buildCirculationChart(idx) {
  const endTs = TIMESTAMPS[idx];
  const endTime = Date.parse(endTs);
  const points = [];

  for (let i = idx; i >= 0; i--) {
    const ts = TIMESTAMPS[i];
    const t = Date.parse(ts);
    if (endTime - t > WINDOW_MS) break;
    const frame = DATA[ts];
    if (!frame) continue;
    let totalDocked = 0;
    let n = 0;
    for (const d of Object.values(frame)) { totalDocked += d.total; n++; }
    if (n > 0) points.push({ t, totalDocked });
  }
  points.reverse();

  if (points.length < 2) {
    return '<div class="spark-empty">Historique insuffisant (&lt; 24h de données)</div>';
  }

  const peakDocked = Math.max(...points.map(p => p.totalDocked));
  const series = points.map(p => ({ t: p.t, circulation: Math.max(0, peakDocked - p.totalDocked) }));

  const W = 200, H = 60, PAD = 4;
  const maxCirc = Math.max(1, ...series.map(p => p.circulation));
  const xStep = (W - 2 * PAD) / (series.length - 1);
  const yFor = (v) => H - PAD - (v / maxCirc) * (H - 2 * PAD);

  const pts = series.map((p, i) => `${(PAD + i * xStep).toFixed(1)},${yFor(p.circulation).toFixed(1)}`).join(' ');
  const areaPts = `${PAD},${H - PAD} ${pts} ${(W - PAD).toFixed(1)},${H - PAD}`;
  const current = series[series.length - 1].circulation;

  return `
    <div style="font-size:12px; margin-bottom:2px;">
      Actuellement : <strong>${current}</strong> vélo(s) estimé(s) hors stations
      <span style="color:#999;">(pic référence: ${peakDocked} dockés)</span>
    </div>
    <svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
      <polygon points="${areaPts}" fill="#ff8fc7" fill-opacity="0.15" stroke="none" />
      <polyline points="${pts}" fill="none" stroke="#e0559f" stroke-width="2" />
    </svg>`;
}

function updateCirculationPanel(idx) {
  document.getElementById('circulationChart').innerHTML = buildCirculationChart(idx);
}

// Deux cercles concentriques par station : "outer" (anneau, valeur la plus
// grande) et "inner" (toujours ramené au premier plan, valeur la plus
// petite) — ainsi la plus petite valeur n'est jamais masquée par la plus
// grande, quel que soit le sens (méca > élec ou l'inverse).
const markers = {};

for (const [id, st] of Object.entries(STATIONS)) {
  const outer = L.circleMarker([st.lat, st.lon], { weight: 1, fillOpacity: 0.8 }).addTo(map);
  const inner = L.circleMarker([st.lat, st.lon], { weight: 1, fillOpacity: 0.9 }).addTo(map);

  outer.bindTooltip(() => tooltipHtml(id, st.name), { direction: 'top', sticky: true });
  inner.bindTooltip(() => tooltipHtml(id, st.name), { direction: 'top', sticky: true });

  markers[id] = { outer, inner, name: st.name };
}

function renderFrame(idx) {
  currentIndex = idx;
  const ts = TIMESTAMPS[idx];
  document.getElementById('timeLabel').textContent = fmtTimestamp(ts);
  const frame = DATA[ts] || {};
  updateCirculationPanel(idx);

  for (const [id, m] of Object.entries(markers)) {
    const d = frame[id];
    if (!d) {
      m.outer.setStyle({ radius: 3, color: '#ccc', fillColor: '#ccc' });
      m.inner.setStyle({ radius: 0, opacity: 0, fillOpacity: 0 });
      continue;
    }

    const mech = d.mechanical, elec = d.electrical;

    if (MODE === 'elec') {
      if (elec === 0) {
        m.outer.setStyle({ radius: 5, color: '#111', fillColor: '#fff', weight: 2, opacity: 1, fillOpacity: 1 });
        m.inner.setStyle({ radius: 0, opacity: 0, fillOpacity: 0 });
      } else {
        m.outer.setStyle({ radius: radiusFor(elec), color: ELEC_COLOR, fillColor: ELEC_COLOR, weight: 1, opacity: 1, fillOpacity: 0.8 });
        m.inner.setStyle({ radius: 0, opacity: 0, fillOpacity: 0 });
      }
    } else if (MODE === 'mech') {
      if (mech === 0) {
        m.outer.setStyle({ radius: 5, color: '#111', fillColor: '#fff', weight: 2, opacity: 1, fillOpacity: 1 });
        m.inner.setStyle({ radius: 0, opacity: 0, fillOpacity: 0 });
      } else {
        m.outer.setStyle({ radius: radiusFor(mech), color: MECH_COLOR, fillColor: MECH_COLOR, weight: 1, opacity: 1, fillOpacity: 0.8 });
        m.inner.setStyle({ radius: 0, opacity: 0, fillOpacity: 0 });
      }
    } else if (mech === 0 && elec === 0) {
      // Station totalement vide : point noir creux plutôt que les deux cercles colorés
      m.outer.setStyle({ radius: 5, color: '#111', fillColor: '#fff', weight: 2, opacity: 1, fillOpacity: 1 });
      m.inner.setStyle({ radius: 0, opacity: 0, fillOpacity: 0 });
    } else {
      const total = mech + elec;
      const smaller = Math.min(mech, elec);
      const smallerIsMech = mech <= elec;
      const outerColor = smallerIsMech ? ELEC_COLOR : MECH_COLOR; // représente la plus grande valeur
      const innerColor = smallerIsMech ? MECH_COLOR : ELEC_COLOR; // toujours au premier plan

      m.outer.setStyle({ radius: radiusFor(total), color: outerColor, fillColor: outerColor, opacity: 1, fillOpacity: 0.75 });
      m.inner.setStyle({ radius: radiusFor(smaller), color: innerColor, fillColor: innerColor, opacity: 1, fillOpacity: 0.95 });
    }

    m.inner.bringToFront();
  }
}

const slider = document.getElementById('slider');
slider.max = TIMESTAMPS.length - 1;
slider.addEventListener('input', () => renderFrame(parseInt(slider.value)));

document.querySelectorAll('input[name="mode"]').forEach((radio) => {
  radio.addEventListener('change', (e) => {
    MODE = e.target.value;
    renderFrame(currentIndex);
  });
});

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
