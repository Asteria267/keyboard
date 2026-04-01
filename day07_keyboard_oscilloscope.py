"""
BUILDCORED ORCAS — Day 07: KeyboardOscilloscope
================================================
Press keyboard keys to generate tones.
Hold multiple keys to form chords — each combination
produces a unique waveform visible on the live oscilloscope.

Hardware concept: DAC as Signal Source
  Your sound card is a DAC (Digital-to-Analog Converter).
  numpy generates the samples mathematically, sounddevice
  streams them to the DAC in real time. The oscilloscope
  shows the time-domain sum of all active sine waves —
  exactly what an analog oscilloscope displays when you
  plug in a synth.

KEY MAP (white keys):
  A  S  D  F  G  H  J  K  L
  C4 D4 E4 F4 G4 A4 B4 C5 D5

KEY MAP (black keys):
  W    E    T    Y    U    O
  C#4  D#4  F#4  G#4  A#4  C#5

WAVEFORM:   Tab  → cycle sine / triangle / square / sawtooth
VOLUME:     +/-  → adjust
QUIT:       Escape or close window

INSTALL:
  pip install pygame sounddevice numpy
"""

import pygame
import numpy as np
import sounddevice as sd
import threading
import collections
import sys

# ============================================================
# CONSTANTS
# ============================================================
SAMPLE_RATE  = 44100
CHUNK        = 512        # samples per audio callback (lower = less latency)
AMPLITUDE    = 0.25       # master volume (0.0 – 1.0)
SCREEN_W     = 900
SCREEN_H     = 540
SCOPE_H      = 300
FPS          = 60

# ── Note frequencies (equal temperament, A4 = 440 Hz) ──────
NOTES = {
    'C4': 261.63, 'D4': 293.66, 'E4': 329.63, 'F4': 349.23,
    'G4': 392.00, 'A4': 440.00, 'B4': 493.88, 'C5': 523.25,
    'D5': 587.33,
    'C#4': 277.18, 'D#4': 311.13, 'F#4': 369.99,
    'G#4': 415.30, 'A#4': 466.16, 'C#5': 554.37,
}

# ── Keyboard → note mapping ─────────────────────────────────
KEY_MAP = {
    pygame.K_a: 'C4',  pygame.K_s: 'D4',  pygame.K_d: 'E4',
    pygame.K_f: 'F4',  pygame.K_g: 'G4',  pygame.K_h: 'A4',
    pygame.K_j: 'B4',  pygame.K_k: 'C5',  pygame.K_l: 'D5',
    pygame.K_w: 'C#4', pygame.K_e: 'D#4', pygame.K_t: 'F#4',
    pygame.K_y: 'G#4', pygame.K_u: 'A#4', pygame.K_o: 'C#5',
}

WAVE_TYPES = ['sine', 'triangle', 'square', 'sawtooth']

CHORD_NAMES = {
    frozenset(['C4','E4','G4']):       'C major',
    frozenset(['D4','F#4','A4']):      'D major',
    frozenset(['E4','G#4','B4']):      'E major',
    frozenset(['F4','A4','C5']):       'F major',
    frozenset(['G4','B4','D5']):       'G major',
    frozenset(['A4','C#5','E4']):      'A major',
    frozenset(['C4','D#4','G4']):      'C minor',
    frozenset(['D4','F4','A4']):       'D minor',
    frozenset(['E4','G4','B4']):       'E minor',
    frozenset(['C4','E4','G4','B4']): 'Cmaj7',
    frozenset(['C4','E4','G4','A#4']):'C7',
    frozenset(['C4','G4']):            'C5 (power chord)',
    frozenset(['A4','E4']):            'A5 (power chord)',
}

# ============================================================
# AUDIO ENGINE
# ============================================================
class AudioEngine:
    """Generates and streams audio samples for active notes."""

    def __init__(self):
        self.active   = {}          # note -> phase accumulator
        self.lock     = threading.Lock()
        self.wave     = 'sine'
        self.volume   = AMPLITUDE
        self.scope_buf = collections.deque(maxlen=SAMPLE_RATE // 10)  # ~100ms

    def set_wave(self, w):
        self.wave = w

    def note_on(self, note):
        with self.lock:
            if note not in self.active:
                self.active[note] = 0.0   # phase

    def note_off(self, note):
        with self.lock:
            self.active.pop(note, None)

    def _generate(self, note, phase, n_samples):
        freq = NOTES[note]
        t    = phase + (np.arange(n_samples) * freq / SAMPLE_RATE)
        w    = self.wave

        if w == 'sine':
            wave = np.sin(2 * np.pi * t)
        elif w == 'triangle':
            wave = 2 * np.abs(2 * (t - np.floor(t + 0.5))) - 1
        elif w == 'square':
            wave = np.sign(np.sin(2 * np.pi * t))
        else:  # sawtooth
            wave = 2 * (t - np.floor(t + 0.5))

        new_phase = (phase + n_samples * freq / SAMPLE_RATE) % 1.0
        return wave.astype(np.float32), new_phase

    def callback(self, outdata, frames, time_info, status):
        with self.lock:
            notes = dict(self.active)

        if not notes:
            outdata[:] = 0
            self.scope_buf.extend([0.0] * frames)
            return

        mix = np.zeros(frames, dtype=np.float32)
        new_phases = {}
        for note, phase in notes.items():
            wave, new_phase = self._generate(note, phase, frames)
            mix += wave
            new_phases[note] = new_phase

        # Normalize to prevent clipping when chords are held
        n = len(notes)
        mix /= max(n, 1)
        mix *= self.volume

        with self.lock:
            for note, ph in new_phases.items():
                if note in self.active:
                    self.active[note] = ph

        self.scope_buf.extend(mix.tolist())
        outdata[:, 0] = mix

# ============================================================
# OSCILLOSCOPE RENDERER
# ============================================================
BG        = (13,  17,  23)
GRID      = (28,  33,  40)
SCOPE_COL = [(55, 139, 221), (102, 187, 106), (239, 159, 39), (212, 83, 126)]
WHITE     = (220, 222, 224)
GRAY      = (100, 108, 118)
DARK      = (22,  27,  34)
ACCENT    = (55,  139, 221)

def draw_scope(surface, buf, n_notes, rect):
    x, y, w, h = rect
    pygame.draw.rect(surface, DARK, rect, border_radius=8)

    # grid
    for i in range(1, 4):
        gy = y + h * i // 4
        pygame.draw.line(surface, GRID, (x, gy), (x + w, gy))
    for i in range(1, 8):
        gx = x + w * i // 8
        pygame.draw.line(surface, GRID, (gx, y), (gx, y + h))

    # center line
    cy = y + h // 2
    pygame.draw.line(surface, GRID, (x, cy), (x + w, cy), 1)

    data = list(buf)
    if not data:
        pygame.draw.line(surface, SCOPE_COL[0], (x, cy), (x + w, cy), 2)
        return

    color = SCOPE_COL[min(n_notes, len(SCOPE_COL) - 1)]
    step  = max(1, len(data) // w)
    pts   = []
    for i in range(w):
        idx  = min(i * step, len(data) - 1)
        samp = data[idx]
        sy   = int(cy - samp * (h // 2) * 0.9)
        sy   = max(y + 2, min(y + h - 2, sy))
        pts.append((x + i, sy))

    if len(pts) > 1:
        pygame.draw.lines(surface, color, False, pts, 2)

# ============================================================
# KEYBOARD RENDERER
# ============================================================
WHITE_NOTES = ['C4','D4','E4','F4','G4','A4','B4','C5','D5']
BLACK_NOTES = ['C#4','D#4',None,'F#4','G#4','A#4',None,'C#5',None]
BLACK_OFFSET = [0.65, 1.65, None, 3.65, 4.65, 5.65, None, 7.65, None]

def draw_keyboard(surface, active_notes, rect):
    x, y, w, h = rect
    key_w = w // len(WHITE_NOTES)
    bkey_w = int(key_w * 0.6)
    bkey_h = int(h * 0.6)

    # White keys
    for i, note in enumerate(WHITE_NOTES):
        kx = x + i * key_w
        pressed = note in active_notes
        color = (55, 139, 221) if pressed else (230, 232, 235)
        border = (55, 139, 221) if pressed else (160, 165, 170)
        pygame.draw.rect(surface, color, (kx+1, y, key_w-2, h), border_radius=4)
        pygame.draw.rect(surface, border, (kx+1, y, key_w-2, h), 1, border_radius=4)

        # Labels
        font_sm = pygame.font.SysFont('monospace', 10)
        kb_key  = [k for k, v in KEY_MAP.items() if v == note]
        if kb_key:
            kname = pygame.key.name(kb_key[0]).upper()
            lbl   = font_sm.render(kname, True, (80,88,96) if not pressed else WHITE)
            surface.blit(lbl, (kx + key_w//2 - lbl.get_width()//2, y + h - 22))
        nlbl = font_sm.render(note, True, (100,108,118) if not pressed else WHITE)
        surface.blit(nlbl, (kx + key_w//2 - nlbl.get_width()//2, y + h - 12))

    # Black keys
    for i, note in enumerate(BLACK_NOTES):
        if note is None:
            continue
        offset = BLACK_OFFSET[i]
        kx = int(x + offset * key_w)
        pressed = note in active_notes
        color = (55, 139, 221) if pressed else (28, 33, 40)
        pygame.draw.rect(surface, color, (kx, y, bkey_w, bkey_h), border_radius=3)
        pygame.draw.rect(surface, (60,66,72) if not pressed else (90,160,230),
                         (kx, y, bkey_w, bkey_h), 1, border_radius=3)
        font_xs = pygame.font.SysFont('monospace', 9)
        kb_key  = [k for k, v in KEY_MAP.items() if v == note]
        if kb_key:
            kname = pygame.key.name(kb_key[0]).upper()
            lbl   = font_xs.render(kname, True, (120,128,136) if not pressed else WHITE)
            surface.blit(lbl, (kx + bkey_w//2 - lbl.get_width()//2, y + bkey_h - 14))

# ============================================================
# MAIN
# ============================================================
def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("KeyboardOscilloscope — Day 07")
    clock  = pygame.time.Clock()

    font_lg = pygame.font.SysFont('monospace', 22)
    font_md = pygame.font.SysFont('monospace', 15)
    font_sm = pygame.font.SysFont('monospace', 12)

    engine = AudioEngine()
    wave_idx = 0

    stream = sd.OutputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype='float32',
        blocksize=CHUNK,
        callback=engine.callback,
    )
    stream.start()

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  🎹 KeyboardOscilloscope — Day 07")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  Keys : A S D F G H J K L  (white keys)")
    print("         W E T Y U O        (black keys)")
    print("  Tab  : cycle waveform")
    print("  +/-  : volume up/down")
    print("  Esc  : quit\n")

    running = True
    while running:
        clock.tick(FPS)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_TAB:
                    wave_idx = (wave_idx + 1) % len(WAVE_TYPES)
                    engine.set_wave(WAVE_TYPES[wave_idx])
                    print(f"  waveform → {WAVE_TYPES[wave_idx]}")
                elif event.key == pygame.K_EQUALS or event.key == pygame.K_PLUS:
                    engine.volume = min(1.0, round(engine.volume + 0.05, 2))
                elif event.key == pygame.K_MINUS:
                    engine.volume = max(0.0, round(engine.volume - 0.05, 2))
                elif event.key in KEY_MAP:
                    engine.note_on(KEY_MAP[event.key])

            elif event.type == pygame.KEYUP:
                if event.key in KEY_MAP:
                    engine.note_off(KEY_MAP[event.key])

        # ── DRAW ──────────────────────────────────────────
        screen.fill(BG)

        active = set(engine.active.keys())
        n      = len(active)

        # Header
        title = font_lg.render("KeyboardOscilloscope", True, WHITE)
        screen.blit(title, (20, 14))

        wave_lbl = font_md.render(f"waveform: {WAVE_TYPES[wave_idx]}  |  vol: {int(engine.volume*100)}%", True, GRAY)
        screen.blit(wave_lbl, (SCREEN_W - wave_lbl.get_width() - 20, 18))

        # Oscilloscope
        scope_rect = (20, 50, SCREEN_W - 40, SCOPE_H)
        draw_scope(screen, engine.scope_buf, n, scope_rect)

        # BPM / note info strip
        info_y = 50 + SCOPE_H + 10
        freq_str = '  '.join(f"{NOTES[nt]:.0f}Hz" for nt in sorted(active)) if active else '--'
        note_str = '  '.join(sorted(active)) if active else 'no keys pressed'
        chord    = CHORD_NAMES.get(frozenset(active), '')

        notes_lbl = font_md.render(f"notes: {note_str}", True, WHITE)
        freq_lbl  = font_md.render(f"freq:  {freq_str}", True, GRAY)
        screen.blit(notes_lbl, (20, info_y))
        screen.blit(freq_lbl,  (20, info_y + 20))

        if chord:
            chord_lbl = font_lg.render(chord, True, SCOPE_COL[min(n,3)])
            screen.blit(chord_lbl, (SCREEN_W - chord_lbl.get_width() - 20, info_y))

        # Keyboard
        kbd_rect = (20, info_y + 52, SCREEN_W - 40, 100)
        draw_keyboard(screen, active, kbd_rect)

        # Hint
        hint = font_sm.render("Tab = waveform  |  +/- = volume  |  hold keys for chords", True, GRID)
        screen.blit(hint, (SCREEN_W//2 - hint.get_width()//2, SCREEN_H - 18))

        pygame.display.flip()

    stream.stop()
    stream.close()
    pygame.quit()
    print("  See you tomorrow for Day 08! 🔥")
    sys.exit(0)

if __name__ == '__main__':
    main()
