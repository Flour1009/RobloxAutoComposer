import argparse
import threading
import random
import time
from dataclasses import dataclass

import pydirectinput as di
import pygetwindow as gw
from pynput import keyboard


di.PAUSE = 0

WHITE_KEYS = list("1234567890qwertyuiopasdfghjklzxcvbnm")
DEGREE_ORDER = [0, 2, 4, 5, 7, 9, 11]
HAS_SHARP = {0, 2, 5, 7, 9}

NOTE_NAME_TO_PC = {
    "C": 0,
    "C#": 1,
    "DB": 1,
    "D": 2,
    "D#": 3,
    "EB": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "GB": 6,
    "G": 7,
    "G#": 8,
    "AB": 8,
    "A": 9,
    "A#": 10,
    "BB": 10,
    "B": 11,
}

PC_TO_NAME = {
    0: "C",
    1: "C#",
    2: "D",
    3: "D#",
    4: "E",
    5: "F",
    6: "F#",
    7: "G",
    8: "G#",
    9: "A",
    10: "A#",
    11: "B",
}

SCALES = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],
}

STYLE_PRESETS = {
    "pop": {
        "bpm": (92, 118),
        "rhythms": [
            [1, 1, 1, 1],
            [1, 0.5, 0.5, 1, 1],
            [0.5, 0.5, 1, 0.5, 0.5, 1],
            [1.5, 0.5, 1, 1],
            [0.5, 1, 0.5, 1, 1],
            [1, 1, 0.5, 0.5, 1],
        ],
        "melody_energy": 1.0,
        "bass_lengths": (1.2, 1.1),
        "arp_length": 0.42,
        "use_arp": True,
    },
    "ballad": {
        "bpm": (72, 90),
        "rhythms": [
            [1, 1, 1, 1],
            [1.5, 0.5, 1, 1],
            [2, 1, 1],
            [1, 1.5, 0.5, 1],
            [1, 1, 2],
        ],
        "melody_energy": 0.8,
        "bass_lengths": (1.5, 1.3),
        "arp_length": 0.55,
        "use_arp": True,
    },
    "ambient": {
        "bpm": (58, 74),
        "rhythms": [
            [2, 1, 1],
            [1.5, 0.5, 2],
            [1, 1, 2],
            [2, 2],
            [1, 1.5, 1.5],
        ],
        "melody_energy": 0.55,
        "bass_lengths": (1.8, 1.6),
        "arp_length": 0.65,
        "use_arp": False,
    },
}

MAJOR_PROGRESSIONS = [
    [0, 4, 5, 3],   # I-V-vi-IV
    [0, 5, 3, 4],   # I-vi-IV-V
    [0, 3, 4, 0],   # I-IV-V-I
    [5, 3, 0, 4],   # vi-IV-I-V
    [0, 2, 5, 4],   # I-iii-vi-V
]

MINOR_PROGRESSIONS = [
    [0, 5, 2, 6],   # i-VI-III-VII
    [0, 3, 4, 0],   # i-iv-v-i
    [0, 6, 5, 6],   # i-VII-VI-VII
    [5, 2, 0, 4],   # VI-III-i-v
]

MAJOR_ROMAN = ["I", "ii", "iii", "IV", "V", "vi", "viiÂ°"]
MINOR_ROMAN = ["i", "iiÂ°", "III", "iv", "v", "VI", "VII"]


@dataclass
class BeatNote:
    start_beat: float
    dur_beat: float
    degree: int
    velocity: int
    part: str


def build_chromatic_keyboard(white_keys):
    chroma = []
    degree_i = 0
    last_i = len(white_keys) - 1
    for i, k in enumerate(white_keys):
        chroma.append((k, False))
        degree = DEGREE_ORDER[degree_i]
        if i != last_i and degree in HAS_SHARP:
            chroma.append((k, True))
        degree_i = (degree_i + 1) % 7
    return chroma


CHROMA_KEYS = build_chromatic_keyboard(WHITE_KEYS)


def bring_roblox_to_front():
    titles = [t for t in gw.getAllTitles() if t and "roblox" in t.lower()]
    if not titles:
        return
    w = gw.getWindowsWithTitle(titles[0])[0]
    try:
        w.activate()
    except Exception:
        pass


def parse_hotkey(name: str):
    name = name.strip().lower()
    if len(name) == 1:
        return keyboard.KeyCode.from_char(name)

    aliases = {
        "esc": keyboard.Key.esc,
        "escape": keyboard.Key.esc,
        "space": keyboard.Key.space,
        "enter": keyboard.Key.enter,
        "return": keyboard.Key.enter,
        "tab": keyboard.Key.tab,
    }
    if name in aliases:
        return aliases[name]

    if name.startswith("f") and name[1:].isdigit():
        fnum = int(name[1:])
        k = getattr(keyboard.Key, f"f{fnum}", None)
        if k is not None:
            return k

    raise ValueError(f"Не понимаю клавишу: {name}")


def wait_for_key(key_name: str):
    target = parse_hotkey(key_name)

    def on_press(k):
        if k == target:
            return False

    with keyboard.Listener(on_press=on_press) as listener:
        listener.join()


def stop_listener(stop_key: str, stop_event: threading.Event):
    target = parse_hotkey(stop_key)

    def on_press(k):
        if k == target:
            stop_event.set()
            return False

    with keyboard.Listener(on_press=on_press) as listener:
        listener.join()


def parse_key_name(name: str):
    name = name.strip().upper().replace(" ", "")
    if name in NOTE_NAME_TO_PC:
        return NOTE_NAME_TO_PC[name]
    raise ValueError(f"Error: {name}")


def roman_progression(prog, scale_name: str):
    table = MAJOR_ROMAN if scale_name == "major" else MINOR_ROMAN
    return "-".join(table[d % 7] for d in prog)


def scale_degree_to_midi(tonic_midi: int, scale_name: str, degree: int):
    scale = SCALES[scale_name]
    octs, deg = divmod(degree, 7)
    return tonic_midi + (12 * octs) + scale[deg]


def chord_tone_classes(chord_degree: int):
    return {chord_degree % 7, (chord_degree + 2) % 7, (chord_degree + 4) % 7}


def nearest_degree_of_class(target_class: int, around: int, low: int, high: int):
    candidates = [d for d in range(low, high + 1) if d % 7 == target_class % 7]
    if not candidates:
        return around
    return min(candidates, key=lambda d: (abs(d - around), d))


def choose_anchor(prev_deg, chord_degree, center, low, high, rng, prefer_root=False):
    chord_classes = chord_tone_classes(chord_degree)
    best = None
    for d in range(low, high + 1):
        if d % 7 not in chord_classes:
            continue
        score = 0.0
        score -= 0.75 * abs(d - center)
        if prev_deg is not None:
            score -= 0.55 * abs(d - prev_deg)
        if d % 7 == chord_degree % 7:
            score += 1.1 if prefer_root else 0.35
        score += rng.random() * 0.35
        cand = (score, d)
        if best is None or cand > best:
            best = cand
    if best is None:
        return max(low, min(high, center))
    return best[1]


def make_interval_motif(note_count: int, rng, energy: float):
    if note_count <= 0:
        return []

    pos = 0
    motif = [0]
    if energy >= 0.95:
        steps = [-3, -2, -1, 0, 1, 2, 3]
        weights = [0.15, 0.9, 2.4, 1.8, 2.4, 0.9, 0.15]
    elif energy >= 0.7:
        steps = [-2, -1, 0, 1, 2]
        weights = [0.6, 2.2, 1.9, 2.2, 0.6]
    else:
        steps = [-2, -1, 0, 1, 2]
        weights = [0.35, 2.4, 2.6, 2.4, 0.35]

    for _ in range(note_count - 1):
        step = rng.choices(steps, weights=weights, k=1)[0]
        if abs(pos + step) > 5:
            step = -1 if pos > 0 else 1
        pos += step
        motif.append(pos)

    if note_count >= 4 and (max(motif) - min(motif) < 2):
        motif[-1] += 1
    return motif


def vary_motif(motif, rng, max_delta=1):
    if not motif:
        return []
    out = motif[:]
    idx = rng.randrange(1, len(out)) if len(out) > 1 else 0
    out[idx] += rng.choice([-max_delta, max_delta])
    out[idx] = max(-5, min(5, out[idx]))
    if len(out) > 4 and rng.random() < 0.35:
        idx2 = rng.randrange(1, len(out))
        out[idx2] += rng.choice([-1, 1])
        out[idx2] = max(-5, min(5, out[idx2]))
    return out


def realize_bar(
    bar_start,
    chord_degree,
    rhythm,
    motif,
    prev_deg,
    center,
    low,
    high,
    rng,
    end_target_class=None,
    final_bar=False,
):
    notes = []
    chord_classes = chord_tone_classes(chord_degree)
    anchor = choose_anchor(prev_deg, chord_degree, center, low, high, rng, prefer_root=True)

    t = 0.0
    local_prev = prev_deg
    for i, dur in enumerate(rhythm):
        desired = anchor + motif[min(i, len(motif) - 1)]
        cadence_target = None
        if i == len(rhythm) - 1 and end_target_class is not None:
            cadence_target = nearest_degree_of_class(end_target_class, desired, low, high)

        chosen = choose_note_for_slot(
            desired=desired,
            prev_deg=local_prev,
            chord_degree=chord_degree,
            chord_classes=chord_classes,
            beat_pos=t,
            low=low,
            high=high,
            rng=rng,
            cadence_target=cadence_target,
            final=final_bar and i == len(rhythm) - 1,
        )

        art = 0.93 if dur <= 1.0 else 0.97
        notes.append(BeatNote(bar_start + t, dur * art, chosen, 100, "melody"))
        local_prev = chosen
        t += dur

    return notes, local_prev


def make_section_pattern_set(label, memory_a, style_name, rng):
    rhythms = STYLE_PRESETS[style_name]["rhythms"]
    energy = STYLE_PRESETS[style_name]["melody_energy"]

    if label == "A" or memory_a is None:
        p1 = rng.choice(rhythms)
        p2 = rng.choice(rhythms)
        m1 = make_interval_motif(len(p1), rng, energy)
        m2 = make_interval_motif(len(p2), rng, energy)
        memory_a = {
            "patterns": (p1, p2),
            "motifs": (m1, m2),
            "center": 13,
        }
        return memory_a, [p1, p2, p1, p2], [m1, m2, m1[:], vary_motif(m2, rng)]

    p1, p2 = memory_a["patterns"]
    m1, m2 = memory_a["motifs"]

    if label == "A2":
        return memory_a, [p1, p2, p1, p2], [vary_motif(m1, rng), m2[:], vary_motif(m1, rng), vary_motif(m2, rng)]

    if label == "A3":
        return memory_a, [p1, p2, p1, p2], [m1[:], vary_motif(m2, rng), m1[:], vary_motif(m2, rng)]

    p3 = rng.choice(rhythms)
    p4 = rng.choice(rhythms)
    m3 = make_interval_motif(len(p3), rng, energy + 0.2)
    m4 = make_interval_motif(len(p4), rng, energy + 0.25)
    return memory_a, [p3, p4, p3, p4], [m3, m4, vary_motif(m3, rng), vary_motif(m4, rng)]


def choose_note_for_slot(
    desired,
    prev_deg,
    chord_degree,
    chord_classes,
    beat_pos,
    low,
    high,
    rng,
    cadence_target=None,
    final=False,
):
    strong = abs(beat_pos - round(beat_pos)) < 1e-6 and int(round(beat_pos)) in (0, 2)
    moderate = abs(beat_pos - round(beat_pos)) < 1e-6 and int(round(beat_pos)) in (1, 3)

    lo = max(low, desired - 4)
    hi = min(high, desired + 4)
    if lo > hi:
        lo, hi = low, high

    center = (low + high) / 2
    best = None

    for d in range(lo, hi + 1):
        dist_desired = abs(d - desired)
        score = -1.35 * dist_desired

        if prev_deg is not None:
            jump = abs(d - prev_deg)
            if jump == 0:
                score += 0.35
            elif jump in (1, 2):
                score += 1.15
            elif jump == 3:
                score += 0.2
            elif jump >= 5:
                score -= 2.3

        if d % 7 in chord_classes:
            if strong:
                score += 2.35
            elif moderate:
                score += 1.0
            else:
                score += 0.35
        else:
            score += 0.65 if not strong else -0.95

        if d % 7 == chord_degree % 7 and strong:
            score += 0.45

        if cadence_target is not None:
            score += 2.8 - 1.15 * abs(d - cadence_target)

        if final and d % 7 == 0:
            score += 2.25

        score -= 0.12 * abs(d - center)
        score += rng.random() * 0.35

        cand = (score, d)
        if best is None or cand > best:
            best = cand

    if best is None:
        return desired
    return best[1]


def generate_melody(section_labels, section_progressions, style_name, rng):
    events = []
    prev_deg = 12
    memory_a = None
    melody_low = 9
    melody_high = 18

    total_sections = len(section_labels)
    for sec_idx, label in enumerate(section_labels):
        progression = section_progressions[sec_idx]
        memory_a, patterns, motifs = make_section_pattern_set(label, memory_a, style_name, rng)

        if label == "B":
            center = memory_a["center"] + 2
        elif label == "A2":
            center = memory_a["center"] + 1
        else:
            center = memory_a["center"]

        for bar_in_section in range(4):
            bar_start = (sec_idx * 4 + bar_in_section) * 4.0
            chord_degree = progression[bar_in_section]

            if bar_in_section == 3:
                if sec_idx == total_sections - 1:
                    end_target_class = 0
                elif label == "B":
                    end_target_class = 4
                else:
                    end_target_class = 4
            else:
                end_target_class = None
            final_bar = sec_idx == total_sections - 1 and bar_in_section == 3
            center_bar = center + (1 if label == "B" and bar_in_section < 2 else 0)

            bar_notes, prev_deg = realize_bar(
                bar_start=bar_start,
                chord_degree=chord_degree,
                rhythm=patterns[bar_in_section],
                motif=motifs[bar_in_section],
                prev_deg=prev_deg,
                center=center_bar,
                low=melody_low,
                high=melody_high,
                rng=rng,
                end_target_class=end_target_class,
                final_bar=final_bar,
            )
            events.extend(bar_notes)

    return events


def generate_accompaniment(section_progressions, section_labels, style_name, rng):
    preset = STYLE_PRESETS[style_name]
    use_arp = preset["use_arp"]
    bass_len_1, bass_len_2 = preset["bass_lengths"]
    arp_len = preset["arp_length"]
    events = []

    for sec_idx, progression in enumerate(section_progressions):
        label = section_labels[sec_idx]
        for bar_in_section, chord_degree in enumerate(progression):
            bar_index = sec_idx * 4 + bar_in_section
            bar_start = bar_index * 4.0

            bass_root = nearest_degree_of_class(chord_degree, around=-5, low=-7, high=0)
            bass_fifth = nearest_degree_of_class((chord_degree + 4) % 7, around=-3, low=-7, high=1)

            if label == "B" and rng.random() < 0.35:
                bass_fifth = nearest_degree_of_class((chord_degree + 2) % 7, around=-3, low=-7, high=1)

            events.append(BeatNote(bar_start + 0.0, bass_len_1, bass_root, 74, "bass"))
            events.append(BeatNote(bar_start + 2.0, bass_len_2, bass_fifth, 72, "bass"))

            if not use_arp:
                continue

            arp_base = 4 if style_name == "ballad" else 3
            arp_pattern = [
                chord_degree,
                (chord_degree + 2) % 7,
                (chord_degree + 4) % 7,
                (chord_degree + 2) % 7,
            ]
            if label == "B":
                arp_pattern = [
                    chord_degree,
                    (chord_degree + 4) % 7,
                    (chord_degree + 2) % 7,
                    (chord_degree + 4) % 7,
                ]

            for off, deg_class in zip((0.5, 1.5, 2.5, 3.5), arp_pattern):
                arp_deg = nearest_degree_of_class(deg_class, around=arp_base, low=2, high=8)
                events.append(BeatNote(bar_start + off, arp_len, arp_deg, 66, "arp"))

    return events


def choose_progressions(scale_name: str, sections_count: int, rng):
    main_pool = MAJOR_PROGRESSIONS if scale_name == "major" else MINOR_PROGRESSIONS
    main = rng.choice(main_pool)
    alt = rng.choice(main_pool)

    final = [main[0], 3, 4, 0] if scale_name == "major" else [0, 3, 4, 0]

    labels = []
    progressions = []
    for sec in range(sections_count):
        if sec == 0:
            labels.append("A")
            progressions.append(main)
        elif sec == sections_count - 1:
            labels.append("A3")
            progressions.append(final)
        elif sections_count >= 3 and sec == sections_count - 2:
            labels.append("B")
            progressions.append(alt)
        else:
            labels.append("A2")
            progressions.append(main)

    return labels, progressions


def beat_notes_to_midi_events(beat_notes, tonic_midi, scale_name, bpm):
    sec_per_beat = 60.0 / bpm
    out = []
    for bn in beat_notes:
        start = bn.start_beat * sec_per_beat
        end = (bn.start_beat + bn.dur_beat) * sec_per_beat
        midi = scale_degree_to_midi(tonic_midi, scale_name, bn.degree)
        out.append((start, end, midi, bn.velocity, bn.part))
    out.sort(key=lambda x: (x[0], x[1], x[2]))
    return out


def build_actions(note_events, min_hold=0.05, max_hold=0.55):
    actions = []
    for s, e, n, _v, part in note_events:
        raw_dur = max(0.01, e - s)
        if part == "melody":
            dur = max(min_hold, min(max_hold, raw_dur))
        elif part == "bass":
            dur = max(min_hold, min(max_hold + 0.18, raw_dur))
        else:
            dur = max(min_hold, min(max_hold - 0.08, raw_dur))
        e2 = s + dur
        actions.append((s, 1, n))
        actions.append((e2, 0, n))
    actions.sort(key=lambda x: (x[0], x[1]))
    return actions


def note_to_key(note_midi: int, base_midi: int):
    idx = note_midi - base_midi
    if 0 <= idx < len(CHROMA_KEYS):
        return CHROMA_KEYS[idx]
    return None


def key_down(key: str, use_shift: bool):
    if use_shift:
        di.keyDown("shift")
        di.keyDown(key)
        di.keyUp("shift")
    else:
        di.keyDown(key)


def key_up(key: str, use_shift: bool):
    di.keyUp(key)


def build_song(args):
    seed = args.seed if args.seed >= 0 else int(time.time()) & 0xFFFFFFFF
    rng = random.Random(seed)

    style = args.style
    if style not in STYLE_PRESETS:
        raise ValueError(f"Не понятный стиль: {style}")

    if args.scale == "auto":
        scale_name = rng.choices(["major", "minor"], weights=[0.62, 0.38], k=1)[0]
    else:
        scale_name = args.scale

    if args.key.lower() == "auto":
        key_pc = rng.choice([0, 2, 4, 5, 7, 9, 11] if scale_name == "major" else [0, 2, 4, 5, 7, 9])
    else:
        key_pc = parse_key_name(args.key)

    bpm = args.bpm if args.bpm > 0 else rng.randint(*STYLE_PRESETS[style]["bpm"])

    bars = max(4, int(args.bars))
    if bars % 4 != 0:
        bars = ((bars + 3) // 4) * 4

    sections_count = max(1, bars // 4)
    section_labels, section_progressions = choose_progressions(scale_name, sections_count, rng)

    tonic_midi = args.base_midi + 12 + key_pc

    melody = generate_melody(section_labels, section_progressions, style, rng)
    accompaniment = generate_accompaniment(section_progressions, section_labels, style, rng)

    beat_notes = accompaniment + melody
    midi_events = beat_notes_to_midi_events(beat_notes, tonic_midi, scale_name, bpm)
    actions = build_actions(midi_events, min_hold=args.min_hold, max_hold=args.max_hold)

    all_notes = [midi for _, _, midi, _, _ in midi_events]
    in_range = sum(1 for n in all_notes if note_to_key(n, args.base_midi))

    info = {
        "seed": seed,
        "style": style,
        "scale": scale_name,
        "key_pc": key_pc,
        "key_name": PC_TO_NAME[key_pc],
        "bpm": bpm,
        "bars": bars,
        "section_labels": section_labels,
        "section_progressions": section_progressions,
        "tonic_midi": tonic_midi,
        "total_notes": len(all_notes),
        "in_range": in_range,
    }
    return actions, info


def play_actions(actions, base_midi, start_key, stop_key, speed, max_poly):
    print("Roblox: Windowed/Windowed Fullscreen → кликни по пианино → ENG раскладка.")
    bring_roblox_to_front()
    print(f"Start: {start_key.upper()} | Stop: {stop_key.upper()}")

    wait_for_key(start_key)

    stop_event = threading.Event()
    threading.Thread(target=stop_listener, args=(stop_key, stop_event), daemon=True).start()

    pressed = {}
    pressed_count = 0
    start_wall = time.time()

    try:
        di.press("/")
        time.sleep(0.1)
        di.write("Script by Skufupanda")
        time.sleep(0.1)
        di.press("enter")
        for t_action, kind, note in actions:
            if stop_event.is_set():
                break

            target = start_wall + (t_action * speed)
            now = time.time()
            if target > now:
                time.sleep(target - now)

            mapped = note_to_key(note, base_midi)
            if not mapped:
                continue
            key, use_shift = mapped

            if kind == 1:
                if note in pressed:
                    continue
                if pressed_count >= max_poly:
                    continue
                key_down(key, use_shift)
                pressed[note] = (key, use_shift)
                pressed_count += 1
            else:
                if note not in pressed:
                    continue
                k, sh = pressed.pop(note)
                key_up(k, sh)
                pressed_count = max(0, pressed_count - 1)
    finally:
        for _note, (k, sh) in list(pressed.items()):
            key_up(k, sh)


def main():
    ap = argparse.ArgumentParser(description="Roblox piano composer")
    ap.add_argument("--start-key", type=str, default="f8")
    ap.add_argument("--stop-key", type=str, default="f9")
    ap.add_argument("--speed", type=float, default=1.5, help=">1 медленнее, <1 быстрее")
    ap.add_argument("--style", choices=["pop", "ballad", "ambient"], default="pop")
    ap.add_argument("--scale", choices=["auto", "major", "minor"], default="auto")
    ap.add_argument("--key", type=str, default="auto", help="auto, C, D#, F, A...")
    ap.add_argument("--bars", type=int, default=16)
    ap.add_argument("--bpm", type=int, default=0)
    ap.add_argument("--seed", type=int, default=-1)
    ap.add_argument("--base-midi", type=int, default=36)
    ap.add_argument("--max-poly", type=int, default=3)
    ap.add_argument("--min-hold", type=float, default=0.05)
    ap.add_argument("--max-hold", type=float, default=0.55)
    args = ap.parse_args()

    try:
        actions, info = build_song(args)
    except Exception as e:
        print(f"Не вышло: {e}")
        return

    print("\n=== READY ===")
    print("\nScript by Skufupanda")
    print(f"seed        : {info['seed']}")
    print(f"style       : {info['style']}")
    print(f"key         : {info['key_name']} {info['scale']}")
    print(f"bpm         : {info['bpm']}")
    print(f"bars        : {info['bars']}")
    print(f"base_midi   : {args.base_midi}  (range {args.base_midi}..{args.base_midi + len(CHROMA_KEYS) - 1})")
    print(f"notes       : {info['total_notes']} | in_range: {info['in_range']}/{info['total_notes']}")
    print("sections    :")
    for label, prog in zip(info["section_labels"], info["section_progressions"]):
        print(f"  {label:>2} -> {roman_progression(prog, info['scale'])}")
    print("================\n")

    play_actions(
        actions=actions,
        base_midi=args.base_midi,
        start_key=args.start_key,
        stop_key=args.stop_key,
        speed=args.speed,
        max_poly=max(1, int(args.max_poly)),
    )

    print("DONE.")


if __name__ == "__main__":
    main()
