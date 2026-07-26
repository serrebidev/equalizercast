const statusNode = document.querySelector('#status');
const bandsNode = document.querySelector('#bands');
const outputNode = document.querySelector('#output-control');
const toneButton = document.querySelector('#tone-toggle');
const toneState = document.querySelector('#tone-state');
const toneFrequency = document.querySelector('#tone-frequency');
const toneRange = document.querySelector('#tone-frequency-range');
const toneLevel = document.querySelector('#tone-level');
const presetSelect = document.querySelector('#preset');
const presetDescription = document.querySelector('#preset-description');
const bandCount = document.querySelector('#band-count');
let values = {};
let bands = [];
let equalizer = {};
let presetData = {frequencies: [], presets: []};
let toneOn = false;
const saveTimers = new Map();

function announce(message, error = false) {
  statusNode.textContent = message;
  statusNode.dataset.error = error ? 'true' : 'false';
}

async function post(path, body = {}) {
  const response = await fetch(path, {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-Equalizer-Request': '1'},
    body: JSON.stringify(body)
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

function scheduleSet(name, value, label) {
  clearTimeout(saveTimers.get(name));
  saveTimers.set(name, setTimeout(async () => {
    try {
      await post('/api/set', {name, value});
      values[name] = value;
      announce(`${label} set to ${value}. Live and saved.`);
    } catch (error) {
      announce(`Could not set ${label}: ${error.message}`, true);
    }
  }, 80));
}

function addControl(parent, {name, label, min, max, step, unit}, value) {
  const box = document.createElement('div');
  box.className = 'control';
  const id = `control-${name.replaceAll('.', '-')}`;
  const labelNode = document.createElement('label');
  labelNode.htmlFor = id;
  labelNode.textContent = label;
  const range = document.createElement('input');
  range.id = id;
  range.type = 'range';
  Object.assign(range, {min, max, step, value});
  const number = document.createElement('input');
  number.type = 'number';
  number.setAttribute('aria-label', `${label} exact value`);
  Object.assign(number, {min, max, step, value});
  const unitNode = document.createElement('span');
  unitNode.textContent = ` ${unit}`;
  const update = source => {
    const next = Number(source.value);
    range.value = next;
    number.value = next;
    scheduleSet(name, next, label);
  };
  range.addEventListener('input', () => update(range));
  number.addEventListener('change', () => update(number));
  box.append(labelNode, range, number, unitNode);
  parent.append(box);
  return box;
}

function addBandControl(band, index) {
  const name = `eq.band.${index}.gain`;
  const box = addControl(
    bandsNode,
    {name, label: `Band ${index + 1}: ${formatHz(band.frequency)}`, min: equalizer.gain_min,
      max: equalizer.gain_max, step: equalizer.gain_step, unit: 'dB'},
    band.gain
  );
  const gainInputs = box.querySelectorAll('input');
  for (const input of gainInputs) {
    input.addEventListener(input.type === 'range' ? 'input' : 'change', () => {
      band.gain = Number(input.value);
    });
  }
  const settings = document.createElement('div');
  settings.className = 'band-settings';
  const frequencyLabel = document.createElement('label');
  frequencyLabel.textContent = 'Frequency (Hz)';
  const frequency = document.createElement('input');
  frequency.type = 'number';
  Object.assign(frequency, {min: equalizer.frequency_min, max: equalizer.frequency_max, step: 1, value: band.frequency});
  frequency.addEventListener('change', () => { band.frequency = Number(frequency.value); });
  frequencyLabel.append(frequency);
  const qLabel = document.createElement('label');
  qLabel.textContent = 'Q (width)';
  const q = document.createElement('input');
  q.type = 'number';
  Object.assign(q, {min: equalizer.q_min, max: equalizer.q_max, step: equalizer.q_step, value: band.q});
  q.addEventListener('change', () => { band.q = Number(q.value); });
  qLabel.append(q);
  settings.append(frequencyLabel, qLabel);
  box.append(settings);
}

function formatHz(frequency) {
  return frequency >= 1000 ? `${Number((frequency / 1000).toFixed(2))} kHz` : `${Number(frequency.toFixed(1))} Hz`;
}

function renderBands() {
  bandsNode.replaceChildren();
  bands.forEach(addBandControl);
  bandCount.value = bands.length;
}

function interpolate(points, pointValues, frequency) {
  if (frequency <= points[0]) return pointValues[0];
  if (frequency >= points.at(-1)) return pointValues.at(-1);
  const target = Math.log(frequency);
  for (let index = 1; index < points.length; index++) {
    if (frequency <= points[index]) {
      const left = Math.log(points[index - 1]);
      const right = Math.log(points[index]);
      const ratio = (target - left) / (right - left);
      return pointValues[index - 1] + ratio * (pointValues[index] - pointValues[index - 1]);
    }
  }
  return pointValues.at(-1);
}

function resampleBands(count) {
  const first = bands.length > 1 ? bands[0].frequency : 32;
  const last = bands.length > 1 ? bands.at(-1).frequency : 16000;
  const frequencies = count === 1
    ? [Math.round(Math.sqrt(first * last))]
    : Array.from({length: count}, (_, index) => Math.round(first * Math.pow(last / first, index / (count - 1))));
  const oldFrequencies = bands.map(band => band.frequency);
  return frequencies.map(frequency => ({
    frequency,
    gain: Number(interpolate(oldFrequencies, bands.map(band => band.gain), frequency).toFixed(2)),
    q: Number(interpolate(oldFrequencies, bands.map(band => band.q), frequency).toFixed(2))
  }));
}

async function replaceBands(nextBands, message) {
  for (const timer of saveTimers.values()) clearTimeout(timer);
  saveTimers.clear();
  const result = await post('/api/bands', {bands: nextBands});
  bands = result.bands;
  renderBands();
  announce(message);
}

function selectedPreset() {
  return presetData.presets[Number(presetSelect.value)];
}

function showPresetDescription() {
  const preset = selectedPreset();
  presetDescription.textContent = preset ? preset.description : '';
}

function populatePresets() {
  const groups = new Map();
  presetData.presets.forEach((preset, index) => {
    if (!groups.has(preset.category)) {
      const group = document.createElement('optgroup');
      group.label = preset.category;
      groups.set(preset.category, group);
      presetSelect.append(group);
    }
    const option = document.createElement('option');
    option.value = index;
    option.textContent = preset.name;
    groups.get(preset.category).append(option);
  });
  showPresetDescription();
}

document.querySelector('#save-layout').addEventListener('click', async () => {
  try {
    const sorted = bands.map(band => ({...band})).sort((left, right) => left.frequency - right.frequency);
    await replaceBands(sorted, `Applied and saved ${sorted.length} customized bands.`);
  } catch (error) {
    announce(`Could not apply band layout: ${error.message}`, true);
  }
});

document.querySelector('#set-band-count').addEventListener('click', async () => {
  const count = Number(bandCount.value);
  if (!Number.isInteger(count) || count < equalizer.min_bands || count > equalizer.max_bands) {
    return announce(`Band count must be between ${equalizer.min_bands} and ${equalizer.max_bands}.`, true);
  }
  try {
    await replaceBands(resampleBands(count), `Band count changed to ${count}. Live and saved.`);
  } catch (error) {
    announce(`Could not change band count: ${error.message}`, true);
  }
});

presetSelect.addEventListener('change', showPresetDescription);
document.querySelector('#apply-preset').addEventListener('click', async () => {
  const preset = selectedPreset();
  if (!preset) return;
  const keepLayout = document.querySelector('#keep-layout').checked;
  const frequencies = keepLayout ? bands.map(band => band.frequency) : presetData.frequencies;
  const next = frequencies.map((frequency, index) => ({
    frequency,
    gain: Number((keepLayout
      ? interpolate(presetData.frequencies, preset.gains, frequency)
      : preset.gains[index]).toFixed(2)),
    q: keepLayout ? bands[index].q : 1
  }));
  try {
    await replaceBands(next, `${preset.name} preset applied. Live and saved.`);
  } catch (error) {
    announce(`Could not apply preset: ${error.message}`, true);
  }
});

function hzToSlider(hz) {
  return Math.round(Math.log(hz / 20) / Math.log(1000) * 1000);
}

function sliderToHz(value) {
  return Math.round(20 * Math.pow(1000, value / 1000));
}

function dbToLinear(db) {
  return Math.pow(10, db / 20);
}

async function setToneParameter(name, value, label) {
  try {
    await post('/api/set', {name, value});
    announce(`${label} set to ${value}.`);
  } catch (error) {
    announce(`Could not set ${label}: ${error.message}`, true);
  }
}

toneRange.addEventListener('input', () => {
  const hz = sliderToHz(Number(toneRange.value));
  toneFrequency.value = hz;
  scheduleSet('eq.tone.frequency', hz, 'Tone frequency');
});

toneFrequency.addEventListener('change', () => {
  const hz = Math.min(20000, Math.max(20, Number(toneFrequency.value)));
  toneFrequency.value = hz;
  toneRange.value = hzToSlider(hz);
  setToneParameter('eq.tone.frequency', hz, 'Tone frequency');
});

toneLevel.addEventListener('change', () => {
  setToneParameter('eq.tone.amplitude', dbToLinear(Number(toneLevel.value)), 'Tone level');
});

toneButton.addEventListener('click', async () => {
  try {
    toneOn = !toneOn;
    await post('/api/tone', {enabled: toneOn});
    toneButton.setAttribute('aria-pressed', String(toneOn));
    toneButton.textContent = toneOn ? 'Stop on-air tone' : 'Start on-air tone';
    toneState.textContent = toneOn
      ? 'Tone is ON AIR. Automatic stop in 30 seconds.'
      : 'Tone is off; music is on air.';
    if (toneOn) setTimeout(() => {
      toneOn = false;
      toneButton.setAttribute('aria-pressed', 'false');
      toneButton.textContent = 'Start on-air tone';
      toneState.textContent = 'Tone auto-stopped; music is on air.';
    }, 30500);
  } catch (error) {
    toneOn = false;
    announce(`Tone control failed: ${error.message}`, true);
  }
});

document.querySelector('#reset').addEventListener('click', async () => {
  if (!confirm('Reset every EQ band, its layout, and output gain to the installed curve?')) return;
  try {
    await post('/api/reset');
    location.reload();
  } catch (error) {
    announce(`Reset failed: ${error.message}`, true);
  }
});

async function load() {
  try {
    const response = await fetch('/api/state', {cache: 'no-store'});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const state = await response.json();
    values = state.values;
    bands = state.bands;
    equalizer = state.controls.equalizer;
    presetData = state.presets;
    const output = state.controls.output;
    addControl(outputNode, output, values[output.name]);
    renderBands();
    populatePresets();
    toneFrequency.value = values['eq.tone.frequency'];
    toneRange.value = hzToSlider(values['eq.tone.frequency']);
    toneLevel.value = (20 * Math.log10(values['eq.tone.amplitude'])).toFixed(1);
    announce(`Connected. ${presetData.presets.length} presets available; changes are live and auto-saved.`);
  } catch (error) {
    announce(`Connection failed: ${error.message}`, true);
  }
}

load();
