// All artwork and icons are drawn locally. The iris is decorative and has no data inputs.
const paths = {
  home: 'M3 10 12 3l9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z',
  nodes: 'M8 6h8M6 8v7m12-7v7M8 18h8',
  pulse: 'M2 12h5l3-8 4 16 3-8h5',
  book: 'M12 6c-3-2-6-2-9-1v14c3-1 6-1 9 1 3-2 6-2 9-1V5c-3-1-6-1-9 1zm0 0v14',
  history: 'M3 4v6h6M4 10a8 8 0 1 1 0 6m8-10v6l4 2',
  branch: 'M5 4v10a4 4 0 0 0 4 4h8M5 9h7a4 4 0 0 0 4-4V3m-2 13 3 2-3 2',
  message: 'M3 5h18v12H9l-5 4v-4H3zm4 4h10m-10 4h7',
  chart: 'M4 3v17h17M8 16v-5m5 5V6m5 10v-8',
  archive: 'M3 4h18v5H3zm2 5v11h14V9m-9 4h4',
  settings: 'M4 7h7m5 0h4M4 17h3m5 0h8',
  shield: 'm12 2 8 4v6c0 5-4 8-8 10-4-2-8-5-8-10V6zm-4 10 3 3 5-6',
  sun: 'M12 2v2m0 16v2M2 12h2m16 0h2M5 5l2 2m10 10 2 2M5 19l2-2M17 7l2-2',
  moon: 'M20 15a8 8 0 0 1-11-11A9 9 0 1 0 20 15z',
  arr: 'M5 12h14m-5-5 5 5-5 5',
  chev: 'm9 5 7 7-7 7',
  down: 'm6 9 6 6 6-6',
  plus: 'M12 5v14m-7-7h14',
  check: 'm4 12 5 5L20 6',
  close: 'm5 5 14 14M19 5 5 19',
  sync: 'M20 4v6h-6m6-1A8 8 0 0 0 5 7M4 20v-6h6m-6 1a8 8 0 0 0 15 2',
  lock: 'M5 10h14v11H5zm3 0V7a4 4 0 1 1 8 0v3m-4 4v3',
  plug: 'M8 3v4m8-4v4M5 7h14l-2 7-5 3-5-3zm7 10v4',
  grid: 'M3 3h7v7H3zm11 0h7v7h-7zM3 14h7v7H3zm11 0h7v7h-7z',
  clock: 'M12 6v6l4 3',
  leaf: 'M3 20c7-2 13-8 16-16M5 16C1 7 11 3 21 3c0 10-3 18-12 16',
  menu: 'M3 6h18M3 12h18M3 18h18',
  copy: 'M8 8h13v13H8zM17 8V3H3v14h5',
  download: 'M12 3v12m-5-5 5 5 5-5M3 15v6h18v-6',
  info: 'M12 11v6m0-11v1',
  globe: 'M2 12h20M12 3c-6 4-6 14 0 18 6-4 6-14 0-18',
  filter: 'M3 5h18l-7 8v6l-4 2v-8z',
  signal: 'M4 19v-3m5 3v-7m5 7V8m5 11V4',
  quote: 'M4 12h6v6H4v-5c0-4 2-6 5-7m5 6h6v6h-6v-5c0-4 2-6 5-7',
  activity: 'M3 19h18M3 12h3l3-6 4 10 3-5h5',
  user: 'M4 21v-2a8 8 0 0 1 16 0v2',
  database: 'M3 6v12c0 5 18 5 18 0V6M3 12c0 5 18 5 18 0',
  file: 'M5 2h9l5 5v15H5zm9 0v6h5M8 13h8m-8 4h6'
};
const circles = {
  nodes: [[5, 5, 2.6], [19, 5, 2.6], [5, 18, 2.6], [19, 18, 2.6]],
  settings: [[13, 7, 2.5], [9, 17, 2.5]],
  sun: [[12, 12, 4]],
  clock: [[12, 12, 9]],
  info: [[12, 12, 9]],
  globe: [[12, 12, 9]],
  user: [[12, 7, 4]]
};
export function icon(name, size = 18) {
  const dots = (circles[name] || []).map(([x, y, r]) => '<circle cx="' + x + '" cy="' + y + '" r="' + r + '"/>').join('');
  return '<svg class="icon" width="' + size + '" height="' + size
    + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    + dots + '<path d="' + (paths[name] || paths.info) + '"/>'
    + (name === 'database' ? '<ellipse cx="12" cy="6" rx="9" ry="3"/>' : '') + '</svg>';
}
export function drawIris(canvas, light = false) {
  if (!canvas) return;
  const rect = canvas.getBoundingClientRect();
  const w = rect.width,
    h = rect.height;
  if (!w || !h) return;
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = w * ratio;
  canvas.height = h * ratio;
  const c = canvas.getContext('2d');
  if (!c) return;
  c.scale(ratio, ratio);
  const cx = w * .55,
    cy = h * .50,
    size = Math.min(w * .29, h * .385);
  // Each curve is a different latitude on one folded toroidal surface.
  const tilt = -.46;
  c.lineJoin = 'round';
  c.lineCap = 'round';
  const project = (u, v) => {
    const r = (1 + .305 * Math.cos(v)) * (1 + .16 * Math.cos(3 * u + v * .65));
    const x = r * Math.cos(u),
      y = r * Math.sin(u),
      z = .34 * Math.sin(v) + .35 * Math.sin(2 * u - v * .68);
    const yy = y * .67 + z * .87;
    return [cx + (x * Math.cos(tilt) - yy * Math.sin(tilt)) * size, cy + (x * Math.sin(tilt) + yy * Math.cos(tilt)) * size];
  };
  const glow = c.createRadialGradient(cx, cy, 0, cx, cy, size * 1.7);
  glow.addColorStop(0, light ? 'rgba(159,114,185,.13)' : 'rgba(164,106,191,.16)');
  glow.addColorStop(1, 'rgba(126,86,149,0)');
  c.fillStyle = glow;
  c.fillRect(0, 0, w, h);
  for (let j = 0; j < 108; j++) {
    const v = j / 108 * Math.PI * 2,
      wave = (Math.cos(v - .4) + 1) / 2;
    const gradient = c.createLinearGradient(cx - size, cy - size * .5, cx + size, cy + size * .6);
    gradient.addColorStop(0, light ? 'rgba(83,52,128,.44)' : 'rgba(186,144,237,' + (.20 + wave * .40) + ')');
    gradient.addColorStop(.46, light ? 'rgba(140,86,144,.41)' : 'rgba(224,184,239,' + (.22 + wave * .48) + ')');
    gradient.addColorStop(.76, light ? 'rgba(173,123,80,.6)' : 'rgba(249,217,168,' + (.24 + wave * .52) + ')');
    gradient.addColorStop(1, light ? 'rgba(107,78,140,.25)' : 'rgba(156,127,203,.3)');
    c.strokeStyle = gradient;
    c.lineWidth = j % 8 === 0 ? .97 : .54;
    c.beginPath();
    for (let i = 0; i <= 200; i++) {
      const [x, y] = project(i / 200 * Math.PI * 2, v);
      i ? c.lineTo(x, y) : c.moveTo(x, y);
    }
    c.stroke();
  }
  const ink = light ? 'rgba(99,73,113,.28)' : 'rgba(232,208,248,.29)';
  c.strokeStyle = ink;
  c.lineWidth = .62;
  c.setLineDash([2, 7]);
  c.beginPath();
  c.ellipse(cx, cy, size * 1.70, size * .71, -.36, 0, Math.PI * 2);
  c.stroke();
  c.setLineDash([]);
  [[.18, .27], [.89, .23], [.84, .76], [.11, .71]].forEach(([x, y], i) => {
    c.fillStyle = ink;
    c.beginPath();
    c.arc(x * w, y * h, i % 2 ? 1.6 : 1.0, 0, Math.PI * 2);
    c.fill();
  });
}
