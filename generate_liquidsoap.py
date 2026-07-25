#!/usr/bin/env python3
"""Generate the Liquidsoap block consumed by EqualizerCast."""

import json
from pathlib import Path


config = json.loads((Path(__file__).parent / "controls.json").read_text())

print("""# EqualizerCast runtime controls. Insert after `radio` is defined.
eq_tone_enabled = interactive.bool("eq.tone.enabled", description="On-air engineering tone", false)
eq_tone_frequency = interactive.float("eq.tone.frequency", min=20.0, max=20000.0, step=1.0, description="Tone frequency", unit="Hz", 1000.0)
eq_tone_amplitude = interactive.float("eq.tone.amplitude", min=0.001, max=0.5012, step=0.001, description="Tone amplitude", unit="linear", 0.1259)
def eq_tone_level() = if eq_tone_enabled() then eq_tone_amplitude() else 0.0 end end
eq_test_tone = sine(id="eq_test_tone", amplitude=eq_tone_level, eq_tone_frequency)
eq_program_tracks = source.tracks(radio)
eq_mixed_audio = track.audio.add(normalize=false, [eq_program_tracks.audio, source.tracks(eq_test_tone).audio])
radio = source({audio=eq_mixed_audio, metadata=eq_program_tracks.metadata, track_marks=eq_program_tracks.track_marks})""")

for band in config["bands"]:
    frequency = band["frequency"]
    variable = f"eq_gain_{frequency}"
    print(
        f'{variable} = interactive.float("eq.gain.{frequency}", min=-6.0, max=6.0, '
        f'step=0.05, description="{frequency} Hz EQ gain", unit="dB", {band["gain"]:.2f})'
    )
    print(
        f"radio = filter.iir.eq.peak(frequency={frequency:.1f}, "
        f"gain={variable}, q={band['q']:.2f}, radio)"
    )

output = config["output"]
print(
    f'eq_output_gain = interactive.float("{output["name"]}", min={output["min"]}, '
    f'max={output["max"]}, step={output["step"]}, description="Final output gain", '
    f'unit="linear", {output["value"]})'
)
print('radio = amplify(id="equalizercast_output", override=null, eq_output_gain, radio)')

