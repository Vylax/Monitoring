const legendBox = document.getElementById('legend');
const windowSelect = document.getElementById('windowSelect');

const cpuCtx = document.getElementById('chartCpu').getContext('2d');
const memCtx = document.getElementById('chartMem').getContext('2d');
const procCtx = document.getElementById('chartProc').getContext('2d');

// Window mapping
const WINDOW_PRESETS_MS = {
  '5m': 5 * 60 * 1000,
  '30m': 30 * 60 * 1000,
  '1h': 60 * 60 * 1000,
  '4h': 4 * 60 * 60 * 1000,
  '12h': 12 * 60 * 60 * 1000,
  '1d': 24 * 60 * 60 * 1000,
  '3d': 3 * 24 * 60 * 60 * 1000,
  '1w': 7 * 24 * 60 * 60 * 1000,
  '1mo': 30 * 24 * 60 * 60 * 1000,
  '6mo': 182 * 24 * 60 * 60 * 1000,
  '1y': 365 * 24 * 60 * 60 * 1000,
};

let windowMs = WINDOW_PRESETS_MS['30m'];

const palette = [
  '#60a5fa', '#34d399', '#fbbf24', '#f87171', '#a78bfa', '#fb7185', '#22d3ee', '#f59e0b', '#10b981', '#f472b6',
];
function colorForIndex(i) { return palette[i % palette.length]; }

let datasetsByKey = {};

function makeChart(ctx, yLabel, yMax) {
  return new Chart(ctx, {
    type: 'line',
    data: { datasets: [] },
    options: {
      animation: false,
      parsing: false,
      normalized: true,
      responsive: true,
      maintainAspectRatio: false,
      devicePixelRatio: 1,
      interaction: { mode: 'nearest', axis: 'x', intersect: false },
      scales: {
        x: { type: 'time', time: { unit: 'minute' }, grid: { color: '#1f2937' }, ticks: { color: '#9ca3af' } },
        y: { beginAtZero: true, grid: { color: '#1f2937' }, ticks: { color: '#9ca3af' }, title: { display: true, text: yLabel } },
      },
      plugins: { legend: { display: false } },
    }
  });
}

const cpuChart = makeChart(cpuCtx, 'CPU (fraction)');
const memChart = makeChart(memCtx, 'Memory (MiB)');
const procChart = makeChart(procCtx, 'Processes');

function toMiB(bytes) { return bytes / 1024 / 1024; }

function updateLegend() {
  legendBox.innerHTML = '';
  Object.keys(datasetsByKey).forEach((key) => {
    const ds = datasetsByKey[key];
    const span = document.createElement('span');
    const dot = document.createElement('span');
    dot.className = 'dot';
    dot.style.background = ds.color;
    span.appendChild(dot);
    span.appendChild(document.createTextNode(ds.label));
    legendBox.appendChild(span);
  });
}

function ensureDatasets(key, label) {
  if (datasetsByKey[key]) return datasetsByKey[key];
  const color = colorForIndex(Object.keys(datasetsByKey).length);
  const dsCpu = { label, data: [], borderColor: color, backgroundColor: 'transparent', borderWidth: 2, pointRadius: 0, tension: 0.2 };
  const dsMem = { label, data: [], borderColor: color, backgroundColor: 'transparent', borderWidth: 2, pointRadius: 0, tension: 0.2 };
  const dsProc = { label, data: [], borderColor: color, backgroundColor: 'transparent', borderWidth: 2, pointRadius: 0, tension: 0.2 };
  cpuChart.data.datasets.push(dsCpu);
  memChart.data.datasets.push(dsMem);
  procChart.data.datasets.push(dsProc);
  datasetsByKey[key] = { label, color, dsCpu, dsMem, dsProc };
  updateLegend();
  return datasetsByKey[key];
}

function applySnapshot(snap) {
  const now = Date.now();
  const cutoff = now - windowMs;

  let cpuMaxWindow = 0;

  const seriesKeys = Object.keys(snap);
  for (const key of seriesKeys) {
    const s = snap[key];
    const bundle = ensureDatasets(key, s.display_name);
    const pts = s.points || [];
    const cpuData = pts.map(p => ({ x: p.t * 1000, y: (p.cpu || 0) / 100 })).filter(pt => pt.x >= cutoff);
    bundle.dsCpu.data = cpuData;
    bundle.dsMem.data = pts.map(p => ({ x: p.t * 1000, y: toMiB(p.mem || 0) })).filter(pt => pt.x >= cutoff);
    bundle.dsProc.data = pts.map(p => ({ x: p.t * 1000, y: p.process_count || 0 })).filter(pt => pt.x >= cutoff);
    for (const c of cpuData) { if (c.y > cpuMaxWindow) cpuMaxWindow = c.y; }
  }

  const dynMax = cpuMaxWindow > 0 ? cpuMaxWindow * 1.1 : 0.01;
  cpuChart.options.scales.y.max = dynMax;
  cpuChart.options.scales.y.suggestedMax = dynMax;

  [cpuChart, memChart, procChart].forEach((c) => {
    c.options.scales.x.min = cutoff;
    c.options.scales.x.max = now;
    c.update('none');
  });
}

windowSelect.addEventListener('change', () => {
  const val = windowSelect.value;
  windowMs = WINDOW_PRESETS_MS[val] || WINDOW_PRESETS_MS['30m'];
  fetch('/api/snapshot').then(r => r.json()).then(({data}) => applySnapshot(data));
});

// Initial snapshot
fetch('/api/snapshot').then(r => r.json()).then(({data}) => applySnapshot(data));

// Live updates via SSE
const evtSource = new EventSource('/events');
evtSource.onmessage = (evt) => {
  try {
    const payload = JSON.parse(evt.data);
    applySnapshot(payload.data);
  } catch (e) { /* ignore */ }
};

// Connect modal logic
const modal = document.getElementById('credsModal');
const btn = document.getElementById('credsBtn');
const cancel = document.getElementById('cancelBtn');
const save = document.getElementById('saveBtn');
const hostI = document.getElementById('hostInput');
const userI = document.getElementById('userInput');
const passI = document.getElementById('passInput');
const portI = document.getElementById('portInput');
const sslI = document.getElementById('sslInput');

btn.addEventListener('click', () => { modal.style.display = 'flex'; });
cancel.addEventListener('click', () => { modal.style.display = 'none'; });
save.addEventListener('click', async () => {
  const payload = {
    host: hostI.value || undefined,
    username: userI.value,
    password: passI.value,
    port: portI.value ? parseInt(portI.value, 10) : undefined,
    use_ssl: !!sslI.checked,
  };
  const r = await fetch('/api/winrm', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
  const j = await r.json();
  if (!j.ok) { alert('Error: ' + (j.error || 'unknown')); return; }
  modal.style.display = 'none';
});
