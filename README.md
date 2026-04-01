# 🎹 Day 07 — KeyboardOscilloscope

BuildCored Orcas · Day 07 🐳

Press keyboard keys to generate tones. Hold multiple keys to form chords — each combination produces a unique waveform visible live on the oscilloscope.

# What it does

| Feature | Status |

| Keyboard keys trigger tones | ✅ |
| Multiple keys held simultaneously form chords | ✅ |
| Live oscilloscope renders the summed waveform | ✅ |
| BPM / note / frequency info displayed | ✅ |
| Chord name detection (C major, D minor, etc.) | ✅ |
| 4 waveform types: sine, triangle, square, sawtooth | ✅ |
| Volume control | ✅ |

## Hardware concept

Your sound card is a **DAC (Digital-to-Analog Converter)**. `numpy` generates the waveform samples mathematically in software; 
`sounddevice` streams them to the DAC in real time at 44,100 samples/sec. 
The oscilloscope shows the **time-domain sum** of all active sine waves — exactly what you'd see on a real analog oscilloscope probed at the output of a synthesizer.

When you press multiple keys, the waveforms are **superimposed** (added sample-by-sample), 
and the resulting interference pattern is what gives each chord its unique "color."

keypress → numpy wave math → float32 sample buffer → sounddevice DAC → speaker
                                                                      ↓
                                                              scope_buf → pygame oscilloscope


## What I learned

- **DAC & real-time streaming** — `sounddevice` calls a callback every `CHUNK` samples (~11ms). 
The callback must fill the buffer synchronously or you get audio glitches.
- **Phase accumulation** — each oscillator tracks a floating-point phase (0.0–1.0) so waveforms stay continuous across buffer boundaries. 
Resetting phase on each callback would cause clicks.
- **Superposition** — summing N sine waves and dividing by N keeps amplitude normalized.
Without normalization, 4-note chords would clip and distort.
- **Hysteresis / envelope** — square and sawtooth waves have rich harmonics 
(visible as sharper edges on the scope) because they're mathematically equivalent to summing many sine waves at integer multiples of the fundamental frequency.
- **Time-domain vs frequency-domain** — the oscilloscope shows amplitude vs time. An FFT would show amplitude vs frequency (a spectrum analyzer). 
Both views come from the same audio buffer.

