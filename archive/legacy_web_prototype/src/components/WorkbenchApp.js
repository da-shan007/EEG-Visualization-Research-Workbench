export function WorkbenchApp(dataset) {
  const app = document.createElement('div');
  app.className = 'app-shell';

  const sidebar = document.createElement('aside');
  sidebar.className = 'sidebar';
  sidebar.innerHTML = `
    <div class="brand-block">
      <div class="brand-mark">EEG</div>
      <div>
        <h1>Workbench</h1>
        <p>Research Interface</p>
      </div>
    </div>

    <div class="panel">
      <h2>Acquisition</h2>

      <label class="control">
        <span>Channel Select</span>
        <select id="channelSelect">
          ${dataset.channels.map((channel, index) => `<option value="${index}">${channel}</option>`).join('')}
        </select>
      </label>

      <label class="control">
        <span>Filter</span>
        <select id="filterMode">
          <option value="none">None</option>
          <option value="smooth">Smooth</option>
          <option value="notch">Notch</option>
        </select>
      </label>

      <label class="control">
        <span>Window</span>
        <div class="value-row">
          <input id="windowSize" type="range" min="1000" max="12000" step="250" value="4000" />
          <strong>4.0 s</strong>
        </div>
      </label>
    </div>

    <div class="panel" style="margin-top: 16px;">
      <button class="primary" id="togglePlayback">Pause</button>
      <button id="randomizeSignal" style="margin-top: 12px;">Randomize</button>
    </div>
  `;

  const main = document.createElement('main');
  main.className = 'main-panel';
  main.innerHTML = `
    <header class="topbar">
      <div>
        <p class="eyebrow">Signal Overview</p>
        <h2>Realtime EEG Monitor</h2>
      </div>
      <div class="status-pill"><span class="dot"></span>Live</div>
    </header>

    <section class="metrics-grid">
      <article class="metric-card accent-blue">
        <span>Signal Quality</span>
        <strong id="signalQualityValue">94.2%</strong>
      </article>
      <article class="metric-card accent-green">
        <span>Alpha Power</span>
        <strong id="alphaPowerValue">13.4 dB</strong>
      </article>
      <article class="metric-card accent-purple">
        <span>Beta Power</span>
        <strong id="betaPowerValue">19.5 dB</strong>
      </article>
      <article class="metric-card accent-orange">
        <span>Artifact Index</span>
        <strong id="artifactValue">1.8%</strong>
      </article>
    </section>

    <section class="visual-grid">
      <div class="panel">
        <div class="panel-header">
          <h3>Waveform View</h3>
          <span>Channels: ${dataset.channels.length}</span>
        </div>
        <canvas id="waveformCanvas" width="980" height="430"></canvas>
      </div>

      <div class="panel">
        <div class="panel-header">
          <h3>Frequency Spectrum</h3>
        </div>
        <canvas id="spectrumCanvas" width="420" height="220"></canvas>
      </div>
    </section>

    <section class="bottom-grid">
      <div class="panel">
        <div class="panel-header">
          <h3>Topographic Map</h3>
        </div>
        <canvas id="topographyCanvas" width="820" height="220"></canvas>
      </div>

      <div class="panel">
        <div class="panel-header">
          <h3>Event Timeline</h3>
        </div>
        <div class="event-timeline">
          <div class="event-item"><span class="tag">Cue</span><span class="time">0.2 s</span></div>
          <div class="event-item"><span class="tag">Blink</span><span class="time">1.8 s</span></div>
          <div class="event-item"><span class="tag">Stimulus</span><span class="time">3.1 s</span></div>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-header">
        <h3>Channel Heatmap</h3>
        <span>Time × Channel</span>
      </div>
      <canvas id="heatmapCanvas" width="1180" height="220"></canvas>
    </section>
  `;

  app.appendChild(sidebar);
  app.appendChild(main);

  const waveformCanvas = main.querySelector('#waveformCanvas');
  const spectrumCanvas = main.querySelector('#spectrumCanvas');
  const topographyCanvas = main.querySelector('#topographyCanvas');
  const heatmapCanvas = main.querySelector('#heatmapCanvas');

  const waveformCtx = waveformCanvas.getContext('2d');
  const spectrumCtx = spectrumCanvas.getContext('2d');
  const topographyCtx = topographyCanvas.getContext('2d');
  const heatmapCtx = heatmapCanvas.getContext('2d');

  const channelSelect = sidebar.querySelector('#channelSelect');
  const filterMode = sidebar.querySelector('#filterMode');
  const togglePlayback = sidebar.querySelector('#togglePlayback');
  const randomizeSignal = sidebar.querySelector('#randomizeSignal');

  let activeChannel = 0;
  let playing = true;

  function smoothSeries(values) {
    const result = values.slice();
    for (let i = 0; i < result.length; i += 1) {
      let sum = 0;
      let count = 0;
      for (let j = -2; j <= 2; j += 1) {
        const idx = i + j;
        if (idx >= 0 && idx < result.length) {
          sum += result[idx];
          count += 1;
        }
      }
      result[i] = sum / count;
    }
    return result;
  }

  function renderWaveform() {
    waveformCtx.clearRect(0, 0, waveformCanvas.width, waveformCanvas.height);
    waveformCtx.fillStyle = '#09131f';
    waveformCtx.fillRect(0, 0, waveformCanvas.width, waveformCanvas.height);

    const data = dataset.series.map((series) => {
      const mode = filterMode.value;
      if (mode === 'smooth') return smoothSeries(series.values);
      if (mode === 'notch') {
        return series.values.map((value, i) => value - Math.sin(i / 10) * 0.3);
      }
      return series.values;
    });

    const channelCount = data.length;
    const spacing = (waveformCanvas.height - 60) / channelCount;

    data.forEach((series, idx) => {
      waveformCtx.beginPath();
      waveformCtx.strokeStyle = idx === activeChannel ? '#65b6ff' : 'rgba(148,164,181,0.8)';
      waveformCtx.lineWidth = idx === activeChannel ? 2 : 1;

      series.forEach((value, sampleIdx) => {
        const x = (sampleIdx / (series.length - 1)) * (waveformCanvas.width - 40) + 20;
        const y = 30 + idx * spacing + value * 9;
        if (sampleIdx === 0) waveformCtx.moveTo(x, y);
        else waveformCtx.lineTo(x, y);
      });
      waveformCtx.stroke();
    });
  }

  function renderSpectrum() {
    spectrumCtx.clearRect(0, 0, spectrumCanvas.width, spectrumCanvas.height);
    spectrumCtx.fillStyle = '#09131f';
    spectrumCtx.fillRect(0, 0, spectrumCanvas.width, spectrumCanvas.height);

    const values = [11, 17, 21, 14];
    const labels = ['Theta', 'Alpha', 'Beta', 'Gamma'];
    const max = Math.max(...values, 1);

    values.forEach((value, index) => {
      const x = 32 + index * 90;
      const barHeight = (value / max) * 140;
      const y = spectrumCanvas.height - 30 - barHeight;
      spectrumCtx.fillStyle = ['#65b6ff', '#63e7c3', '#b794ff', '#ffb86c'][index];
      spectrumCtx.fillRect(x, y, 40, barHeight);
      spectrumCtx.fillStyle = '#ebf4ff';
      spectrumCtx.font = '12px sans-serif';
      spectrumCtx.fillText(labels[index], x + 4, spectrumCanvas.height - 10);
    });
  }

  function renderTopography() {
    topographyCtx.clearRect(0, 0, topographyCanvas.width, topographyCanvas.height);
    topographyCtx.fillStyle = '#09131f';
    topographyCtx.fillRect(0, 0, topographyCanvas.width, topographyCanvas.height);

    const cx = topographyCanvas.width / 2;
    const cy = topographyCanvas.height / 2;
    const radius = 70;

    topographyCtx.beginPath();
    topographyCtx.arc(cx, cy, radius, 0, Math.PI * 2);
    topographyCtx.strokeStyle = 'rgba(155,177,199,0.3)';
    topographyCtx.stroke();

    const positions = [
      { label: 'Fp1', x: -1.2, y: -0.7 },
      { label: 'Fp2', x: 1.2, y: -0.7 },
      { label: 'C3', x: -1.1, y: 0.4 },
      { label: 'C4', x: 1.1, y: 0.4 },
      { label: 'P3', x: -0.8, y: 1.4 },
      { label: 'P4', x: 0.8, y: 1.4 },
      { label: 'O1', x: -0.5, y: 2.1 },
      { label: 'O2', x: 0.5, y: 2.1 }
    ];

    positions.forEach((pos, idx) => {
      const x = cx + pos.x * 55;
      const y = cy + pos.y * 42;
      topographyCtx.beginPath();
      topographyCtx.fillStyle = ['#65b6ff', '#63e7c3', '#b794ff', '#ffb86c', '#65b6ff', '#63e7c3', '#b794ff', '#ffb86c'][idx];
      topographyCtx.arc(x, y, 9, 0, Math.PI * 2);
      topographyCtx.fill();
      topographyCtx.fillStyle = '#ebf4ff';
      topographyCtx.font = '11px sans-serif';
      topographyCtx.fillText(pos.label, x - 12, y + 3);
    });
  }

  function renderHeatmap() {
    heatmapCtx.clearRect(0, 0, heatmapCanvas.width, heatmapCanvas.height);
    heatmapCtx.fillStyle = '#09131f';
    heatmapCtx.fillRect(0, 0, heatmapCanvas.width, heatmapCanvas.height);

    const rows = dataset.channels.length;
    const cols = 48;
    const cellW = (heatmapCanvas.width - 40) / cols;
    const cellH = (heatmapCanvas.height - 40) / rows;

    dataset.series.forEach((series, rowIndex) => {
      for (let col = 0; col < cols; col += 1) {
        const value = series.values[Math.floor((col / cols) * series.values.length)] ?? 0;
        const normalized = (value + 8) / 16;
        const hue = 210 - normalized * 120;
        heatmapCtx.fillStyle = `hsla(${hue}, 80%, 60%, ${0.35 + normalized * 0.7})`;
        heatmapCtx.fillRect(20 + col * cellW, 20 + rowIndex * cellH, cellW + 1, cellH + 1);
      }
    });
  }

  function renderMetrics() {
    const selected = dataset.series[activeChannel];
    const mean = selected.values.reduce((sum, value) => sum + value, 0) / selected.values.length;
    const variance = selected.values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / selected.values.length;
    const quality = Math.max(80, 100 - Math.sqrt(variance) * 3.5).toFixed(1);
    const alpha = (Math.sqrt(selected.values.reduce((sum, value) => sum + value * value, 0) / selected.values.length) * 6).toFixed(1);
    const beta = (parseFloat(alpha) * 1.4 + 6).toFixed(1);
    const artifact = (Math.sqrt(variance) * 0.5).toFixed(1);

    const signalQuality = document.getElementById('signalQualityValue');
    const alphaPower = document.getElementById('alphaPowerValue');
    const betaPower = document.getElementById('betaPowerValue');
    const artifactIndex = document.getElementById('artifactValue');

    signalQuality.textContent = `${quality}%`;
    alphaPower.textContent = `${alpha} dB`;
    betaPower.textContent = `${beta} dB`;
    artifactIndex.textContent = `${artifact}%`;
  }

  function renderAll() {
    renderWaveform();
    renderSpectrum();
    renderTopography();
    renderHeatmap();
    renderMetrics();
  }

  channelSelect.addEventListener('change', (event) => {
    activeChannel = Number(event.target.value);
    renderAll();
  });

  filterMode.addEventListener('change', renderAll);

  togglePlayback.addEventListener('click', () => {
    playing = !playing;
    togglePlayback.textContent = playing ? 'Pause' : 'Resume';
  });

  randomizeSignal.addEventListener('click', () => {
    dataset.series.forEach((series) => {
      series.values = series.values.map((value) => value + (Math.random() - 0.5) * 3);
    });
    renderAll();
  });

  renderAll();

  function tick() {
    if (playing) {
      dataset.series.forEach((series, idx) => {
        series.values = series.values.slice(1).concat(series.values[series.values.length - 1] + (Math.random() - 0.5) * 0.8 + idx * 0.02);
      });
      renderAll();
    }
    requestAnimationFrame(tick);
  }

  requestAnimationFrame(tick);

  return app;
}
