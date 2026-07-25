const statusNode = document.querySelector('#status');
const bandsNode = document.querySelector('#bands');
const outputNode = document.querySelector('#output-control');
const toneButton = document.querySelector('#tone-toggle');
const toneState = document.querySelector('#tone-state');
const toneFrequency = document.querySelector('#tone-frequency');
const toneRange = document.querySelector('#tone-frequency-range');
const toneLevel = document.querySelector('#tone-level');
let values = {};
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
}

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
  if (!confirm('Reset every EQ band and output gain to the installed curve?')) return;
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
    const output = state.controls.output;
    addControl(outputNode, output, values[output.name]);
    for (const band of state.controls.bands) {
      addControl(
        bandsNode,
        {name: `eq.gain.${band.frequency}`, label: `${band.frequency} Hz`, min: -6, max: 6, step: .05, unit: 'dB'},
        values[`eq.gain.${band.frequency}`]
      );
    }
    toneFrequency.value = values['eq.tone.frequency'];
    toneRange.value = hzToSlider(values['eq.tone.frequency']);
    toneLevel.value = (20 * Math.log10(values['eq.tone.amplitude'])).toFixed(1);
    announce('Connected. Changes are live and auto-saved.');
  } catch (error) {
    announce(`Connection failed: ${error.message}`, true);
  }
}

load();

