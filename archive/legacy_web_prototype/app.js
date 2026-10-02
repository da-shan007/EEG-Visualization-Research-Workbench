const state = {
  channels: 8,
  channelNames: ['Fp1', 'Fp2', 'C3', 'C4', 'P3', 'P4', 'O1', 'O2'],
  windowMs: 4000,
  noiseLevel: 3,
  driftLevel: 2,
  gain: 1.0,
  playing: true,
  sampleRate: 250,
  drift: 0,
  signalSeed: 1,
  channelData: [],
  activeChannel: 0,
  filterMode: 'smooth',
  events: [
    { type: 'Cue', time: 0.2 },
    { type: 'Blink', time: 1.8 },
    { type: 'Stimulus', time: 3.1 }
  ],
  loadedFromCsv: false,
  datasetLabel: 'Synthetic EEG'
};

const channelSelect = document.getElementById('channelSelect');
const windowSizeInput = document.getElementById('windowSize');
const sampleRateInput = document.getElementById('sampleRate');
const filterModeInput = document.getElementById('filterMode');
const noiseLevelInput = document.getElementById('noiseLevel');
const driftLevelInput = document.getElementById('driftLevel');
const gainLevelInput = document.getElementById('gainLevel');
const fileInput = document.getElementById('fileInput');

const windowSizeValue = document.getElementById('windowSizeValue');
const noiseLevelValue = document.getElementById('noiseLevelValue');
const driftLevelValue = document.getElementById('driftLevelValue');
const gainLevelValue = document.getElementById('gainLevelValue');
const sampleRateValueDisplay = document.getElementById('sampleRateValueDisplay');
const waveformStatus = document.getElementById('waveformStatus');
const statusText = document.getElementById('statusText');

const waveformCanvas = document.getElementById('waveformCanvas');
const spectrumCanvas = document.getElementById('spectrumCanvas');
const topographyCanvas = document.getElementById('topographyCanvas');
const heatmapCanvas = document.getElementById('heatmapCanvas');
const waveformCtx = waveformCanvas.getContext('2d');
const spectrumCtx = spectrumCanvas.getContext('2d');
const topographyCtx = topographyCanvas.getContext('2d');
const heatmapCtx = heatmapCanvas.getContext('2d');

const togglePlaybackButton = document.getElementById('togglePlayback');
const randomizeButton = document.getElementById('randomizeSignal');
const eventTimeline = document.getElementById('eventTimeline');

const BAND_COLORS = ['#65b6ff', '#63e7c3', '#b794ff', '#ffb86c'];
const CHANNEL_COLORS = ['#65b6ff', '#63e7c3', '#b794ff', '#ffb86c', '#ff7b7b', '#7ae1ff', '#d9b3ff', '#8ef0d2'];
const ELECTRODE_POSITIONS = {
  Fp1: { x: -0.7, y: 0.8 },
  Fp2: { x: 0.7, y: 0.8 },
  C3: { x: -0.9, y: 0.1 },
  C4: { x: 0.9, y: 0.1 },
  P3: { x: -0.7, y: -0.8 },
  P4: { x: 0.7, y: -0.8 },
  O1: { x: -0.35, y: -1.1 },
  O2: { x: 0.35, y: -1.1 }
};

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function randomBetween(min, max) {
  return Math.random() * (max - min) + min;
}

function waveSample(t, frequency, amplitude, phase) {
  return Math.sin((t * frequency) + phase) * amplitude;
}

function formatSeconds(value) {
  return `${(value / 1000).toFixed(1)} s`;
}

function buildChannelSelect() {
  channelSelect.innerHTML = '';
  state.channelNames.forEach((name, index) => {
    const option = document.createElement('option');
    option.value = String(index);
    option.textContent = name;
    channelSelect.appendChild(option);
  });
  channelSelect.value = String(state.activeChannel);
}

function applyFilter(signal, mode) {
  if (mode === 'none') return signal.slice();

  const result = signal.slice();
  const windowSize = mode === 'smooth' ? 5 : 3;

  for (let i = 0; i < result.length; i += 1) {
    let sum = 0;
    let count = 0;
    for (let j = -windowSize; j <= windowSize; j += 1) {
      const idx = i + j;
      if (idx >= 0 && idx < result.length) {
        sum += result[idx];
        count += 1;
      }
    }
    result[i] = sum / count;
  }

  if (mode === 'notch') {
    for (let i = 0; i < result.length; i += 1) {
      const t = i / state.sampleRate;
      result[i] = result[i] - Math.sin(2 * Math.PI * 50 * t) * 0.15;
    }
  }

  return result;
}

function computeSpectrum(signal) {
  const n = signal.length;
  const magnitudes = [];
  for (let k = 0; k < Math.floor(n / 2); k += 1) {
    let real = 0;
    let imag = 0;
    for (let i = 0; i < n; i += 1) {
      const angle = (-2 * Math.PI * k * i) / n;
      real += signal[i] * Math.cos(angle);
      imag += signal[i] * Math.sin(angle);
    }
    const magnitude = Math.sqrt(real * real + imag * imag) / n;
    const frequency = (k * state.sampleRate) / n;
    if (frequency >= 1 && frequency <= 45) {
      magnitudes.push({ frequency, magnitude });
    }
  }
  return magnitudes;
}

function computeBandPowers(signal) {
  const spectrum = computeSpectrum(signal);
  const bands = { theta: 0, alpha: 0, beta: 0, gamma: 0 };

  spectrum.forEach(({ frequency, magnitude }) => {
    if (frequency >= 4 && frequency < 8) bands.theta += magnitude;
    if (frequency >= 8 && frequency < 13) bands.alpha += magnitude;
    if (frequency >= 13 && frequency < 30) bands.beta += magnitude;
    if (frequency >= 30 && frequency <= 45) bands.gamma += magnitude;
  });

  return bands;
}

function computeMetrics() {
  const allValues = state.channelData.flat();
  const mean = allValues.reduce((sum, value) => sum + value, 0) / allValues.length;
  const variance = allValues.reduce((sum, value) => sum + (value - mean) ** 2, 0) / allValues.length;
  const std = Math.sqrt(variance);
  const peakToPeak = Math.max(...allValues) - Math.min(...allValues);

  const selectedSeries = state.channelData[state.activeChannel] || state.channelData[0] || [];
  const bandPower = computeBandPowers(selectedSeries);
  const quality = clamp(100 - std * 0.9 - Math.abs(mean) * 0.15, 30, 100);
  const artifact = clamp((std * 0.8 + Math.abs(mean) * 0.5) / 4, 0.5, 99.9);

  return {
    quality: `${quality.toFixed(1)}%`,
    alphaPower: `${(bandPower.alpha * 18 + 6).toFixed(1)} dB`,
    betaPower: `${(bandPower.beta * 22 + 8).toFixed(1)} dB`,
    artifactIndex: `${artifact.toFixed(1)}%`
  };
}

function buildSyntheticSignals() {
  const sampleCount = Math.floor((state.windowMs / 1000) * state.sampleRate);
  state.channelData = [];

  for (let channel = 0; channel < state.channelNames.length; channel += 1) {
    const series = [];
    const alpha = randomBetween(8.5, 12.5);
    const beta = randomBetween(18, 29);
    const theta = randomBetween(4, 7.5);
    const gamma = randomBetween(30, 42);
    const phaseShift = randomBetween(0, Math.PI * 2);
    const amplitudeAlpha = randomBetween(3.5, 8.5);
    const amplitudeBeta = randomBetween(2.2, 5.4);
    const amplitudeTheta = randomBetween(2.0, 6.0);
    const amplitudeGamma = randomBetween(0.8, 2.2);
    const offset = randomBetween(-1.5, 1.5);

    for (let i = 0; i < sampleCount; i += 1) {
      const t = i / state.sampleRate;
      const baseline = Math.sin(t * 0.22 + channel * 0.5 + state.drift) * 0.7;
      const driftWave = Math.sin(t * 0.35 + channel * 0.9 + state.drift) * (state.driftLevel * 0.3);
      const signal =
        waveSample(t, alpha, amplitudeAlpha, phaseShift + channel * 0.4) +
        waveSample(t, beta, amplitudeBeta, phaseShift + 0.7 + channel * 0.25) +
        waveSample(t, theta, amplitudeTheta, phaseShift + 1.5 + channel * 0.35) +
        waveSample(t, gamma, amplitudeGamma, phaseShift + 2.2) +
        baseline +
        driftWave;

      const noise = (Math.random() - 0.5) * state.noiseLevel * 0.9;
      series.push((signal + offset + noise) * state.gain);
    }

    state.channelData.push(applyFilter(series, state.filterMode));
  }
}

function parseCsv(text) {
  const rawRows = text.split(/\r?\n/).filter((row) => row.trim() !== '');
  if (rawRows.length < 2) {
    return null;
  }

  const firstRow = rawRows[0].split(',').map((cell) => cell.trim());
  const headerLikely = firstRow.some((cell) => /[A-Za-z]/.test(cell));
  const startIndex = headerLikely ? 1 : 0;
  const headerLabels = headerLikely ? firstRow.slice(1) : null;
  const dataRows = rawRows.slice(startIndex).map((row) => row.split(',').map((cell) => cell.trim()));

  const numericRows = dataRows
    .map((row) => row.map((cell) => Number(cell)).filter((value) => !Number.isNaN(value)))
    .filter((row) => row.length > 1);

  if (!numericRows.length) {
    return null;
  }

  const channelCount = Math.max(1, Math.min(state.channelNames.length, numericRows[0].length - 1));
  const channels = Array.from({ length: channelCount }, () => []);

  numericRows.forEach((row) => {
    for (let i = 0; i < channelCount; i += 1) {
      const value = row[i + 1] ?? row[i];
      if (typeof value === 'number' && Number.isFinite(value)) {
        channels[i].push(value);
      }
    }
  });

  if (headerLabels && headerLabels.length) {
    state.channelNames = headerLabels.slice(0, channelCount).map((label) => label.replace(/['"]/g, '').trim() || `Ch${String(Math.random())}`);
  } else {
    state.channelNames = Array.from({ length: channelCount }, (_, idx) => `Ch${idx + 1}`);
  }

  return channels.filter((channel) => channel.length > 10);
}

function updateControls() {
  windowSizeValue.textContent = formatSeconds(state.windowMs);
  noiseLevelValue.textContent = `${state.noiseLevel}%`;
  driftLevelValue.textContent = `${state.driftLevel}%`;
  gainLevelValue.textContent = `${state.gain.toFixed(1)}x`;
  sampleRateValueDisplay.textContent = `${state.sampleRate} Hz`;
  waveformStatus.textContent = `Channels: ${state.channelNames.length}`;
}

function updateEventTimeline() {
  eventTimeline.innerHTML = '';
  state.events.forEach((event) => {
    const item = document.createElement('div');
    item.className = 'event-item';
    item.innerHTML = `<span class="tag">${event.type}</span><span class="time">${event.time.toFixed(1)} s</span>`;
    eventTimeline.appendChild(item);
  });
}

function drawWaveform() {
  const width = waveformCanvas.width;
  const height = waveformCanvas.height;
  const padding = 28;
  const channelCount = Math.max(1, state.channelData.length);
  const channelSpacing = (height - padding * 2) / channelCount;

  waveformCtx.clearRect(0, 0, width, height);
  waveformCtx.fillStyle = '#09131f';
  waveformCtx.fillRect(0, 0, width, height);

  waveformCtx.strokeStyle = 'rgba(155, 177, 199, 0.22)';
  waveformCtx.lineWidth = 1;
  for (let i = 0; i <= 5; i += 1) {
    const y = padding + ((height - padding * 2) * i) / 5;
    waveformCtx.beginPath();
    waveformCtx.moveTo(0, y);
    waveformCtx.lineTo(width, y);
    waveformCtx.stroke();
  }

  state.channelData.forEach((series, idx) => {
    const yOffset = padding + idx * channelSpacing + channelSpacing / 2;
    const ampScale = channelSpacing * 0.26;

    waveformCtx.beginPath();
    waveformCtx.strokeStyle = idx === state.activeChannel ? '#65b6ff' : 'rgba(148, 164, 181, 0.8)';
    waveformCtx.lineWidth = idx === state.activeChannel ? 2 : 1;

    series.forEach((value, xIndex) => {
      const x = (xIndex / Math.max(1, series.length - 1)) * (width - padding * 2) + padding;
      const y = yOffset + value * ampScale;
      if (xIndex === 0) {
        waveformCtx.moveTo(x, y);
      } else {
        waveformCtx.lineTo(x, y);
      }
    });
    waveformCtx.stroke();
  });

  const activeLabel = state.channelNames[state.activeChannel] || 'Channel';
  waveformCtx.fillStyle = '#dfeeff';
  waveformCtx.font = '12px sans-serif';
  waveformCtx.fillText(activeLabel, 10, 18);
}

function drawSpectrum() {
  const width = spectrumCanvas.width;
  const height = spectrumCanvas.height;
  const padding = 18;
  const selectedSeries = state.channelData[state.activeChannel] || state.channelData[0] || [];
  const bandPowers = computeBandPowers(selectedSeries);
  const values = [bandPowers.theta, bandPowers.alpha, bandPowers.beta, bandPowers.gamma];
  const maxValue = Math.max(...values, 1e-6);

  spectrumCtx.clearRect(0, 0, width, height);
  spectrumCtx.fillStyle = '#09131f';
  spectrumCtx.fillRect(0, 0, width, height);

  const barCount = values.length;
  const barWidth = (width - padding * 2) / barCount - 12;
  values.forEach((value, index) => {
    const x = padding + index * ((width - padding * 2) / barCount) + 6;
    const barHeight = (value / maxValue) * (height - padding * 2 - 16);
    const y = height - padding - barHeight;

    spectrumCtx.fillStyle = BAND_COLORS[index % BAND_COLORS.length];
    spectrumCtx.fillRect(x, y, barWidth, barHeight);

    spectrumCtx.fillStyle = '#dcecff';
    spectrumCtx.font = '12px sans-serif';
    spectrumCtx.fillText(['Theta', 'Alpha', 'Beta', 'Gamma'][index], x + 4, height - 8);
  });
}

function drawTopography() {
  const width = topographyCanvas.width;
  const height = topographyCanvas.height;
  const cx = width / 2;
  const cy = height / 2;
  const radius = Math.min(width, height) * 0.34;

  topographyCtx.clearRect(0, 0, width, height);
  topographyCtx.fillStyle = '#09131f';
  topographyCtx.fillRect(0, 0, width, height);

  topographyCtx.beginPath();
  topographyCtx.arc(cx, cy, radius, 0, Math.PI * 2);
  topographyCtx.strokeStyle = 'rgba(155,177,199,0.35)';
  topographyCtx.stroke();

  const powers = state.channelData.map((series) => Object.values(computeBandPowers(series)).reduce((sum, value) => sum + value, 0));
  const maxPower = Math.max(...powers, 1);

  state.channelNames.forEach((name, index) => {
    const placement = ELECTRODE_POSITIONS[name] || { x: (index % 2 ? 1 : -1) * 0.7, y: ((index % 4) - 1.5) * 0.5 };
    const x = cx + placement.x * radius * 1.35;
    const y = cy + placement.y * radius * 1.2;
    const value = powers[index] / maxPower;
    const alpha = clamp(value * 0.9 + 0.15, 0.2, 1);
    const hue = 210 - value * 90;

    topographyCtx.beginPath();
    topographyCtx.fillStyle = `hsla(${hue}, 80%, 62%, ${alpha})`;
    topographyCtx.arc(x, y, 12, 0, Math.PI * 2);
    topographyCtx.fill();

    topographyCtx.fillStyle = '#ebf4ff';
    topographyCtx.font = '11px sans-serif';
    topographyCtx.fillText(name, x - 10, y + 3);
  });
}

function drawHeatmap() {
  const width = heatmapCanvas.width;
  const height = heatmapCanvas.height;
  const margin = 25;
  const rows = state.channelNames.length;
  const cols = 48;

  heatmapCtx.clearRect(0, 0, width, height);
  heatmapCtx.fillStyle = '#09131f';
  heatmapCtx.fillRect(0, 0, width, height);

  const cellW = (width - margin * 2) / cols;
  const cellH = (height - margin * 2) / rows;

  for (let row = 0; row < rows; row += 1) {
    const series = state.channelData[row] || [];
    for (let col = 0; col < cols; col += 1) {
      const idx = Math.floor((col / cols) * Math.max(1, series.length));
      const value = series[idx] ?? 0;
      const normalized = clamp((value + 20) / 40, 0, 1);
      const hue = 210 - normalized * 120;
      heatmapCtx.fillStyle = `hsla(${hue}, 80%, 60%, ${0.25 + normalized * 0.7})`;
      heatmapCtx.fillRect(margin + col * cellW, margin + row * cellH, cellW + 1, cellH + 1);
    }
  }

  heatmapCtx.fillStyle = '#dcecff';
  heatmapCtx.font = '12px sans-serif';
  state.channelNames.forEach((name, idx) => {
    heatmapCtx.fillText(name, 8, margin + idx * cellH + 15);
  });
}

function render() {
  updateControls();
  drawWaveform();
  drawSpectrum();
  drawTopography();
  drawHeatmap();
  updateEventTimeline();

  const metrics = computeMetrics();
  document.getElementById('signalQualityValue').textContent = metrics.quality;
  document.getElementById('alphaPowerValue').textContent = metrics.alphaPower;
  document.getElementById('betaPowerValue').textContent = metrics.betaPower;
  document.getElementById('artifactValue').textContent = metrics.artifactIndex;
}

function onControlInput() {
  state.windowMs = Number(windowSizeInput.value);
  state.sampleRate = Number(sampleRateInput.value);
  state.filterMode = filterModeInput.value;
  state.noiseLevel = Number(noiseLevelInput.value);
  state.driftLevel = Number(driftLevelInput.value);
  state.gain = Number(gainLevelInput.value);
  state.drift += 0.2;
  buildSyntheticSignals();
  render();
}

function handleChannelChange() {
  state.activeChannel = Number(channelSelect.value);
  render();
}

function togglePlayback() {
  state.playing = !state.playing;
  togglePlaybackButton.textContent = state.playing ? 'Pause' : 'Resume';
  statusText.textContent = state.playing ? 'Live' : 'Paused';
}

function randomizeSignals() {
  state.signalSeed = Math.random() * 1000;
  state.drift += 0.6;
  buildSyntheticSignals();
  render();
}

function readCsvFile(event) {
  const file = event.target.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = (loadEvent) => {
    const parsed = parseCsv(loadEvent.target.result);
    if (!parsed || !parsed.length) {
      statusText.textContent = 'Invalid CSV';
      return;
    }

    state.channelData = parsed.map((signal) => applyFilter(signal, state.filterMode));
    state.channelNames = state.channelNames.slice(0, state.channelData.length);
    if (state.channelData.length > 0) {
      state.activeChannel = 0;
    }
    state.loadedFromCsv = true;
    statusText.textContent = `Loaded: ${file.name}`;
    buildChannelSelect();
    render();
  };
  reader.readAsText(file);
}

windowSizeInput.addEventListener('input', onControlInput);
sampleRateInput.addEventListener('input', onControlInput);
filterModeInput.addEventListener('change', onControlInput);
noiseLevelInput.addEventListener('input', onControlInput);
driftLevelInput.addEventListener('input', onControlInput);
gainLevelInput.addEventListener('input', onControlInput);
channelSelect.addEventListener('change', handleChannelChange);
togglePlaybackButton.addEventListener('click', togglePlayback);
randomizeButton.addEventListener('click', randomizeSignals);
fileInput.addEventListener('change', readCsvFile);

function animate() {
  if (state.playing && !state.loadedFromCsv) {
    state.signalSeed += 0.2;
    state.drift += 0.12;
    buildSyntheticSignals();
    render();
  }
  requestAnimationFrame(animate);
}

buildChannelSelect();
buildSyntheticSignals();
render();
requestAnimationFrame(animate);

