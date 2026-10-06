import { useEffect, useRef } from "react";
import { geoEquirectangular, geoGraticule10, geoPath } from "d3-geo";
import { feature } from "topojson-client";
import land from "world-atlas/land-110m.json";
import { utilColor } from "../utils";

const W = 1200;
const H = 600;
const RED = "#ff4d4d";
const projection = geoEquirectangular().fitSize([W, H], { type: "Sphere" });
const landFeature = feature(land, land.objects.land);

// Add a segment to the current path; split it if it crosses the antimeridian.
function addSegment(ctx, a, b) {
  if (Math.abs(a[0] - b[0]) <= W / 2) {
    ctx.moveTo(a[0], a[1]);
    ctx.lineTo(b[0], b[1]);
  } else {
    const [l, r] = a[0] < b[0] ? [a, b] : [b, a];
    ctx.moveTo(l[0], l[1]);
    ctx.lineTo(r[0] - W, r[1]);
    ctx.moveTo(r[0], r[1]);
    ctx.lineTo(l[0] + W, l[1]);
  }
}

const pairKey = (a, b) => (a < b ? `${a}-${b}` : `${b}-${a}`);

function drawFrame(ctx, init, frame, selectedFlow) {
  const sats = frame.sats.map(([lat, lon]) => projection([lon, lat]));
  const stations = init.stations.map((s) => projection([s.lon, s.lat]));
  const nodePos = (id) => (id[0] === "S" ? sats[+id.slice(1)] : stations[+id.slice(1)]);

  const down = frame.failures ?? { sats: [], stations: [], isls: [] };
  const downSats = new Set(down.sats);
  const downStations = new Set(down.stations);
  const downIsls = new Set(down.isls.map(([a, b]) => pairKey(a, b)));

  // 1. faint ISL mesh (links touching failed satellites or failed links are hidden)
  ctx.beginPath();
  for (const [a, b] of init.isl_pairs) {
    if (downSats.has(a) || downSats.has(b) || downIsls.has(pairKey(a, b))) continue;
    addSegment(ctx, sats[a], sats[b]);
  }
  ctx.strokeStyle = "rgba(120,160,220,0.10)";
  ctx.lineWidth = 0.6;
  ctx.stroke();

  // 2. ISLs carrying traffic, colored by utilization
  for (const l of frame.loaded_links) {
    ctx.beginPath();
    addSegment(ctx, nodePos(l.u), nodePos(l.v));
    ctx.strokeStyle = utilColor(l.utilization);
    ctx.lineWidth = 1.5 + 2 * Math.min(1, l.utilization);
    ctx.stroke();
  }

  // 3. failed links
  if (down.isls.length) {
    ctx.beginPath();
    for (const [a, b] of down.isls) addSegment(ctx, sats[a], sats[b]);
    ctx.setLineDash([3, 3]);
    ctx.strokeStyle = RED;
    ctx.lineWidth = 1.4;
    ctx.stroke();
    ctx.setLineDash([]);
  }

  // 4. serving ground links
  ctx.setLineDash([5, 3]);
  for (const g of frame.ground_links) {
    ctx.beginPath();
    addSegment(ctx, stations[g.station], sats[g.sat]);
    ctx.strokeStyle = utilColor(g.utilization);
    ctx.lineWidth = 2;
    ctx.stroke();
  }
  ctx.setLineDash([]);

  // 5. selected flow route
  const path = selectedFlow?.reachable ? selectedFlow.path : null;
  if (path && path.length > 1) {
    ctx.beginPath();
    for (let i = 0; i < path.length - 1; i++) addSegment(ctx, nodePos(path[i]), nodePos(path[i + 1]));
    ctx.strokeStyle = "rgba(90,220,255,0.35)";
    ctx.lineWidth = 7;
    ctx.stroke();
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 2.2;
    ctx.stroke();
  }

  // 6. satellites
  const serving = new Set(frame.ground_links.map((g) => g.sat));
  const onPath = new Set((path ?? []).filter((id) => id[0] === "S").map((id) => +id.slice(1)));

  ctx.beginPath();
  sats.forEach((p, i) => {
    if (serving.has(i) || onPath.has(i) || downSats.has(i)) return;
    ctx.moveTo(p[0] + 1.6, p[1]);
    ctx.arc(p[0], p[1], 1.6, 0, 2 * Math.PI);
  });
  ctx.fillStyle = "#7aa2f7";
  ctx.fill();

  for (const [set, color, r] of [[serving, "#ffd166", 3.2], [onPath, "#ffffff", 3.8]]) {
    ctx.beginPath();
    set.forEach((i) => {
      const p = sats[i];
      ctx.moveTo(p[0] + r, p[1]);
      ctx.arc(p[0], p[1], r, 0, 2 * Math.PI);
    });
    ctx.fillStyle = color;
    ctx.fill();
  }

  if (downSats.size) {                                   // failed satellites: red ×
    ctx.beginPath();
    downSats.forEach((i) => {
      const [x, y] = sats[i];
      ctx.moveTo(x - 3.5, y - 3.5);
      ctx.lineTo(x + 3.5, y + 3.5);
      ctx.moveTo(x + 3.5, y - 3.5);
      ctx.lineTo(x - 3.5, y + 3.5);
    });
    ctx.strokeStyle = RED;
    ctx.lineWidth = 1.8;
    ctx.stroke();
  }

  // 7. ground stations
  ctx.font = "13px system-ui, sans-serif";
  init.stations.forEach((s, i) => {
    const p = stations[i];
    const isDown = downStations.has(i);
    ctx.beginPath();
    ctx.arc(p[0], p[1], 5, 0, 2 * Math.PI);
    ctx.fillStyle = isDown ? "#555" : "#ff6b6b";
    ctx.fill();
    ctx.strokeStyle = isDown ? RED : "#fff";
    ctx.lineWidth = isDown ? 2.5 : 1.5;
    ctx.stroke();
    ctx.fillStyle = isDown ? "#ff8a8a" : "#fff";
    ctx.fillText(isDown ? `${s.name} (down)` : s.name, p[0] + 9, p[1] + 4);
  });
}

export default function MapCanvas({ init, frame, selectedFlow }) {
  const baseRef = useRef(null);
  const overlayRef = useRef(null);

  // static layer: drawn once
  useEffect(() => {
    const ctx = baseRef.current.getContext("2d");
    const path = geoPath(projection, ctx);
    ctx.fillStyle = "#0b1220";
    ctx.fillRect(0, 0, W, H);
    ctx.beginPath();
    path(geoGraticule10());
    ctx.strokeStyle = "rgba(255,255,255,0.06)";
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.beginPath();
    path(landFeature);
    ctx.fillStyle = "#1c2a3f";
    ctx.fill();
    ctx.strokeStyle = "#2c4160";
    ctx.stroke();
  }, []);

  // per-frame layer
  useEffect(() => {
    const ctx = overlayRef.current.getContext("2d");
    ctx.clearRect(0, 0, W, H);
    if (init && frame) drawFrame(ctx, init, frame, selectedFlow);
  }, [init, frame, selectedFlow]);

  return (
    <div className="map-wrap">
      <canvas ref={baseRef} width={W} height={H} />
      <canvas ref={overlayRef} width={W} height={H} />
      <div className="legend">
        <span className="dot" style={{ background: "#7aa2f7" }} /> satellite
        <span className="dot" style={{ background: "#ffd166" }} /> serving
        <span className="dot" style={{ background: "#ff6b6b" }} /> station
        <span className="dot" style={{ background: "#fff" }} /> selected route
        <span className="dot" style={{ background: RED }} /> failed
        <span className="bar" /> link utilization 0 → 100%
      </div>
    </div>
  );
}