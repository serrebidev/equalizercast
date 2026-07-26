#!/usr/bin/env python3
"""Generate the Liquidsoap block consumed by EqualizerCast."""

import json
from pathlib import Path


config = json.loads((Path(__file__).parent / "controls.json").read_text())
equalizer = config["equalizer"]
bands = config["bands"]

print("""# EqualizerCast runtime controls. Insert after `radio` is defined.
eq_tone_enabled = interactive.bool("eq.tone.enabled", description="On-air engineering tone", false)
eq_tone_frequency = interactive.float("eq.tone.frequency", min=20.0, max=20000.0, step=1.0, description="Tone frequency", unit="Hz", 1000.0)
eq_tone_amplitude = interactive.float("eq.tone.amplitude", min=0.001, max=0.5012, step=0.001, description="Tone amplitude", unit="linear", 0.1259)
def eq_tone_level() = if eq_tone_enabled() then eq_tone_amplitude() else 0.0 end end
eq_test_tone = sine(id="eq_test_tone", amplitude=eq_tone_level, eq_tone_frequency)
eq_program_tracks = source.tracks(radio)
eq_mixed_audio = track.audio.add(normalize=false, [eq_program_tracks.audio, source.tracks(eq_test_tone).audio])
radio = source({audio=eq_mixed_audio, metadata=eq_program_tracks.metadata, track_marks=eq_program_tracks.track_marks})""")

print(
    f'eq_band_count = interactive.float("eq.band.count", min=0.0, '
    f'max={equalizer["max_bands"]:.1f}, step=1.0, description="Active EQ bands", '
    f'{len(bands):.1f})'
)
print(
    'eq_band_revision = interactive.float("eq.band.revision", min=0.0, '
    'max=4294967295.0, step=1.0, description="EQ state fingerprint", 0.0)'
)

for index in range(equalizer["max_bands"]):
    band = bands[index] if index < len(bands) else {"frequency": 1000, "gain": 0, "q": 1}
    frequency = band["frequency"]
    frequency_variable = f"eq_band_frequency_{index}"
    gain_variable = f"eq_band_gain_{index}"
    q_variable = f"eq_band_q_{index}"
    effective_gain = f"eq_band_effective_gain_{index}"
    print(
        f'{frequency_variable} = interactive.float("eq.band.{index}.frequency", '
        f'min={equalizer["frequency_min"]:.1f}, max={equalizer["frequency_max"]:.1f}, '
        f'step=1.0, description="EQ band {index + 1} frequency", unit="Hz", {frequency:.1f})'
    )
    print(
        f'{gain_variable} = interactive.float("eq.band.{index}.gain", '
        f'min={equalizer["gain_min"]:.1f}, max={equalizer["gain_max"]:.1f}, '
        f'step={equalizer["gain_step"]}, description="EQ band {index + 1} gain", '
        f'unit="dB", {band["gain"]:.2f})'
    )
    print(
        f'{q_variable} = interactive.float("eq.band.{index}.q", '
        f'min={equalizer["q_min"]:.1f}, max={equalizer["q_max"]:.1f}, '
        f'step={equalizer["q_step"]}, description="EQ band {index + 1} Q", {band["q"]:.2f})'
    )
    print(
        f"def {effective_gain}() = if eq_band_count() > {index:.1f} then "
        f"{gain_variable}() else 0.0 end end"
    )
    print(
        f"radio = filter.iir.eq.peak(frequency={frequency_variable}, "
        f"gain={effective_gain}, q={q_variable}, radio)"
    )

output = config["output"]
print(
    f'eq_output_gain = interactive.float("{output["name"]}", min={output["min"]}, '
    f'max={output["max"]}, step={output["step"]}, description="Final output gain", '
    f'unit="linear", {output["value"]})'
)
print('radio = amplify(id="equalizercast_output", override=null, eq_output_gain, radio)')
