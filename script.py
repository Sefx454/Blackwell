# Authors: Woody Churchward, Kahekili Spears, Jack O'Brien
# Date Created: 10/30/26
# Date Modified: 10/31/26
# Purpose: To create a fun game to play with friends


# Blackwell V16
from __future__ import annotations
import json
import heapq
import math
import os
import random
import time
import textwrap
import struct
import subprocess
import sys
import tempfile
import threading
import wave
import tkinter as tk
import traceback
from tkinter import messagebox
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

try:
    from PIL import Image, ImageDraw, ImageTk, ImageEnhance
except ImportError as exc:
    raise SystemExit(
        "Pillow is needed for the custom pixel-art renderer. "
        "Install it with: python3 -m pip install pillow"
    ) from exc

VERSION = "18"
SW, SH = 1440, 900
VIEW_X, VIEW_Y = 27, 89
VIEW_W, VIEW_H = 996, 690
PIXEL_SCALE = 3
WORLD_W, WORLD_H = 548, 374
VISIBLE_W = VIEW_W / PIXEL_SCALE
VISIBLE_H = VIEW_H / PIXEL_SCALE
STEP_INTERVAL = 1 / 30
SAVE_FILE = Path.home() / ".blackwell_ten_shadows_v3_save.json"
OLD_SAVE_FILE = Path.home() / ".blackwell_ten_shadows_save.json"

C = {
    "black": "#060e19",
    "midnight": "#071424",
    "panel": "#0c1b30",
    "panel_high": "#132943",
    "panel_light": "#1b3650",
    "edge": "#45627e",
    "thin": "#243d58",
    "gold": "#ddb56b",
    "gold_dim": "#9f835d",
    "ivory": "#f2e6ce",
    "muted": "#9eb1c3",
    "cyan": "#88cddc",
    "red": "#d27979",
    "green": "#80ba96",
    "paper": "#d8c29c",
    "ink": "#392b27",
    "pale": "#e7d3af",
    "warm": "#e5ae5c",
    "lamp": "#e8bc72",
    "earth": "#4b352e",
    "shadow": "#111622",
}

#Kahekili's PPR
def sfx(name):
    if name == "menu_select":
        pitch, waveform, duration, volume = 660, "square", 0.07, 0.18
    elif name == "deduction_correct":
        pitch, waveform, duration, volume = 880, "square", 0.14, 0.18
    elif name == "deduction_wrong":
        pitch, waveform, duration, volume = 180, "saw", 0.14, 0.18
    elif name == "overlay_open":
        pitch, waveform, duration, volume = 520, "triangle", 0.08, 0.18
    elif name == "overlay_close":
        pitch, waveform, duration, volume = 390, "triangle", 0.08, 0.18
    elif name == "clue_found":
        pitch, waveform, duration, volume = 880, "square", 0.14, 0.18
    elif name == "coin":
        pitch, waveform, duration, volume = 1200, "triangle", 0.06, 0.18
    elif name == "coin_bounce":
        pitch, waveform, duration, volume = 740, "square", 0.10, 0.12
    elif name == "leave_hide":
        pitch, waveform, duration, volume = 330, "triangle", 0.10, 0.18
    elif name == "enter_hide":
        pitch, waveform, duration, volume = 260, "square", 0.11, 0.18
    elif name == "leave_blend":
        pitch, waveform, duration, volume = 350, "triangle", 0.09, 0.18
    elif name == "enter_blend":
        pitch, waveform, duration, volume = 590, "triangle", 0.10, 0.18
    elif name == "caught":
        pitch, waveform, duration, volume = 110, "saw", 0.35, 0.22
    else:
        raise ValueError(f"Unknown sound effect: {name}")

    sample_rate, samples = generate_sound(pitch, waveform, duration, volume)
    threading.Thread(target=play_sound, args=(samples, sample_rate), daemon=True).start()


def generate_sound(pitch, waveform, duration, volume):
    pitch = clamp(float(pitch), 40, 1800)
    sample_rate = 22050
    count = int(sample_rate * duration)
    samples = bytearray()
    for i in range(count):
        phase = (i * pitch / sample_rate) % 1.0
        if waveform == "square":
            sample = 1.0 if phase < 0.5 else -1.0
        elif waveform == "triangle":
            sample = 1.0 - 4.0 * abs(phase - 0.5)
        else:  # saw
            sample = 2.0 * phase - 1.0
        fade = min(1.0, i / 180, (count - i - 1) / 300)
        samples.extend(struct.pack("<h", int(sample * volume * max(0, fade) * 32767)))
    return sample_rate, samples


def play_sound(samples, sample_rate):
    """Write generated samples to a temporary WAV and play it via the OS."""
    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            path = tmp.name
        with wave.open(path, "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(sample_rate)
            audio.writeframes(samples)
        if sys.platform == "darwin":
            command = ["afplay", path]
        elif os.name == "nt":
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME)
            return
        else:
            command = ["aplay", "-q", path]
        subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    except (OSError, wave.Error):
        pass  # Audio output is optional; the game still works without a player.
    finally:
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def as_int(value, default=0):
    """Tolerant int() for values read back from a save file."""
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def as_point(value):
    """An (x, y) pair from a save file, or None if it is malformed."""
    try:
        x, y = value
        return (float(x), float(y))
    except (TypeError, ValueError):
        return None


def lerp(a, b, alpha):
    return a + (b - a) * alpha


def length(x, y):
    return math.hypot(x, y)


def unit(x, y):
    d = math.hypot(x, y)
    return (x / d, y / d) if d > 0.00001 else (0.0, 0.0)


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def roman(n):
    return ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"][n]


def wrapped(s: str, width=68):
    return textwrap.fill(s, width=width, replace_whitespace=False)


def hex2rgb(s: str):
    return tuple(int(s[i:i + 2], 16) for i in (1, 3, 5))


def light(c, amount=0.2):
    rgb = hex2rgb(c) if isinstance(c, str) and c.startswith("#") else c
    return tuple(clamp(int(v + amount * 255), 0, 255) for v in rgb)


def shade(c, amt):
    rgb = hex2rgb(c) if isinstance(c, str) and c.startswith("#") else c
    return tuple(clamp(int(v * amt), 0, 255) for v in rgb)


@dataclass
class Item:
    id: str
    name: str
    x: float
    y: float
    kind: str
    details: str = ""
    secret: bool = False


@dataclass
class Agent:
    x: float
    y: float
    facing: str = "down"
    vx: float = 0.0
    vy: float = 0.0
    frame: float = 0.0
    moving: bool = False
    coat: int = 0
    hair: int = 0
    skin: int = 0
    hat: bool = False
    accessory: int = 0

    @property
    def feet(self):
        return self.x, self.y


@dataclass
class Level:
    chapter: int
    theme: str
    props: list[tuple]
    collisions: list[tuple[float, float, float, float]]
    objects: list[Item]
    witness: Agent
    killer: Agent
    civilians: list[Agent]
    hide_positions: list[tuple[float, float]]
    blend_zones: list[tuple[float, float, float]]
    patrol: list[tuple[float, float]]
    start: tuple[float, float]
    cards: list[str]


# Suspicion is NOT a world-wide switch. These distinct secure locations are
# the only portions of a chapter where surveillance creates active danger.
# The rest of the map is a public investigation space: there are real witnesses,
# nobody attacks you for walking near the evidence, and you can reason at leisure.
INVESTIGATION_STAKES = [
    ("Collins forged the time of death to make the house servants accuse one another.",
     "The family solicitor has been bought. Collins plans to silence the housemaid who saw his boots at the study door.",
     "Your clock reconstruction, his boot print, and the trust letter prove a staged alibi, access, and motive."),
    ("Vale did not vanish accidentally. The false punch and rewritten shift roster isolate Ada's movements.",
     "The station police answer to the manifest's owners; Ada is about to destroy the list and identify the surviving porter.",
     "The obsolete punch, witness account, and altered roster put Ada alone in the carriage."),
    ("Rowan was being kept in the hotel as a patient against his will.",
     "Fenwick controls the doctor's certificates and the local constables. Another patient is being moved tonight.",
     "The duplicate key, fabricated treatment bill, and bell log show exactly how he staged the sealed room."),
    ("Celeste's recorded testimony was the danger, not her performance.",
     "Rook controls every exit backstage and has ordered the film burned after tonight's final curtain.",
     "The revised cue, matching fiber, and emptied reel canister connect Rook to the blackout and theft."),
    ("Someone burned only the records that could challenge the Blackwell family's official history.",
     "Voss is ordering a second fire. The archivist's assistant is locked in the building with the replacement books.",
     "The targeted register, unique signet, and arcade route establish both the order and the escape."),
    ("Iris's plant was an address disguised as a specimen number.",
     "Wren hired armed men to retrieve the final botanical notebook; the gardener is still trapped in the glasshouse.",
     "The inward glass, early inventory removal, and Iris's final letter identify her sponsor as the intruder."),
    ("The wrong tide makes the entire official drowning report impossible.",
     "Pike has arranged for another courier to disappear on the departing launch while the harbor patrol looks away.",
     "The contrary current, rope braid, and forged docket identify the private launch and its master."),
    ("Grey was using the dome to watch people, not stars.",
     "Crane is sealing the observatory as a witness arrives; the only surviving guest book will be destroyed at dawn.",
     "The telescope angle, sabotaged gear, and erased attendance log point to Crane's concealment."),
    ("Judge Harrow had the original verdict. Blythe replaced it with a fiction.",
     "The courthouse guards have orders to return every witness to Blythe. The restored pages must leave before lockdown.",
     "The mismatched transcript, her authorization, and the dustless passage identify who changed the file."),
    ("All nine tokens arrange into a floor plan. Evelyn placed them along your route deliberately.",
     "Evelyn's final command is to eliminate you and burn the case archive. She has already sent her guards to the crypt.",
     "The token map, the founder's portrait, and the recorded confession establish her command over the chain of deaths."),
]


@dataclass
class PatrolGuard:
    """A real guard, rather than a sprite with an omniscient proximity trigger."""
    actor: Agent
    route: list[tuple[float, float]]
    rank: str = "security"
    waypoint: int = 0
    mode: str = "patrol"  # patrol, curious, investigate, search, pursue
    notice: float = 0.0
    linger: float = 0.0
    last_known: Any = None
    path: list[tuple[float, float]] = field(default_factory=list)
    path_goal: Any = None
    repath: float = 0.0
    scan_clock: float = 0.0
    search_turns: int = 0
    warned: bool = False


# TEN CHAPTERS / THIRTY DISTINCT REASONING TECHNIQUES
METHODS = [('Chronology', 'Compare timestamps to expose a false timeline.'),
           ('Contradiction', 'Find two claims that cannot both be true.'),
           ('Trace analysis', 'Connect a physical trace to its source.'),
           ('Alibi testing', "Cross-check a suspect's stated location."),
           ('Document authentication', 'Identify a forged or altered document.'),
           ('Motive mapping', 'Follow who benefits from the crime.'),
           ('Spatial inference', 'Infer movement from room layout.'),
           ('Witness triangulation', 'Reconcile conflicting eyewitness accounts.'),
           ('Cipher breaking', 'Decode a concealed message.'),
           ('Opportunity analysis', 'Establish access at the critical moment.'),
           ('Pattern recognition', 'Spot a repeated signature across incidents.'),
           ('Forensic comparison', 'Compare marks left by objects or tools.'),
           ('Negative evidence', 'Reason from something conspicuously absent.'),
           ('Behavioral profiling', 'Compare conduct to known habits.'),
           ('Ledger reconciliation', 'Find a financial discrepancy.'),
           ('Route reconstruction', "Rebuild a suspect's path."),
           ('Sound localization', 'Locate a sound through testimony.'),
           ('Material identification', 'Recognize a rare substance or fabric.'),
           ('Chain of custody', 'Track who handled an item.'),
           ('Codebook inference', 'Derive meaning from a recurring symbol.'),
           ('Probability elimination', 'Discard incompatible explanations.'),
           ('Security bypass analysis', 'Determine how safeguards failed.'),
           ('Testimony sequencing', 'Put recollections into proper order.'),
           ('Network analysis', 'Expose hidden associations between people.'),
           ('Chemical residue', 'Interpret safe, non-actionable lab residue.'),
           ('Handwriting comparison', 'Match distinctive letter forms.'),
           ('Mechanical reconstruction', 'Infer how a mechanism was manipulated.'),
           ('Identity verification', 'Compare claimed identity against records.'),
           ('Deception detection', 'Recognize a deliberately staged scene.'),
           ('Synthesis', 'Unite separate cases into one theory.')]

CHAPTERS = [{'title': 'The Manor',
             'place': 'Blackwell Manor',
             'victim': 'Albert Blackwell',
             'culprit': 'Mr. Collins',
             'role': 'the estate steward',
             'motive': 'his fear that Albert had discovered years of theft',
             'scene': 'manor',
             'threat': 'A storm batters the estate while someone inside keeps extinguishing lamps one by '
                       'one.',
             'intro': ['The Blackwell family has money, enemies, and a talent for silence.',
                       'Tonight the patriarch Albert Blackwell lies dead in his study while thunder '
                       'drowns every scream.',
                       'A woman calling herself Lady Evelyn presses a silver moth token into your '
                       "hand and whispers: 'Do not trust the clocks.'"],
             'reveal': 'Collins breaks when cornered. He admits the killing, but swears he was only the '
                       'first hand used by a hidden patron.',
             'aftermath': 'Inside his coat you find another silver moth and a ledger page naming a '
                          'midnight delivery at Ashcroft Station.',
             'witness': 'I heard the study door open long after the grandfather clock stopped. Someone '
                        'wanted us all staring at the wrong hour.',
             'clues': [('Broken Clock',
                        'The study clock froze at 9:30, but the mainspring was deliberately '
                        'jammed.'),
                       ('Crescent Footprints',
                        'Wet prints from the garden entrance show a crescent heel gouge.'),
                       ('Burned Trust Letter',
                        'A half-burned notice demands missing trust funds be restored before '
                        'dawn.')],
             'questions': [('Was the clock an honest timestamp?',
                            'Broken Clock',
                            'No. The clock was staged to create a false time of death.'),
                           ('Who entered through the garden?',
                            'Crescent Footprints',
                            "Collins's boots share the same crescent-cut heel."),
                           ('Why was Albert silenced?',
                            'Burned Trust Letter',
                            "Albert was about to expose Collins's embezzlement.")],
             'cinematic': ['I knew Albert Blackwell before I knew how to tell a convincing lie. He '
                           'had three fears. Thunder was not one of them.',
                           'The power fails. A gunshot is reported by the maid, but the body bears no '
                           'gunshot wound.',
                           'The family portrait above the stairs has been moved by half an inch. A '
                           'space is visible where a second portrait once hung.',
                           'Evelyn arrives before the constables. She has no umbrella and not a drop '
                           'of rain on her coat.',
                           "A whisper slips beneath the study door: 'He kept two ledgers. One for his "
                           "friends, one for his family.'",
                           'You find the broken clock, still ticking inside despite the hands being '
                           'stopped at half past nine.',
                           'A house full of people might have heard a scream. Every one of them '
                           'claims to have heard the storm instead.',
                           'Collins does not deny entering the study. He denies knowing what time it '
                           'was, then quotes the stopped clock exactly.',
                           'The first silver moth is cold in your hand. Its wings fit a notch carved '
                           'into the study desk.',
                           'An unsigned letter ends with three words: KEEP THEM QUIET.',
                           'Lady Evelyn asks whether you believe the dead deserve justice, or merely '
                           'a better story.',
                           'When you confront Collins, his first question is not whether you have '
                           'evidence. It is whether Evelyn is nearby.'],
             'supporting': ['Margot', 'Edmund'],
             'room_name': 'West Gallery',
             'discovery_moments': ['A small detail catches the light differently the second time you look.',
                                   'You turn the item over slowly. Its meaning changes when you '
                                   'remember what the witness said.',
                                   'You turn the object over. Something on the reverse has escaped every other pair of eyes.'],
             'dialogue': [{'speaker': 'Margot',
                           'text': 'I knew Albert Blackwell. They were frightened in the days '
                                   'before the murder. I keep thinking I should have said '
                                   'something.'},
                          {'speaker': 'Detective',
                           'text': 'Start from the last moment you saw them alive. Leave nothing '
                                   'out, even what seems unimportant.'},
                          {'speaker': 'Margot',
                           'text': 'I heard the study door open long after the grandfather clock '
                                   'stopped. Someone wanted us all staring at the wrong hour.'},
                          {'speaker': 'Detective',
                           'text': 'And who else knew you would be here tonight?'},
                          {'speaker': 'Margot',
                           'text': 'There was a message with a silver moth on the seal. I thought '
                                   'it was a family emblem.'},
                          {'speaker': 'Detective',
                           'text': 'This is the tenth time someone has told me that. Not one of '
                                   'them looked relieved.'},
                          {'speaker': 'Edmund',
                           'text': 'The people who run this place have been told to pretend they '
                                   'remember nothing.'},
                          {'speaker': 'Edmund',
                           'text': 'Even if I told you what I saw, I doubt you would believe who '
                                   'told me to stay silent.'},
                          {'speaker': 'Detective',
                           'text': "I will decide what the evidence can support. I won't decide "
                                   "before I've seen it."},
                          {'speaker': 'Margot',
                           'text': "Then search the room. You may find the truth, but it won't "
                                   'make this night easier.'}],
             'suspect_speech': ['You should have stayed away from Blackwell Manor. People who dig '
                                'beneath a family usually find graves.',
                                "I won't pretend I cared about Albert Blackwell. But you don't know "
                                'who truly wanted this done.',
                                "The silver moth is not a symbol of loyalty. It's a reminder that "
                                'someone can always see the light you stand in.',
                                'Ask Evelyn why your case file already existed before the murder was '
                                'reported.'],
             'deduction_decoys': [['The damage was an ordinary accident at Blackwell Manor.',
                                   'A stranger without access arrived after everyone left.'],
                                  ['The witness mistook a harmless visitor for the suspect.',
                                   'There is no reliable way to link the trace to any person.'],
                                  ['The motive was a spontaneous argument unrelated to the '
                                   'evidence.',
                                   'The paperwork is genuine and the loss has no connection to the '
                                   'death.']],
             'journal_lore': ['CASE 01 — THE MANOR',
                              'Location of inquiry: Blackwell Manor',
                              'Deceased: Albert Blackwell',
                              'Current testimony suggests the public story about the death is '
                              'incomplete.',
                              'A silver moth token appears in the evidence chain yet again.',
                              'The Blackwell family seems linked to the scene through a person, a '
                              'document, or a piece of land.',
                              "The night guard's patrol changes whenever anyone raises an alarm.",
                              'The witness seems afraid of a threat beyond the murderer in this room.',
                              'A false conclusion here could conceal evidence needed to unlock the '
                              'next case.',
                              'Only properly supported deductions can form the final accusation.'],
             'suspect_alias': 'Mr. Collins'},
            {'title': 'The Midnight Train',
             'place': 'Ashcroft Station',
             'victim': 'Conductor Vale',
             'culprit': 'Ada Mercer',
             'role': 'a railway clerk',
             'motive': 'to recover a passenger manifest tied to the Lantern network',
             'scene': 'train',
             'threat': 'Fog, steam, and the crush of travelers make it easy for someone to vanish '
                       'between carriages.',
             'intro': ['The station master swears the train never stopped, yet a body disappeared all '
                       'the same.',
                       "Conductor Vale's lantern was found swinging from an empty caboose and a "
                       "ticket was punched for a station that hasn't existed in thirty years.",
                       "In Collins's pocket ledger, Ashcroft Station was circled twice in red ink."],
             'reveal': 'Ada confesses she strangled Vale for the manifest, but claims the names on it '
                       'frightened her more than the murder itself.',
             'aftermath': "The manifest includes a physician from the Hollow Hotel and a note: 'Room 13 "
                          "must remain sealed.'",
             'witness': 'The woman in the blue coat stepped off after the bell, not before it. She '
                        'walked like she already knew no one would stop her.',
             'clues': [('Obsolete Punch Mark',
                        "The ticket was punched by a retired station tool kept in the clerk's "
                        'office.'),
                       ("Porter's Statement",
                        'A porter saw a woman in a blue coat leave after final departure.'),
                       ('Forged Shift Roster',
                        "Ada's shift log was written with fresh ink over dried columns.")],
             'questions': [('Could the ticket have been punched on the train?',
                            'Obsolete Punch Mark',
                            'No. It came from a retired punch only Ada could access.'),
                           ('Who was seen leaving the carriage?',
                            "Porter's Statement",
                            'The porter identified Ada by her distinctive blue coat.'),
                           ("Does Ada's alibi survive scrutiny?",
                            'Forged Shift Roster',
                            'No. The roster was altered after the train had departed.')],
             'cinematic': ['The last train to Ashcroft is delayed by a signal nobody admits sending.',
                           'Every passenger remembers a different conductor. Only the ticket stubs '
                           'agree on his name.',
                           "A child's toy clock ticks inside the empty compartment; its hands have no "
                           'face.',
                           'A whistle cuts through the fog, long after the rails should be silent.',
                           'A woman in blue moves against the flow of passengers, carefully avoiding '
                           'the station lamps.',
                           "The punch mark is shaped like a moth's split wing. Its ink is older than "
                           'the ticket.',
                           'The porter insists he saw Ada. He refuses to say who ordered him to keep '
                           'quiet.',
                           'A manifest lists three passengers under names belonging to people buried '
                           'years ago.',
                           'Your own name appears in the luggage registry with the wrong date of '
                           'birth.',
                           'Behind the station wall, someone has scratched: THE TRACKS ONLY RUN IN '
                           'ONE DIRECTION.',
                           'Ada asks if a list of names can be a weapon. She does not wait for your '
                           'answer.',
                           'A train passes without stopping. In every window is a face you think you '
                           'recognize.'],
             'supporting': ['Porter Finch', 'Station Guard'],
             'room_name': 'Platform Nine',
             'discovery_moments': ['A small detail catches the light differently the second time you look.',
                                   'You turn the item over slowly. Its meaning changes when you '
                                   'remember what the witness said.',
                                   'You turn the object over. Something on the reverse has escaped every other pair of eyes.'],
             'dialogue': [{'speaker': 'Porter Finch',
                           'text': 'I knew Conductor Vale. They were frightened in the days before '
                                   'the murder. I keep thinking I should have said something.'},
                          {'speaker': 'Detective',
                           'text': 'Start from the last moment you saw them alive. Leave nothing '
                                   'out, even what seems unimportant.'},
                          {'speaker': 'Porter Finch',
                           'text': 'The woman in the blue coat stepped off after the bell, not '
                                   'before it. She walked like she already knew no one would stop '
                                   'her.'},
                          {'speaker': 'Detective',
                           'text': 'And who else knew you would be here tonight?'},
                          {'speaker': 'Porter Finch',
                           'text': 'There was a message with a silver moth on the seal. I thought '
                                   'it was a family emblem.'},
                          {'speaker': 'Detective',
                           'text': 'This is the tenth time someone has told me that. Not one of '
                                   'them looked relieved.'},
                          {'speaker': 'Station Guard',
                           'text': 'The people who run this place have been told to pretend they '
                                   'remember nothing.'},
                          {'speaker': 'Station Guard',
                           'text': 'Even if I told you what I saw, I doubt you would believe who '
                                   'told me to stay silent.'},
                          {'speaker': 'Detective',
                           'text': "I will decide what the evidence can support. I won't decide "
                                   "before I've seen it."},
                          {'speaker': 'Porter Finch',
                           'text': "Then search the room. You may find the truth, but it won't "
                                   'make this night easier.'}],
             'suspect_speech': ['You should have stayed away from Ashcroft Station. People who dig '
                                'beneath a family usually find graves.',
                                "I won't pretend I cared about Conductor Vale. But you don't know who "
                                'truly wanted this done.',
                                "The silver moth is not a symbol of loyalty. It's a reminder that "
                                'someone can always see the light you stand in.',
                                'Ask Evelyn why your case file already existed before the murder was '
                                'reported.'],
             'deduction_decoys': [['The damage was an ordinary accident at Ashcroft Station.',
                                   'A stranger without access arrived after everyone left.'],
                                  ['The witness mistook a harmless visitor for the suspect.',
                                   'There is no reliable way to link the trace to any person.'],
                                  ['The motive was a spontaneous argument unrelated to the '
                                   'evidence.',
                                   'The paperwork is genuine and the loss has no connection to the '
                                   'death.']],
             'journal_lore': ['CASE 02 — THE MIDNIGHT TRAIN',
                              'Location of inquiry: Ashcroft Station',
                              'Deceased: Conductor Vale',
                              'Current testimony suggests the public story about the death is '
                              'incomplete.',
                              'A silver moth token appears in the evidence chain yet again.',
                              'The Blackwell family seems linked to the scene through a person, a '
                              'document, or a piece of land.',
                              "The night guard's patrol changes whenever anyone raises an alarm.",
                              'The witness seems afraid of a threat beyond the murderer in this room.',
                              'A false conclusion here could conceal evidence needed to unlock the '
                              'next case.',
                              'Only properly supported deductions can form the final accusation.'],
             'suspect_alias': 'Ada Mercer'},
            {'title': 'The Hollow Hotel',
             'place': 'Hollow Hotel',
             'victim': 'Guest Rowan',
             'culprit': 'Dr. Fenwick',
             'role': 'the resident physician',
             'motive': 'to conceal brutal experiments financed by the Lantern',
             'scene': 'hotel',
             'threat': 'Every corridor looks identical, every bell seems to ring from nowhere, and Room '
                       '13 feels occupied even when empty.',
             'intro': ['At the Hollow Hotel, curtains remain drawn at noon and no guest asks for '
                       'fresh towels twice.',
                       'Rowan, a guest who requested police protection, is gone from a room bolted '
                       'from within.',
                       "Under the bed, you find the next silver moth and the words: 'A doctor can "
                       "turn fear into obedience.'"],
             'reveal': 'Fenwick collapses under questioning and points toward a recording stolen at the '
                       'Gilded Theater—evidence he says could destroy the entire order.',
             'aftermath': 'You recover a coded patient ledger and the reel number of a film hidden in '
                          'the theater district.',
             'witness': 'The bell rang from the hall after Rowan disappeared. I know because I had '
                        'already collected the supper tray.',
             'clues': [('Duplicate Key Wax',
                        'Wax impressions inside the lock preserve the outline of a second key.'),
                       ('False Medical Bill',
                        'A hidden account lists treatments Rowan never authorized.'),
                       ('Bell Log',
                        'The service bell rang after Rowan should already have been dead.')],
             'questions': [('How was the locked room illusion created?',
                            'Duplicate Key Wax',
                            'A duplicate key allowed Fenwick to enter and re-lock the room.'),
                           ('What was Fenwick hiding?',
                            'False Medical Bill',
                            'The bill concealed unauthorized treatments and extortion.'),
                           ("Who faked the victim's final timeline?",
                            'Bell Log',
                            'Fenwick rang the service bell from the hall after the murder.')],
             'cinematic': ['Room thirteen has been rented every Tuesday for nineteen years. The '
                           'signatures are identical.',
                           'The concierge refuses to call the missing guest by their name.',
                           'A second key clinks in the ice bucket, though the ice has melted hours '
                           'ago.',
                           'The corridor mirror reflects a lamp that was extinguished yesterday.',
                           'One guest remembers a scream. Another remembers a lullaby.',
                           'In the basement an examination table lies beneath a sheet too clean for '
                           'the room.',
                           'The medical bills name treatments nobody remembers receiving.',
                           "The physician's handwriting changes halfway through his notebook.",
                           'Room thirteen smells faintly of burnt sugar and something chemical.',
                           'Rowan sent a letter to Evelyn two days before the murder. Evelyn never '
                           'mentioned it.',
                           'A sealed envelope contains the single word: THEATER.',
                           'Someone has been listening at the walls. The service bell rings once, '
                           'then once more.'],
             'supporting': ['Concierge Hale', 'Bellhop Owen'],
             'room_name': 'East Corridor',
             'discovery_moments': ['A small detail catches the light differently the second time you look.',
                                   'You turn the item over slowly. Its meaning changes when you '
                                   'remember what the witness said.',
                                   'You turn the object over. Something on the reverse has escaped every other pair of eyes.'],
             'dialogue': [{'speaker': 'Concierge Hale',
                           'text': 'I knew Guest Rowan. They were frightened in the days before '
                                   'the murder. I keep thinking I should have said something.'},
                          {'speaker': 'Detective',
                           'text': 'Start from the last moment you saw them alive. Leave nothing '
                                   'out, even what seems unimportant.'},
                          {'speaker': 'Concierge Hale',
                           'text': 'The bell rang from the hall after Rowan disappeared. I know '
                                   'because I had already collected the supper tray.'},
                          {'speaker': 'Detective',
                           'text': 'And who else knew you would be here tonight?'},
                          {'speaker': 'Concierge Hale',
                           'text': 'There was a message with a silver moth on the seal. I thought '
                                   'it was a family emblem.'},
                          {'speaker': 'Detective',
                           'text': 'This is the tenth time someone has told me that. Not one of '
                                   'them looked relieved.'},
                          {'speaker': 'Bellhop Owen',
                           'text': 'The people who run this place have been told to pretend they '
                                   'remember nothing.'},
                          {'speaker': 'Bellhop Owen',
                           'text': 'Even if I told you what I saw, I doubt you would believe who '
                                   'told me to stay silent.'},
                          {'speaker': 'Detective',
                           'text': "I will decide what the evidence can support. I won't decide "
                                   "before I've seen it."},
                          {'speaker': 'Concierge Hale',
                           'text': "Then search the room. You may find the truth, but it won't "
                                   'make this night easier.'}],
             'suspect_speech': ['You should have stayed away from Hollow Hotel. People who dig '
                                'beneath a family usually find graves.',
                                "I won't pretend I cared about Guest Rowan. But you don't know who "
                                'truly wanted this done.',
                                "The silver moth is not a symbol of loyalty. It's a reminder that "
                                'someone can always see the light you stand in.',
                                'Ask Evelyn why your case file already existed before the murder was '
                                'reported.'],
             'deduction_decoys': [['The damage was an ordinary accident at Hollow Hotel.',
                                   'A stranger without access arrived after everyone left.'],
                                  ['The witness mistook a harmless visitor for the suspect.',
                                   'There is no reliable way to link the trace to any person.'],
                                  ['The motive was a spontaneous argument unrelated to the '
                                   'evidence.',
                                   'The paperwork is genuine and the loss has no connection to the '
                                   'death.']],
             'journal_lore': ['CASE 03 — THE HOLLOW HOTEL',
                              'Location of inquiry: Hollow Hotel',
                              'Deceased: Guest Rowan',
                              'Current testimony suggests the public story about the death is '
                              'incomplete.',
                              'A silver moth token appears in the evidence chain yet again.',
                              'The Blackwell family seems linked to the scene through a person, a '
                              'document, or a piece of land.',
                              "The night guard's patrol changes whenever anyone raises an alarm.",
                              'The witness seems afraid of a threat beyond the murderer in this room.',
                              'A false conclusion here could conceal evidence needed to unlock the '
                              'next case.',
                              'Only properly supported deductions can form the final accusation.'],
             'suspect_alias': 'Dr. Fenwick'},
            {'title': 'The Gilded Theater',
             'place': 'Gilded Theater',
             'victim': 'Singer Celeste',
             'culprit': 'Victor Rook',
             'role': 'the stage manager',
             'motive': 'to suppress a recording naming Lantern trustees',
             'scene': 'theater',
             'threat': 'Crowds applaud while somebody backstage prepares another death behind velvet '
                       'curtains.',
             'intro': ['Theater folk lie with style, but their props usually tell the truth.',
                       "Celeste dies during a blackout timed to the final bow, and the night's master "
                       'reel vanishes with her final note.',
                       'In the wings you find another moth token pinned beneath a cue sheet.'],
             'reveal': 'Rook admits engineering the blackout and says the missing reel names the people '
                       'who funded every death so far.',
             'aftermath': 'Taped beneath the empty canister is a list of trustees and a registry code '
                          'tied to the Old Quarter archives.',
             'witness': "The stage went dark a breath too early. Only the manager's cue sheet ever "
                        'leaves no room for improvisation.',
             'clues': [('Blackout Cue',
                        "An additional blackout note was penciled into the manager's master cue "
                        'sheet.'),
                       ('Velvet Fiber',
                        "Red velvet threads from Rook's sleeve cling to the trapdoor latch."),
                       ('Hollow Film Canister',
                        'The canister is empty, but a hidden list of names is taped underneath '
                        'it.')],
             'questions': [('Who controlled the blackout?',
                            'Blackout Cue',
                            'Rook inserted the unauthorized lighting cue himself.'),
                           ('Who reached the trapdoor?',
                            'Velvet Fiber',
                            "The trapdoor snagged fibers from Rook's jacket sleeve."),
                           ('Why was Celeste killed?',
                            'Hollow Film Canister',
                            'She had evidence naming Lantern trustees on the stolen reel.')],
             'cinematic': ['The applause goes on after the lights cut out, as if the audience cannot '
                           'bear to hear silence.',
                           "Celeste's final line was changed on the night of her death. Her "
                           'understudy cannot say who changed it.',
                           'The stage manager carries two cue sheets. One contains a blackout nobody '
                           'rehearsed.',
                           'A red velvet thread catches on a brass latch beneath the boards.',
                           'Backstage, a phonograph plays a voice repeating a list of surnames.',
                           'The projectionist says someone swapped reels during the third act.',
                           "A torn ticket in the wings bears the crest of the city's oldest court.",
                           'The director calls it an accident. He is smiling when he says it.',
                           'A masked performer follows you between the curtains, then vanishes into '
                           'the wings.',
                           'The hidden list in the canister contains one family name twice.',
                           'Evelyn appears in a private balcony reserved for empty seats.',
                           'The house lights rise. No one has the courage to applaud.'],
             'supporting': ['Understudy Rose', 'Projectionist Lin'],
             'room_name': 'Stage Wings',
             'discovery_moments': ['A small detail catches the light differently the second time you look.',
                                   'You turn the item over slowly. Its meaning changes when you '
                                   'remember what the witness said.',
                                   'You turn the object over. Something on the reverse has escaped every other pair of eyes.'],
             'dialogue': [{'speaker': 'Understudy Rose',
                           'text': 'I knew Singer Celeste. They were frightened in the days before '
                                   'the murder. I keep thinking I should have said something.'},
                          {'speaker': 'Detective',
                           'text': 'Start from the last moment you saw them alive. Leave nothing '
                                   'out, even what seems unimportant.'},
                          {'speaker': 'Understudy Rose',
                           'text': "The stage went dark a breath too early. Only the manager's cue "
                                   'sheet ever leaves no room for improvisation.'},
                          {'speaker': 'Detective',
                           'text': 'And who else knew you would be here tonight?'},
                          {'speaker': 'Understudy Rose',
                           'text': 'There was a message with a silver moth on the seal. I thought '
                                   'it was a family emblem.'},
                          {'speaker': 'Detective',
                           'text': 'This is the tenth time someone has told me that. Not one of '
                                   'them looked relieved.'},
                          {'speaker': 'Projectionist Lin',
                           'text': 'The people who run this place have been told to pretend they '
                                   'remember nothing.'},
                          {'speaker': 'Projectionist Lin',
                           'text': 'Even if I told you what I saw, I doubt you would believe who '
                                   'told me to stay silent.'},
                          {'speaker': 'Detective',
                           'text': "I will decide what the evidence can support. I won't decide "
                                   "before I've seen it."},
                          {'speaker': 'Understudy Rose',
                           'text': "Then search the room. You may find the truth, but it won't "
                                   'make this night easier.'}],
             'suspect_speech': ['You should have stayed away from Gilded Theater. People who dig '
                                'beneath a family usually find graves.',
                                "I won't pretend I cared about Singer Celeste. But you don't know who "
                                'truly wanted this done.',
                                "The silver moth is not a symbol of loyalty. It's a reminder that "
                                'someone can always see the light you stand in.',
                                'Ask Evelyn why your case file already existed before the murder was '
                                'reported.'],
             'deduction_decoys': [['The damage was an ordinary accident at Gilded Theater.',
                                   'A stranger without access arrived after everyone left.'],
                                  ['The witness mistook a harmless visitor for the suspect.',
                                   'There is no reliable way to link the trace to any person.'],
                                  ['The motive was a spontaneous argument unrelated to the '
                                   'evidence.',
                                   'The paperwork is genuine and the loss has no connection to the '
                                   'death.']],
             'journal_lore': ['CASE 04 — THE GILDED THEATER',
                              'Location of inquiry: Gilded Theater',
                              'Deceased: Singer Celeste',
                              'Current testimony suggests the public story about the death is '
                              'incomplete.',
                              'A silver moth token appears in the evidence chain yet again.',
                              'The Blackwell family seems linked to the scene through a person, a '
                              'document, or a piece of land.',
                              "The night guard's patrol changes whenever anyone raises an alarm.",
                              'The witness seems afraid of a threat beyond the murderer in this room.',
                              'A false conclusion here could conceal evidence needed to unlock the '
                              'next case.',
                              'Only properly supported deductions can form the final accusation.'],
             'suspect_alias': 'Victor Rook'},
            {'title': 'The Old Quarter',
             'place': 'Old Quarter Archives',
             'victim': 'Archivist Bell',
             'culprit': 'Nora Voss',
             'role': 'the city registrar',
             'motive': 'to erase the true Blackwell bloodline from public record',
             'scene': 'quarter',
             'threat': 'Firelight and ash hide a second crime scene among alleys that seem to rearrange '
                       'themselves.',
             'intro': ['When records burn, somebody profits from forgetting.',
                       'A controlled blaze destroys one wall of the municipal archive, yet the flames '
                       'somehow spared a single family register.',
                       "Bell dies clutching a scrap of genealogy and the phrase: 'The first branch "
                       "was cut on purpose.'"],
             'reveal': 'Voss swears she erased the line because it pointed to a woman who built the '
                       'Lantern long before the murders began.',
             'aftermath': 'The surviving branch leads to a Blackwell matriarch and to a conservatory '
                          'donor named Silas Wren.',
             'witness': 'Only those pages burned. The rest of the room smoked, but the Blackwell indexes '
                        'vanished like they had been selected first.',
             'clues': [('Charred Register',
                        'The destroyed pages all indexed Blackwell family births and marriages.'),
                       ('Private Seal Fragment',
                        "A wax seal from a private registrar's signet was left near the ash pan."),
                       ('Arcade Sketch',
                        'A witness drew the escape route through the market arcade to a '
                        "registrar's side entrance.")],
             'questions': [('Which records were actually targeted?',
                            'Charred Register',
                            'The fire focused on the Blackwell lineage pages.'),
                           ('Who authorized their destruction?',
                            'Private Seal Fragment',
                            "The seal belongs to Nora Voss's private signet."),
                           ('How did the culprit escape unseen?',
                            'Arcade Sketch',
                            "The sketch traces directly back to Voss's office entrance.")],
             'cinematic': ['The archive is burning, but the fire follows the shelves like it can '
                           'read.',
                           "A registrar's seal rolls across the ash and comes to rest at your shoe.",
                           'Archivist Bell left a scrap showing a marriage entered twice under two '
                           'different names.',
                           'A door to the arcade was locked from the outside, then opened with a key '
                           'from within.',
                           'The smoke hides a silhouette on the mezzanine, motionless and watching.',
                           "The city historian will not speak until the mayor's carriage leaves.",
                           'Old portraits show a Blackwell child who is absent from the family tree.',
                           'A witness sketches the alley from memory, including a shutter painted '
                           'shut years ago.',
                           'Nora Voss keeps a ledger of every name she has erased.',
                           'For the first time, you wonder whether Albert was ever the head of his '
                           'own house.',
                           'A scorched page contains a family motto: WHAT IS UNWRITTEN CANNOT DIE.',
                           'A bell rings twelve times from a tower that has no working clock.'],
             'supporting': ['Mrs. Alder', 'Watchman Fox'],
             'room_name': 'Archive Gallery',
             'discovery_moments': ['A small detail catches the light differently the second time you look.',
                                   'You turn the item over slowly. Its meaning changes when you '
                                   'remember what the witness said.',
                                   'You turn the object over. Something on the reverse has escaped every other pair of eyes.'],
             'dialogue': [{'speaker': 'Mrs. Alder',
                           'text': 'I knew Archivist Bell. They were frightened in the days before '
                                   'the murder. I keep thinking I should have said something.'},
                          {'speaker': 'Detective',
                           'text': 'Start from the last moment you saw them alive. Leave nothing '
                                   'out, even what seems unimportant.'},
                          {'speaker': 'Mrs. Alder',
                           'text': 'Only those pages burned. The rest of the room smoked, but the '
                                   'Blackwell indexes vanished like they had been selected first.'},
                          {'speaker': 'Detective',
                           'text': 'And who else knew you would be here tonight?'},
                          {'speaker': 'Mrs. Alder',
                           'text': 'There was a message with a silver moth on the seal. I thought '
                                   'it was a family emblem.'},
                          {'speaker': 'Detective',
                           'text': 'This is the tenth time someone has told me that. Not one of '
                                   'them looked relieved.'},
                          {'speaker': 'Watchman Fox',
                           'text': 'The people who run this place have been told to pretend they '
                                   'remember nothing.'},
                          {'speaker': 'Watchman Fox',
                           'text': 'Even if I told you what I saw, I doubt you would believe who '
                                   'told me to stay silent.'},
                          {'speaker': 'Detective',
                           'text': "I will decide what the evidence can support. I won't decide "
                                   "before I've seen it."},
                          {'speaker': 'Mrs. Alder',
                           'text': "Then search the room. You may find the truth, but it won't "
                                   'make this night easier.'}],
             'suspect_speech': ['You should have stayed away from Old Quarter Archives. People who '
                                'dig beneath a family usually find graves.',
                                "I won't pretend I cared about Archivist Bell. But you don't know who "
                                'truly wanted this done.',
                                "The silver moth is not a symbol of loyalty. It's a reminder that "
                                'someone can always see the light you stand in.',
                                'Ask Evelyn why your case file already existed before the murder was '
                                'reported.'],
             'deduction_decoys': [['The damage was an ordinary accident at Old Quarter Archives.',
                                   'A stranger without access arrived after everyone left.'],
                                  ['The witness mistook a harmless visitor for the suspect.',
                                   'There is no reliable way to link the trace to any person.'],
                                  ['The motive was a spontaneous argument unrelated to the '
                                   'evidence.',
                                   'The paperwork is genuine and the loss has no connection to the '
                                   'death.']],
             'journal_lore': ['CASE 05 — THE OLD QUARTER',
                              'Location of inquiry: Old Quarter Archives',
                              'Deceased: Archivist Bell',
                              'Current testimony suggests the public story about the death is '
                              'incomplete.',
                              'A silver moth token appears in the evidence chain yet again.',
                              'The Blackwell family seems linked to the scene through a person, a '
                              'document, or a piece of land.',
                              "The night guard's patrol changes whenever anyone raises an alarm.",
                              'The witness seems afraid of a threat beyond the murderer in this room.',
                              'A false conclusion here could conceal evidence needed to unlock the '
                              'next case.',
                              'Only properly supported deductions can form the final accusation.'],
             'suspect_alias': 'Nora Voss'},
            {'title': 'The Glass Conservatory',
             'place': 'Glass Conservatory',
             'victim': 'Botanist Iris',
             'culprit': 'Silas Wren',
             'role': 'a wealthy patron',
             'motive': "to sell a discovery tied to the Lantern's meeting place",
             'scene': 'conservatory',
             'threat': 'Moonlight through shattered glass makes every shadow look like an intruder.',
             'intro': ['The conservatory should have smelled of earth and orchids. Instead it smells '
                       'of rain and broken glass.',
                       'Botanist Iris is found beside a smashed specimen cabinet, her hands stained '
                       'green from a plant she died protecting.',
                       "Pinned to a potting table is another moth token and a buyer's receipt torn in "
                       'half.'],
             'reveal': "Wren admits ordering the theft of Iris's specimen because it marked the route to "
                       'the hidden docks used by the Lantern.',
             'aftermath': "On the reverse of the buyer's receipt you find tide coordinates and the name "
                          'Pike.',
             'witness': 'She told me her sponsor smiled too easily. People who own glass houses should '
                        'not carry stones in their pockets.',
             'clues': [('Inward Glass Fall',
                        'The shards fell inward, proving the window was broken from outside.'),
                       ('Missing Inventory Slip',
                        'One specimen was removed before the official audit began.'),
                       ('Betrayal Note',
                        "Iris's final note says her own sponsor arranged the theft.")],
             'questions': [('Where did the intruder first enter?',
                            'Inward Glass Fall',
                            'The window was smashed from the garden side.'),
                           ('What was stolen before the murder?',
                            'Missing Inventory Slip',
                            "Wren arranged the specimen's removal ahead of the audit."),
                           ('Whom did Iris accuse?',
                            'Betrayal Note',
                            'The note identifies her sponsor, Silas Wren.')],
             'cinematic': ['The glasshouse turns moonlight into shards of pale blue, and every leaf '
                           'casts a knife-like shadow.',
                           'Botanist Iris died with soil beneath her nails and a pressed flower '
                           'hidden under her tongue.',
                           'One specimen is gone, yet the empty shelf contains fresh water from the '
                           'docks.',
                           "A sponsor's name has been scratched from a brass plaque.",
                           'The greenhouse attendant saw someone leave through the gardens without '
                           'using the path.',
                           'A moth token hangs from the frame of a cracked pane.',
                           'The surviving orchids have been watered with saltwater, which should have '
                           'killed them.',
                           "A half-written letter begins: 'Silas, the map is not a map.'",
                           "The patron's carriage arrives and leaves with one more trunk than it came "
                           'with.',
                           'You hear a glass panel shift in the rafters. A shadow is keeping pace '
                           'above you.',
                           "The plant's roots trace the direction of a buried drainage channel.",
                           "Iris's last words were about a ship, not a flower."],
             'supporting': ['Attendant Vera', 'Groundskeeper Ned'],
             'room_name': 'Glasshouse Walk',
             'discovery_moments': ['A small detail catches the light differently the second time you look.',
                                   'You turn the item over slowly. Its meaning changes when you '
                                   'remember what the witness said.',
                                   'You turn the object over. Something on the reverse has escaped every other pair of eyes.'],
             'dialogue': [{'speaker': 'Attendant Vera',
                           'text': 'I knew Botanist Iris. They were frightened in the days before '
                                   'the murder. I keep thinking I should have said something.'},
                          {'speaker': 'Detective',
                           'text': 'Start from the last moment you saw them alive. Leave nothing '
                                   'out, even what seems unimportant.'},
                          {'speaker': 'Attendant Vera',
                           'text': 'She told me her sponsor smiled too easily. People who own '
                                   'glass houses should not carry stones in their pockets.'},
                          {'speaker': 'Detective',
                           'text': 'And who else knew you would be here tonight?'},
                          {'speaker': 'Attendant Vera',
                           'text': 'There was a message with a silver moth on the seal. I thought '
                                   'it was a family emblem.'},
                          {'speaker': 'Detective',
                           'text': 'This is the tenth time someone has told me that. Not one of '
                                   'them looked relieved.'},
                          {'speaker': 'Groundskeeper Ned',
                           'text': 'The people who run this place have been told to pretend they '
                                   'remember nothing.'},
                          {'speaker': 'Groundskeeper Ned',
                           'text': 'Even if I told you what I saw, I doubt you would believe who '
                                   'told me to stay silent.'},
                          {'speaker': 'Detective',
                           'text': "I will decide what the evidence can support. I won't decide "
                                   "before I've seen it."},
                          {'speaker': 'Attendant Vera',
                           'text': "Then search the room. You may find the truth, but it won't "
                                   'make this night easier.'}],
             'suspect_speech': ['You should have stayed away from Glass Conservatory. People who dig '
                                'beneath a family usually find graves.',
                                "I won't pretend I cared about Botanist Iris. But you don't know who "
                                'truly wanted this done.',
                                "The silver moth is not a symbol of loyalty. It's a reminder that "
                                'someone can always see the light you stand in.',
                                'Ask Evelyn why your case file already existed before the murder was '
                                'reported.'],
             'deduction_decoys': [['The damage was an ordinary accident at Glass Conservatory.',
                                   'A stranger without access arrived after everyone left.'],
                                  ['The witness mistook a harmless visitor for the suspect.',
                                   'There is no reliable way to link the trace to any person.'],
                                  ['The motive was a spontaneous argument unrelated to the '
                                   'evidence.',
                                   'The paperwork is genuine and the loss has no connection to the '
                                   'death.']],
             'journal_lore': ['CASE 06 — THE GLASS CONSERVATORY',
                              'Location of inquiry: Glass Conservatory',
                              'Deceased: Botanist Iris',
                              'Current testimony suggests the public story about the death is '
                              'incomplete.',
                              'A silver moth token appears in the evidence chain yet again.',
                              'The Blackwell family seems linked to the scene through a person, a '
                              'document, or a piece of land.',
                              "The night guard's patrol changes whenever anyone raises an alarm.",
                              'The witness seems afraid of a threat beyond the murderer in this room.',
                              'A false conclusion here could conceal evidence needed to unlock the '
                              'next case.',
                              'Only properly supported deductions can form the final accusation.'],
             'suspect_alias': 'Silas Wren'},
            {'title': 'The Drowned Docks',
             'place': 'Drowned Docks',
             'victim': 'Courier Nash',
             'culprit': 'Harbor Master Pike',
             'role': 'the harbor master',
             'motive': 'to smuggle Lantern correspondence through an unlisted quay',
             'scene': 'docks',
             'threat': 'Fog horns, dark water, and stacked crates leave countless blind corners for an '
                       'ambush.',
             'intro': ["Nash's satchel washed ashore without the letter it was meant to protect.",
                       'The harbor records show no unusual traffic, which usually means every unusual '
                       'thing was paid for in cash.',
                       'Inside the satchel lining you discover a damp moth token and an address at '
                       'the old observatory.'],
             'reveal': 'Pike tries to flee by launch and admits he only moved the messages; he never '
                       'learned why the observatory mattered.',
             'aftermath': 'The recovered correspondence mentions a rooftop meeting under a telescope and '
                          'orders from Professor Crane.',
             'witness': 'The current never would have carried the satchel from the public pier. Whoever '
                        'tossed it did so from somewhere private.',
             'clues': [('Contrary Tide Chart',
                        'The tide direction proves the satchel came from the private quay, not the '
                        'public pier.'),
                       ('Braided Mooring Rope',
                        "A rare rope braid matches the harbor master's launch."),
                       ('Forged Cargo Docket',
                        "An unlisted vessel arrived under a false name in Pike's own ledger.")],
             'questions': [('Where was the satchel actually dumped?',
                            'Contrary Tide Chart',
                            "The current points back to Pike's private quay."),
                           ('Which launch was used?',
                            'Braided Mooring Rope',
                            "The distinctive braid identifies Pike's launch."),
                           ("Who hid the vessel's arrival?",
                            'Forged Cargo Docket',
                            'Pike altered the harbor register himself.')],
             'cinematic': ['The docks swallow sound. Even your footsteps seem late returning from the '
                           'fog.',
                           "Nash's satchel is found where the tide could not have carried it.",
                           'The harbor watch checks the same crate three times and never looks '
                           'inside.',
                           'Somebody has cut the lamps along the private quay.',
                           "Pike's boat leaves no wake on the ledger, but its rope is wet.",
                           'A cargo docket names a ship that was officially destroyed fourteen years '
                           'ago.',
                           'A lantern blinks from the far jetty: one long, two short, one long.',
                           'In the fog, a hooded figure walks straight into a line of stacked crates '
                           'and disappears.',
                           'A note in the satchel reads: LOOK UP WHEN THE CITY LOOKS DOWN.',
                           "Pike's ledger has a faint outline of a moth pressed through the page.",
                           'The tide turns before dawn. You have only a narrow window to reach the '
                           'observatory.',
                           'From the pier the courthouse tower looks exactly like a lighthouse with '
                           'its light put out.'],
             'supporting': ['Sailor Bram', 'Dockhand Moss'],
             'room_name': 'Moonlit Quay',
             'discovery_moments': ['A small detail catches the light differently the second time you look.',
                                   'You turn the item over slowly. Its meaning changes when you '
                                   'remember what the witness said.',
                                   'You turn the object over. Something on the reverse has escaped every other pair of eyes.'],
             'dialogue': [{'speaker': 'Sailor Bram',
                           'text': 'I knew Courier Nash. They were frightened in the days before '
                                   'the murder. I keep thinking I should have said something.'},
                          {'speaker': 'Detective',
                           'text': 'Start from the last moment you saw them alive. Leave nothing '
                                   'out, even what seems unimportant.'},
                          {'speaker': 'Sailor Bram',
                           'text': 'The current never would have carried the satchel from the '
                                   'public pier. Whoever tossed it did so from somewhere private.'},
                          {'speaker': 'Detective',
                           'text': 'And who else knew you would be here tonight?'},
                          {'speaker': 'Sailor Bram',
                           'text': 'There was a message with a silver moth on the seal. I thought '
                                   'it was a family emblem.'},
                          {'speaker': 'Detective',
                           'text': 'This is the tenth time someone has told me that. Not one of '
                                   'them looked relieved.'},
                          {'speaker': 'Dockhand Moss',
                           'text': 'The people who run this place have been told to pretend they '
                                   'remember nothing.'},
                          {'speaker': 'Dockhand Moss',
                           'text': 'Even if I told you what I saw, I doubt you would believe who '
                                   'told me to stay silent.'},
                          {'speaker': 'Detective',
                           'text': "I will decide what the evidence can support. I won't decide "
                                   "before I've seen it."},
                          {'speaker': 'Sailor Bram',
                           'text': "Then search the room. You may find the truth, but it won't "
                                   'make this night easier.'}],
             'suspect_speech': ['You should have stayed away from Drowned Docks. People who dig '
                                'beneath a family usually find graves.',
                                "I won't pretend I cared about Courier Nash. But you don't know who "
                                'truly wanted this done.',
                                "The silver moth is not a symbol of loyalty. It's a reminder that "
                                'someone can always see the light you stand in.',
                                'Ask Evelyn why your case file already existed before the murder was '
                                'reported.'],
             'deduction_decoys': [['The damage was an ordinary accident at Drowned Docks.',
                                   'A stranger without access arrived after everyone left.'],
                                  ['The witness mistook a harmless visitor for the suspect.',
                                   'There is no reliable way to link the trace to any person.'],
                                  ['The motive was a spontaneous argument unrelated to the '
                                   'evidence.',
                                   'The paperwork is genuine and the loss has no connection to the '
                                   'death.']],
             'journal_lore': ['CASE 07 — THE DROWNED DOCKS',
                              'Location of inquiry: Drowned Docks',
                              'Deceased: Courier Nash',
                              'Current testimony suggests the public story about the death is '
                              'incomplete.',
                              'A silver moth token appears in the evidence chain yet again.',
                              'The Blackwell family seems linked to the scene through a person, a '
                              'document, or a piece of land.',
                              "The night guard's patrol changes whenever anyone raises an alarm.",
                              'The witness seems afraid of a threat beyond the murderer in this room.',
                              'A false conclusion here could conceal evidence needed to unlock the '
                              'next case.',
                              'Only properly supported deductions can form the final accusation.'],
             'suspect_alias': 'Harbor Master Pike'},
            {'title': 'The Silent Observatory',
             'place': 'Silent Observatory',
             'victim': 'Astronomer Grey',
             'culprit': 'Professor Crane',
             'role': 'the observatory director',
             'motive': 'to protect secret Lantern meetings hidden in plain sight',
             'scene': 'observatory',
             'threat': 'The dome turns like a gun turret over the city, and every metal footstep echoes '
                       'into the dark.',
             'intro': ["Grey's final sky chart mapped no constellation at all.",
                       'Instead, his telescope was locked toward the courthouse tower and his last '
                       'journal entry listed guest initials, not stars.',
                       'At the base of the instrument lies yet another silver moth, scratched with a '
                       'courthouse seal.'],
             'reveal': 'Crane confesses the observatory dome was used to shield meetings, but insists '
                       'the real founder still moves inside the Blackwell family itself.',
             'aftermath': 'Impressions in a guest book name a magistrate and reference sealed evidence '
                          'in the old courthouse archive.',
             'witness': 'Grey said he had found a star that could ruin men in broad daylight. Then he '
                        'laughed and pointed at the courthouse.',
             'clues': [('Misaligned Star Chart',
                        'The telescope angle matches the courthouse tower rather than a '
                        'constellation.'),
                       ('Broken Dome Gear',
                        'A damaged gear jammed the dome mechanism and blocked an exit.'),
                       ('Indented Guest Book',
                        'Erased names still show through as impressions on the page.')],
             'questions': [('What was Grey truly observing?',
                            'Misaligned Star Chart',
                            'He was watching the courthouse tower, not the night sky.'),
                           ('How was escape prevented?',
                            'Broken Dome Gear',
                            'Someone jammed the dome with deliberate force.'),
                           ('Who attended the secret meeting?',
                            'Indented Guest Book',
                            'The erased impressions identify Lantern trustees and Magistrate '
                            'Blythe.')],
             'cinematic': ['The telescope is pointed at the courthouse, but the dome is aligned with '
                           'the moon.',
                           "Grey's journal records people gathering at the tower as if they were "
                           'celestial events.',
                           'The observatory director has removed one gear and left its teeth lying on '
                           'the floor.',
                           'A cold circle on the desk shows where a flask once stood.',
                           'Someone has marked the guest book with invisible pressure, not ink.',
                           'The metal dome rotates. The exit moves behind you as the mechanism '
                           'grinds.',
                           "An old recording plays a man's voice reading out a trial verdict.",
                           'Crane asks how many lives are worth preserving a single name.',
                           "A brass moth is mounted inside the telescope's eyepiece cap.",
                           'Your evidence points downward even as the telescope points toward the '
                           'sky.',
                           'The courthouse windows wink once in answer to a signal nobody sent.',
                           'A second observer watches from the stairs. By the time you reach them, '
                           'they are gone.'],
             'supporting': ['Assistant Hester', 'Night Watcher'],
             'room_name': 'Lower Dome',
             'discovery_moments': ['A small detail catches the light differently the second time you look.',
                                   'You turn the item over slowly. Its meaning changes when you '
                                   'remember what the witness said.',
                                   'You turn the object over. Something on the reverse has escaped every other pair of eyes.'],
             'dialogue': [{'speaker': 'Assistant Hester',
                           'text': 'I knew Astronomer Grey. They were frightened in the days '
                                   'before the murder. I keep thinking I should have said '
                                   'something.'},
                          {'speaker': 'Detective',
                           'text': 'Start from the last moment you saw them alive. Leave nothing '
                                   'out, even what seems unimportant.'},
                          {'speaker': 'Assistant Hester',
                           'text': 'Grey said he had found a star that could ruin men in broad '
                                   'daylight. Then he laughed and pointed at the courthouse.'},
                          {'speaker': 'Detective',
                           'text': 'And who else knew you would be here tonight?'},
                          {'speaker': 'Assistant Hester',
                           'text': 'There was a message with a silver moth on the seal. I thought '
                                   'it was a family emblem.'},
                          {'speaker': 'Detective',
                           'text': 'This is the tenth time someone has told me that. Not one of '
                                   'them looked relieved.'},
                          {'speaker': 'Night Watcher',
                           'text': 'The people who run this place have been told to pretend they '
                                   'remember nothing.'},
                          {'speaker': 'Night Watcher',
                           'text': 'Even if I told you what I saw, I doubt you would believe who '
                                   'told me to stay silent.'},
                          {'speaker': 'Detective',
                           'text': "I will decide what the evidence can support. I won't decide "
                                   "before I've seen it."},
                          {'speaker': 'Assistant Hester',
                           'text': "Then search the room. You may find the truth, but it won't "
                                   'make this night easier.'}],
             'suspect_speech': ['You should have stayed away from Silent Observatory. People who dig '
                                'beneath a family usually find graves.',
                                "I won't pretend I cared about Astronomer Grey. But you don't know "
                                'who truly wanted this done.',
                                "The silver moth is not a symbol of loyalty. It's a reminder that "
                                'someone can always see the light you stand in.',
                                'Ask Evelyn why your case file already existed before the murder was '
                                'reported.'],
             'deduction_decoys': [['The damage was an ordinary accident at Silent Observatory.',
                                   'A stranger without access arrived after everyone left.'],
                                  ['The witness mistook a harmless visitor for the suspect.',
                                   'There is no reliable way to link the trace to any person.'],
                                  ['The motive was a spontaneous argument unrelated to the '
                                   'evidence.',
                                   'The paperwork is genuine and the loss has no connection to the '
                                   'death.']],
             'journal_lore': ['CASE 08 — THE SILENT OBSERVATORY',
                              'Location of inquiry: Silent Observatory',
                              'Deceased: Astronomer Grey',
                              'Current testimony suggests the public story about the death is '
                              'incomplete.',
                              'A silver moth token appears in the evidence chain yet again.',
                              'The Blackwell family seems linked to the scene through a person, a '
                              'document, or a piece of land.',
                              "The night guard's patrol changes whenever anyone raises an alarm.",
                              'The witness seems afraid of a threat beyond the murderer in this room.',
                              'A false conclusion here could conceal evidence needed to unlock the '
                              'next case.',
                              'Only properly supported deductions can form the final accusation.'],
             'suspect_alias': 'Professor Crane'},
            {'title': 'The Court of Ash',
             'place': 'Old Courthouse',
             'victim': 'Judge Harrow',
             'culprit': 'Magistrate Blythe',
             'role': 'a magistrate',
             'motive': 'to bury the founding trial that protected the Lantern',
             'scene': 'court',
             'threat': 'The courthouse is all echoes and locked doors; once suspicion rises, every '
                       'bailiff becomes a hunter.',
             'intro': ['Harrow reopened a case older than you are and died the night before the '
                       'hearing.',
                       'The archive vault is sealed from the inside, but soot marks show the fire '
                       'began in a document tray, not the furnace.',
                       "Tucked inside a law volume is the ninth moth token and the words: 'She was "
                       "acquitted to found them all.'"],
             'reveal': 'Blythe confesses to the murder and to replacing trial pages—yet she fears Lady '
                       'Evelyn more than prison or death.',
             'aftermath': 'The restored transcript names Evelyn Blackwell as the hidden architect. The '
                          'moth tokens align into a map of the family crypt.',
             'witness': 'The trial had two verdicts. Someone wanted history to remember the innocent one '
                        'and bury the other in ash.',
             'clues': [('Replacement Transcript',
                        'Several trial pages were substituted to hide a second verdict.'),
                       ('Authorization Stamp',
                        "The replacement pages bear Blythe's archive authorization stamp."),
                       ('Dustless Passage',
                        'A hidden corridor to the archives shows fresh footprints in otherwise '
                        'settled dust.')],
             'questions': [('What did the original verdict reveal?',
                            'Replacement Transcript',
                            'The founder was cleared through fraud, not innocence.'),
                           ('Who inserted the false pages?',
                            'Authorization Stamp',
                            'Blythe authorized and installed the substitutions.'),
                           ('How was the sealed archive reached?',
                            'Dustless Passage',
                            'The killer used an unrecorded private corridor.')],
             'cinematic': ["Judge Harrow's office is immaculate. His trial notes are not.",
                           'Every replaced transcript page contains the same faint printer error.',
                           'A magistrate claims she has not entered the archive in years. Dust on her '
                           'coat is from the archive ceiling.',
                           'The courthouse clock rings one fewer time than it should.',
                           "Harrow's last case file has your own initials penciled at the margin.",
                           "A juror's statement ends mid-sentence and begins again in someone else's "
                           'handwriting.',
                           'Behind the bench, a narrow passage leads toward a sealed file room.',
                           'Blythe has kept two verdicts under one case number.',
                           'An old newspaper photograph shows Evelyn without looking one day younger '
                           'than she does now.',
                           "A moth-shaped keyhole appears on the underside of the judge's desk.",
                           'You read the original verdict. The accused was the person who first hired '
                           'you.',
                           'The last token clicks into place. The floor plan leads back to the '
                           'manor.'],
             'supporting': ['Clerk Sloane', 'Bailiff Flint'],
             'room_name': 'Sealed Records',
             'discovery_moments': ['A small detail catches the light differently the second time you look.',
                                   'You turn the item over slowly. Its meaning changes when you '
                                   'remember what the witness said.',
                                   'You turn the object over. Something on the reverse has escaped every other pair of eyes.'],
             'dialogue': [{'speaker': 'Clerk Sloane',
                           'text': 'I knew Judge Harrow. They were frightened in the days before '
                                   'the murder. I keep thinking I should have said something.'},
                          {'speaker': 'Detective',
                           'text': 'Start from the last moment you saw them alive. Leave nothing '
                                   'out, even what seems unimportant.'},
                          {'speaker': 'Clerk Sloane',
                           'text': 'The trial had two verdicts. Someone wanted history to remember '
                                   'the innocent one and bury the other in ash.'},
                          {'speaker': 'Detective',
                           'text': 'And who else knew you would be here tonight?'},
                          {'speaker': 'Clerk Sloane',
                           'text': 'There was a message with a silver moth on the seal. I thought '
                                   'it was a family emblem.'},
                          {'speaker': 'Detective',
                           'text': 'This is the tenth time someone has told me that. Not one of '
                                   'them looked relieved.'},
                          {'speaker': 'Bailiff Flint',
                           'text': 'The people who run this place have been told to pretend they '
                                   'remember nothing.'},
                          {'speaker': 'Bailiff Flint',
                           'text': 'Even if I told you what I saw, I doubt you would believe who '
                                   'told me to stay silent.'},
                          {'speaker': 'Detective',
                           'text': "I will decide what the evidence can support. I won't decide "
                                   "before I've seen it."},
                          {'speaker': 'Clerk Sloane',
                           'text': "Then search the room. You may find the truth, but it won't "
                                   'make this night easier.'}],
             'suspect_speech': ['You should have stayed away from Old Courthouse. People who dig '
                                'beneath a family usually find graves.',
                                "I won't pretend I cared about Judge Harrow. But you don't know who "
                                'truly wanted this done.',
                                "The silver moth is not a symbol of loyalty. It's a reminder that "
                                'someone can always see the light you stand in.',
                                'Ask Evelyn why your case file already existed before the murder was '
                                'reported.'],
             'deduction_decoys': [['The damage was an ordinary accident at Old Courthouse.',
                                   'A stranger without access arrived after everyone left.'],
                                  ['The witness mistook a harmless visitor for the suspect.',
                                   'There is no reliable way to link the trace to any person.'],
                                  ['The motive was a spontaneous argument unrelated to the '
                                   'evidence.',
                                   'The paperwork is genuine and the loss has no connection to the '
                                   'death.']],
             'journal_lore': ['CASE 09 — THE COURT OF ASH',
                              'Location of inquiry: Old Courthouse',
                              'Deceased: Judge Harrow',
                              'Current testimony suggests the public story about the death is '
                              'incomplete.',
                              'A silver moth token appears in the evidence chain yet again.',
                              'The Blackwell family seems linked to the scene through a person, a '
                              'document, or a piece of land.',
                              "The night guard's patrol changes whenever anyone raises an alarm.",
                              'The witness seems afraid of a threat beyond the murderer in this room.',
                              'A false conclusion here could conceal evidence needed to unlock the '
                              'next case.',
                              'Only properly supported deductions can form the final accusation.'],
             'suspect_alias': 'Magistrate Blythe'},
            {'title': 'The Last Lantern',
             'place': 'Blackwell Crypt',
             'victim': 'The final witness',
             'culprit': 'Evelyn Blackwell',
             'role': 'the hidden architect of the Lantern',
             'motive': 'to preserve the family myth by controlling every witness and every record',
             'scene': 'crypt',
             'threat': 'The crypt is a maze of candles, stone, and family portraits; even victory feels '
                       'like trespass.',
             'intro': ['The nine silver moths fit together into a floor plan beneath the Blackwell '
                       'estate.',
                       'Lady Evelyn has been at your shoulder since the first death—offering help, '
                       'steering your attention, feeding your anger.',
                       'Now the crypt opens, and your final witness lies dying beside a recorder '
                       'addressed to you alone.'],
             'reveal': 'Evelyn admits every chapter served her design: each murder pruned a threat to '
                       'the Blackwell legend and drew you downward, one truth at a time.',
             'aftermath': 'With Evelyn dead, the Lantern collapses. The records survive. So does the '
                          'uneasy knowledge that she turned your own hunger for justice into her final '
                          'weapon.',
             'witness': 'She said the family had to remain a story, not a bloodline. Stories survive '
                        'because somebody chooses what is remembered.',
             'clues': [('Moth Map', "The nine moth tokens lock together into the crypt's floor plan."),
                       ("Founder's Portrait",
                        'A concealed dedication names Evelyn as the surviving heir to the '
                        'founder.'),
                       ('Final Confession',
                        'A sealed recording links Evelyn to every prior killing and every order.')],
             'questions': [('What links all nine previous cases?',
                            'Moth Map',
                            'Each crime followed instructions embedded in the moth token network.'),
                           ('Who truly founded and preserved the Lantern?',
                            "Founder's Portrait",
                            'Evelyn Blackwell inherited and directed the society.'),
                           ('Who ordered the chain of murders?',
                            'Final Confession',
                            'The recording names Evelyn as the architect behind all ten '
                            'chapters.')],
             'cinematic': ['The manor is quiet when you return. The storm ended days ago. The windows '
                           'are still lit.',
                           'Nine brass moths fit together like wings around a hollow center.',
                           'The crypt opens beneath the family portrait that was moved on the first '
                           'night.',
                           'A recording addressed to you plays in the voice of someone you buried '
                           'three chapters ago.',
                           'Evelyn is waiting under a circle of candles. She has dressed for a '
                           'funeral but wears no mourning black.',
                           'The surviving witness tries to speak. Evelyn closes their eyes before '
                           'they can say her name.',
                           "Every murder removed someone who might have contradicted the family's "
                           'official history.',
                           'The ledger reveals Evelyn funded the investigation as carefully as she '
                           'funded the killings.',
                           'She says she needed a detective brave enough to do what the Lantern could '
                           'no longer do.',
                           'Your journal lies open on the altar, its pages rearranged into the '
                           'chronology she wanted you to discover.',
                           'The final confession is real. So are the lives that will never be '
                           'returned.',
                           'You have one decision left: end the person who shaped the mystery, or '
                           'become part of her ending.'],
             'supporting': ['Evelyn', 'The last witness'],
             'room_name': 'Family Crypt',
             'discovery_moments': ['A small detail catches the light differently the second time you look.',
                                   'You turn the item over slowly. Its meaning changes when you '
                                   'remember what the witness said.',
                                   'You turn the object over. Something on the reverse has escaped every other pair of eyes.'],
             'dialogue': [{'speaker': 'Evelyn',
                           'text': 'I knew The final witness. They were frightened in the days '
                                   'before the murder. I keep thinking I should have said '
                                   'something.'},
                          {'speaker': 'Detective',
                           'text': 'Start from the last moment you saw them alive. Leave nothing '
                                   'out, even what seems unimportant.'},
                          {'speaker': 'Evelyn',
                           'text': 'She said the family had to remain a story, not a bloodline. '
                                   'Stories survive because somebody chooses what is remembered.'},
                          {'speaker': 'Detective',
                           'text': 'And who else knew you would be here tonight?'},
                          {'speaker': 'Evelyn',
                           'text': 'There was a message with a silver moth on the seal. I thought '
                                   'it was a family emblem.'},
                          {'speaker': 'Detective',
                           'text': 'This is the tenth time someone has told me that. Not one of '
                                   'them looked relieved.'},
                          {'speaker': 'The last witness',
                           'text': 'The people who run this place have been told to pretend they '
                                   'remember nothing.'},
                          {'speaker': 'The last witness',
                           'text': 'Even if I told you what I saw, I doubt you would believe who '
                                   'told me to stay silent.'},
                          {'speaker': 'Detective',
                           'text': "I will decide what the evidence can support. I won't decide "
                                   "before I've seen it."},
                          {'speaker': 'Evelyn',
                           'text': "Then search the room. You may find the truth, but it won't "
                                   'make this night easier.'}],
             'suspect_speech': ['You should have stayed away from Blackwell Crypt. People who dig '
                                'beneath a family usually find graves.',
                                "I won't pretend I cared about The final witness. But you don't know "
                                'who truly wanted this done.',
                                "The silver moth is not a symbol of loyalty. It's a reminder that "
                                'someone can always see the light you stand in.',
                                'Ask Evelyn why your case file already existed before the murder was '
                                'reported.'],
             'deduction_decoys': [['The damage was an ordinary accident at Blackwell Crypt.',
                                   'A stranger without access arrived after everyone left.'],
                                  ['The witness mistook a harmless visitor for the suspect.',
                                   'There is no reliable way to link the trace to any person.'],
                                  ['The motive was a spontaneous argument unrelated to the '
                                   'evidence.',
                                   'The paperwork is genuine and the loss has no connection to the '
                                   'death.']],
             'journal_lore': ['CASE 10 — THE LAST LANTERN',
                              'Location of inquiry: Blackwell Crypt',
                              'Deceased: The final witness',
                              'Current testimony suggests the public story about the death is '
                              'incomplete.',
                              'A silver moth token appears in the evidence chain yet again.',
                              'The Blackwell family seems linked to the scene through a person, a '
                              'document, or a piece of land.',
                              "The night guard's patrol changes whenever anyone raises an alarm.",
                              'The witness seems afraid of a threat beyond the murderer in this room.',
                              'A false conclusion here could conceal evidence needed to unlock the '
                              'next case.',
                              'Only properly supported deductions can form the final accusation.'],
             'suspect_alias': 'Evelyn Blackwell'}]

# Each discovery has a specific sensory detail rather than procedural narration.
# These lines are written from the detective's viewpoint, not as tutorial text.
DISCOVERY_BEATS = [
    [
        "The clock is warm to the touch. The hands are dead, but the mechanism within still struggles to turn.",
        "Rain has filled the heel impressions. One print stops sharply, as though its owner heard the study door open.",
        "Only the signature survives the flame. Someone wanted Albert frightened by the debt before he died.",
    ],
    [
        "The punch is an older pattern, a little star where there should be a square. Who kept a machine everyone else had discarded?",
        "The porter remembers the coat because its hem dragged in the rain. His memory is clear; his timing may not be.",
        "Fresh ink gleams across a dry column. Ada has written herself into a night she cannot account for.",
    ],
    [
        "Wax has settled in the lock's teeth, preserving the shape of a key no guest should possess.",
        "The figures add up too neatly. The hotel charged for a treatment that Rowan never received.",
        "The bell rope shivers under your fingers. Someone used it after the room had already fallen silent.",
    ],
    [
        "The cue has been added in a tighter hand than the rest. Someone prepared a second darkness.",
        "A crimson fiber catches on the latch. It came from a sleeve, not from the stage curtain.",
        "The canister rattles without a reel inside. The real treasure is the list taped beneath its base.",
    ],
    [
        "The missing pages were cut away before the fire caught. The flames were meant to disguise a careful removal.",
        "Voss's crest is pressed into the wax twice. The second impression was made while the seal was still warm.",
        "The route avoids the lamps and passes the registrar's private steps. The witness knew that path well.",
    ],
    [
        "Glass lies inside the conservatory in a fan shape. Nothing about its fall resembles an accident from within.",
        "A blank inventory line holds the impression of a number that has been rubbed out.",
        "Iris's handwriting deteriorates at the bottom of the page. The name she feared is still legible.",
    ],
    [
        "The tide mark contradicts the harbor record. The water could not have done what Pike claims.",
        "Salt has dried into the rope's braid, but the knot is freshly tied.",
        "A false vessel name sits over another entry. Held to the light, the original still shows through.",
    ],
    [
        "Grey used a star chart to point at a courtroom. He must have wanted the discovery to look harmless.",
        "One gear tooth has been bent backward by a tool. The dome did not fail by itself.",
        "The names are gone, but their impressions remain on the next page like whispers pressed into paper.",
    ],
    [
        "The transcript changes voice halfway down the page. Two verdicts were made to read as one.",
        "The approval mark sits over a fold; the page was stamped after it was inserted.",
        "Dust has been brushed away in the shape of a narrow foot. Someone passed through the forgotten corridor.",
    ],
    [
        "The nine moths meet along their damaged edges. Together they form a path through the crypt.",
        "Someone painted over the dedication, but the older lettering rises through the varnish.",
        "The recording begins with Evelyn's voice. She sounds less like a confessor than someone finishing a lesson.",
    ],
]
for _chapter, _moments in zip(CHAPTERS, DISCOVERY_BEATS):
    _chapter["discovery_moments"] = _moments

# -----------------------------------------------------------------------------
# LEVEL BIBLE
# The rooms share a navigation grammar (approachable desks, exits, soft cover),
# but have distinct materials, furniture, clues, props, and spatial rhythm.
# Coordinates are in world pixels, not display pixels.
# -----------------------------------------------------------------------------

THEMES = [
    {
        "name": "manor",
        "floor": (52, 35, 38),
        "floor2": (66, 42, 43),
        "floor_line": (87, 59, 58),
        "wall": (49, 38, 51),
        "wall2": (69, 49, 55),
        "trim": (130, 91, 67),
        "rug": (94, 41, 55),
        "rug_border": (185, 121, 71),
        "blue": (25, 47, 67),
        "warm": (238, 183, 103),
    },
    {
        "name": "train",
        "floor": (52, 48, 50),
        "floor2": (64, 55, 51),
        "floor_line": (84, 76, 70),
        "wall": (38, 51, 66),
        "wall2": (45, 59, 75),
        "trim": (155, 123, 84),
        "rug": (52, 62, 76),
        "rug_border": (168, 143, 93),
        "blue": (20, 42, 63),
        "warm": (240, 192, 108),
    },
    {
        "name": "hotel",
        "floor": (59, 51, 59),
        "floor2": (66, 56, 62),
        "floor_line": (94, 80, 80),
        "wall": (48, 35, 44),
        "wall2": (62, 44, 48),
        "trim": (142, 110, 81),
        "rug": (67, 51, 76),
        "rug_border": (183, 133, 78),
        "blue": (28, 42, 55),
        "warm": (228, 173, 104),
    },
    {
        "name": "theater",
        "floor": (50, 31, 43),
        "floor2": (62, 37, 50),
        "floor_line": (98, 52, 63),
        "wall": (60, 27, 45),
        "wall2": (85, 31, 52),
        "trim": (150, 87, 76),
        "rug": (99, 30, 48),
        "rug_border": (204, 144, 81),
        "blue": (27, 36, 54),
        "warm": (255, 181, 97),
    },
    {
        "name": "archive",
        "floor": (62, 43, 36),
        "floor2": (72, 53, 39),
        "floor_line": (102, 72, 58),
        "wall": (55, 42, 39),
        "wall2": (75, 51, 43),
        "trim": (152, 110, 77),
        "rug": (64, 49, 57),
        "rug_border": (172, 127, 75),
        "blue": (24, 40, 54),
        "warm": (245, 170, 80),
    },
    {
        "name": "greenhouse",
        "floor": (50, 68, 59),
        "floor2": (62, 76, 65),
        "floor_line": (78, 101, 80),
        "wall": (34, 60, 59),
        "wall2": (44, 75, 72),
        "trim": (126, 137, 110),
        "rug": (60, 74, 62),
        "rug_border": (164, 155, 96),
        "blue": (23, 63, 72),
        "warm": (222, 187, 114),
    },
    {
        "name": "docks",
        "floor": (55, 53, 48),
        "floor2": (68, 62, 53),
        "floor_line": (93, 83, 72),
        "wall": (33, 45, 58),
        "wall2": (39, 53, 65),
        "trim": (138, 105, 77),
        "rug": (44, 61, 69),
        "rug_border": (155, 116, 80),
        "blue": (18, 52, 77),
        "warm": (231, 169, 93),
    },
    {
        "name": "observatory",
        "floor": (47, 53, 64),
        "floor2": (58, 63, 73),
        "floor_line": (73, 89, 103),
        "wall": (32, 43, 57),
        "wall2": (41, 57, 72),
        "trim": (128, 128, 121),
        "rug": (59, 56, 72),
        "rug_border": (154, 137, 104),
        "blue": (21, 46, 70),
        "warm": (236, 188, 120),
    },
    {
        "name": "court",
        "floor": (64, 52, 47),
        "floor2": (75, 61, 55),
        "floor_line": (95, 82, 74),
        "wall": (57, 48, 50),
        "wall2": (72, 58, 59),
        "trim": (148, 114, 85),
        "rug": (78, 45, 53),
        "rug_border": (192, 138, 91),
        "blue": (33, 47, 58),
        "warm": (243, 192, 120),
    },
    {
        "name": "crypt",
        "floor": (46, 49, 59),
        "floor2": (54, 57, 65),
        "floor_line": (84, 91, 99),
        "wall": (34, 39, 51),
        "wall2": (45, 49, 62),
        "trim": (127, 112, 100),
        "rug": (53, 44, 62),
        "rug_border": (172, 152, 118),
        "blue": (25, 43, 64),
        "warm": (240, 181, 96),
    },
]

# Each tuple is (visual, world x, world y, variant/size). Interactive objects are
# deliberately NOT overlaid with permanent icons; the player discovers them by
# studying recognizable shapes and context clues.
ROOM_PROPS = [
    [
        ("rug", 122, 128, 0), ("bookcase", 34, 48, 0),
        ("bookcase", 92, 48, 1), ("bookcase", 377, 48, 2),
        ("bookcase", 441, 48, 3), ("fireplace", 238, 45, 0),
        ("painting", 331, 45, 0), ("desk", 126, 119, 0),
        ("clock", 150, 114, 0), ("letter", 317, 198, 1),
        ("footprints", 444, 132, 0), ("armchair", 199, 205, 0),
        ("armchair", 308, 206, 1), ("table", 244, 229, 0),
        ("candle", 262, 225, 1), ("plant", 58, 225, 1),
        ("plant", 479, 247, 1), ("wardrobe", 35, 270, 1),
        ("bookcase", 403, 245, 1), ("piano", 418, 147, 0),
    ],
    [
        ("runner", 90, 139, 0), ("window", 88, 47, 0),
        ("window", 202, 47, 1), ("window", 382, 47, 0),
        ("window", 485, 47, 1), ("bench", 57, 122, 0),
        ("bench", 387, 130, 1), ("ticket", 144, 132, 0),
        ("paper", 310, 217, 0), ("ledger", 443, 132, 0),
        ("suitcase", 207, 250, 0), ("suitcase", 484, 213, 1),
        ("clock", 274, 46, 1), ("lamp", 364, 98, 0),
        ("crate", 55, 284, 0), ("crate", 75, 289, 1),
        ("coatstand", 459, 270, 0), ("pillar", 267, 83, 0),
    ],
    [
        ("runner", 109, 130, 0), ("door", 126, 50, 0),
        ("door", 375, 50, 1), ("key", 138, 110, 0),
        ("bill", 288, 204, 0), ("bell", 454, 124, 0),
        ("desk", 269, 196, 0), ("armchair", 194, 218, 1),
        ("armchair", 385, 242, 0), ("plant", 54, 268, 0),
        ("plant", 474, 263, 0), ("lamp", 78, 157, 1),
        ("lamp", 485, 153, 0), ("painting", 248, 51, 1),
        ("wardrobe", 46, 98, 2), ("counter", 400, 271, 0),
    ],
    [
        ("stage", 82, 47, 0), ("curtain", 89, 47, 0),
        ("curtain", 399, 47, 1), ("piano", 202, 87, 0),
        ("cue", 122, 122, 0), ("velvet", 297, 207, 0),
        ("film", 443, 136, 0), ("table", 282, 218, 0),
        ("footlight", 114, 168, 0), ("footlight", 197, 168, 0),
        ("footlight", 374, 168, 0), ("footlight", 451, 168, 0),
        ("bench", 123, 271, 0), ("bench", 380, 276, 0),
        ("wardrobe", 53, 258, 0), ("coatstand", 495, 245, 0),
    ],
    [
        ("runner", 114, 125, 0), ("bookcase", 40, 47, 0),
        ("bookcase", 96, 47, 1), ("bookcase", 390, 47, 2),
        ("bookcase", 450, 47, 3), ("burned", 122, 118, 0),
        ("seal", 290, 210, 0), ("sketch", 445, 123, 0),
        ("desk", 265, 204, 1), ("clock", 276, 50, 0),
        ("crate", 64, 267, 2), ("crate", 103, 278, 0),
        ("plant", 472, 251, 2), ("lamp", 395, 202, 0),
        ("armchair", 202, 228, 0), ("bookcase", 390, 265, 0),
    ],
    [
        ("glassfloor", 77, 105, 0), ("plant", 47, 122, 2),
        ("plant", 109, 89, 1), ("plant", 439, 102, 2),
        ("plant", 487, 212, 0), ("glass", 153, 121, 0),
        ("inventory", 304, 201, 0), ("note", 452, 137, 0),
        ("desk", 289, 193, 1), ("bench", 208, 251, 0),
        ("plant", 70, 281, 2), ("plant", 158, 286, 0),
        ("plant", 361, 293, 1), ("plant", 452, 278, 2),
        ("glass", 78, 73, 1), ("glass", 475, 76, 2),
    ],
    [
        ("dockfloor", 60, 118, 0), ("water", 67, 49, 0),
        ("water", 401, 47, 1), ("tide", 140, 124, 0),
        ("rope", 303, 212, 0), ("cargo", 448, 136, 0),
        ("crate", 112, 202, 0), ("crate", 232, 248, 2),
        ("crate", 379, 233, 1), ("crate", 438, 269, 0),
        ("barrel", 85, 290, 0), ("barrel", 475, 234, 0),
        ("lantern", 257, 92, 0), ("lantern", 380, 93, 1),
        ("suitcase", 209, 159, 0), ("bench", 381, 270, 0),
    ],
    [
        ("starchart", 101, 116, 0), ("telescope", 242, 70, 0),
        ("guestbook", 446, 136, 0), ("gear", 303, 215, 0),
        ("desk", 285, 207, 2), ("clock", 271, 43, 2),
        ("scope", 155, 88, 0), ("window", 61, 49, 2),
        ("window", 459, 49, 3), ("bookshelf", 83, 255, 0),
        ("plant", 480, 262, 1), ("globe", 411, 261, 0),
        ("bench", 191, 267, 1), ("lamp", 391, 183, 1),
    ],
    [
        ("runner", 118, 115, 0), ("bench", 98, 185, 0),
        ("bench", 445, 205, 1), ("judgebench", 196, 55, 0),
        ("transcript", 139, 130, 0), ("stamp", 300, 206, 0),
        ("passage", 459, 128, 0), ("desk", 282, 198, 0),
        ("bookshelf", 55, 251, 2), ("bookshelf", 449, 264, 1),
        ("portrait", 97, 51, 0), ("portrait", 398, 51, 1),
        ("candle", 225, 140, 1), ("candle", 370, 146, 0),
    ],
    [
        ("stonefloor", 105, 108, 0), ("coffin", 224, 114, 0),
        ("moths", 146, 130, 0), ("portrait", 302, 200, 2),
        ("record", 453, 134, 0), ("altar", 276, 196, 0),
        ("candle", 88, 143, 1), ("candle", 488, 136, 0),
        ("candle", 111, 241, 1), ("candle", 444, 250, 1),
        ("pillar", 67, 76, 0), ("pillar", 470, 78, 0),
        ("pillar", 79, 291, 0), ("pillar", 461, 300, 0),
        ("statue", 55, 205, 0), ("statue", 472, 211, 1),
    ],
]

EVIDENCE_SHAPES = [
    ("clock", "footprints", "letter"),
    ("ticket", "paper", "ledger"),
    ("key", "bill", "bell"),
    ("cue", "velvet", "film"),
    ("burned", "seal", "sketch"),
    ("glass", "inventory", "note"),
    ("tide", "rope", "cargo"),
    ("starchart", "gear", "guestbook"),
    ("transcript", "stamp", "passage"),
    ("moths", "portrait", "record"),
]

EVIDENCE_COORDS = [
    ((155, 126), (444, 132), (318, 203)),
    ((149, 143), (309, 222), (445, 141)),
    ((141, 115), (292, 212), (457, 134)),
    ((129, 125), (301, 217), (446, 143)),
    ((128, 129), (298, 215), (446, 130)),
    ((160, 132), (308, 215), (453, 143)),
    ((146, 134), (310, 219), (450, 141)),
    ((149, 123), (307, 226), (448, 143)),
    ((145, 134), (307, 215), (461, 133)),
    ((149, 132), (308, 211), (457, 140)),
]

# Every cover identity has a social role and a story consequence. A convincing
# uniform can get the detective into staff-only archives; a civilian disguise
# blends better in a crowd but does not automatically grant restricted access.
COVER_IDENTITIES = [
    ("Manor steward", "Dinner guest"),
    ("Railway porter", "First-class passenger"),
    ("Hotel attendant", "Traveling guest"),
    ("Stagehand", "Theater patron"),
    ("Archive clerk", "Book dealer"),
    ("Garden assistant", "Botanical patron"),
    ("Dock laborer", "Shipping agent"),
    ("Observatory technician", "Visiting scholar"),
    ("Court bailiff", "Newspaper correspondent"),
    ("Crypt caretaker", "Family mourner"),
]

SECRET_REVEALS = [
    "Inside the private office is a receipt signed by Evelyn. Collins was not improvising; he was being paid to fail.",
    "A freight ledger names the train passenger who was supposedly dead long before the journey began.",
    "A service schedule lists Rowan as both patient and prisoner. Fenwick's clinic was built to silence witnesses.",
    "A hidden cue specifies a second blackout. Someone planned to kill the singer even if the first attempt failed.",
    "The archive's original census names another surviving Blackwell heir. Evelyn has been lying about the family tree.",
    "A second inventory describes the stolen specimen as a marker for an underground route, not a rare plant.",
    "Pike's off-books manifest lists nine silver moth parcels, each delivered before a different murder.",
    "The telescope's brass housing conceals a guest list. Evelyn attended meetings under a false name.",
    "The true verdict is still here: the Lantern was not a society of benefactors but a mechanism for disappearing people.",
    "The last secret is the cruelest: Evelyn chose the detective because each case would make vengeance feel inevitable.",
]

COVER_LINES = [
    "The servants do not recognize your face, but they know the cut of the steward's coat. Walk. Do not hurry.",
    "A porter can enter the baggage office without a second glance; a passenger cannot.",
    "Hotel staff move everywhere except where they are expected to look. The ledger is behind the locked service wing.",
    "Stagehands are invisible during scene changes. A patron in the wings is a scandal waiting to happen.",
    "The registrar's office is marked PRIVATE. Only clerks and people who move very quietly cross its threshold.",
    "A gardener can walk beneath the glass at midnight. The patron is confined to the lit walkway.",
    "The crates have a path of their own. The right coat lets you move like one more dock worker.",
    "An assistant's badge opens the dome controls. Without it, shadows and timing are your only allies.",
    "A bailiff's jacket turns a locked courtroom into a corridor. A reporter's questions would raise alarms.",
    "The caretaker knows where every crypt key belongs; the mourners know only where to stand.",
]

DECOY_LINES = [
    "A coin strikes the marble. The watchman turns toward the sound rather than your footprints.",
    "The metallic clink disappears under a hiss of steam. The guard breaks formation to investigate.",
    "A coin rings against the bellhop's trolley. Footsteps hurry toward the wrong corridor.",
    "A tiny sound in the darkened wings draws the stage guard away from the curtain.",
    "An echo skips across the tiled archive. Someone searches the shelves you have already left.",
    "The sound travels through glass and leaf. A watchman enters the wrong garden path.",
    "A coin taps the dock planks. The watchman mistakes it for a loose mooring ring.",
    "The dome amplifies the small metallic sound. The director's guard turns to investigate.",
    "A clink against an iron rail sends the bailiff toward the old evidence room.",
    "The coin falls into the stone silence. The caretaker looks toward the wrong tomb.",
]

RESTRICTED_ZONE = (370, 86, 515, 184)

# Furniture footprint atlas. These dimensions come from the actual PixelArt
# drawing methods below; a room's collision model is built from its artwork.
# Decorative objects (rugs, papers, windows, footprints, tiny candles) never
# block movement. Unlike v4, there are no invisible legacy desk rectangles.
SOLID_FURNITURE = {
    "bookcase": (0, 0, 51, 28), "bookshelf": (0, 0, 51, 28),
    "desk": (0, 0, 63, 31), "table": (0, 0, 50, 24),
    "armchair": (0, 0, 30, 24), "fireplace": (0, 0, 72, 34),
    "piano": (0, 0, 78, 39), "bench": (0, 0, 48, 17),
    "wardrobe": (0, 0, 32, 43), "counter": (0, 0, 76, 22),
    "judgebench": (0, 0, 125, 47), "altar": (0, 0, 74, 47),
    "coffin": (0, 0, 76, 32), "crate": (0, 0, 30, 27),
    "barrel": (-9, -11, 10, 9), "suitcase": (0, -4, 23, 18),
    "plant": (-9, -8, 10, 15), "pillar": (-14, -4, 14, 23),
    "statue": (0, -11, 25, 30), "telescope": (-39, -10, 35, 50),
    "scope": (0, 0, 22, 20), "globe": (-12, -12, 12, 12),
    "coatstand": (-10, -17, 10, 29),
}


def prop_collision(prop):
    """Solid pixel-art footprint. Tiny render shadows don't block movement."""
    kind, x, y, variant = prop
    bounds = SOLID_FURNITURE.get(kind)
    if bounds is None:
        return None
    ax, ay, bx, by = bounds
    # Narrow visual leaves shouldn't become invisible broad force fields.
    if kind == "plant":
        ax, ay, bx, by = -7, 2, 8, 13
    if kind == "coatstand":
        ax, ay, bx, by = -4, 9, 5, 25
    if kind == "telescope":
        ax, ay, bx, by = -21, 10, 29, 36
    return (x + ax, y + ay, x + bx, y + by)


def build_collisions(props):
    """Use the same prop list for what we see and what blocks movement."""
    solids = [
        (0, 0, WORLD_W, 38),
        (0, 0, 20, WORLD_H),
        (WORLD_W - 20, 0, WORLD_W, WORLD_H),
        (0, WORLD_H - 18, WORLD_W, WORLD_H),
    ]
    solids.extend(box for p in props if (box := prop_collision(p)) is not None)
    return solids


def solid_at(level, x, y, radius=4):
    for x1, y1, x2, y2 in level.collisions:
        if x + radius > x1 and x - radius < x2 and y + radius > y1 and y - radius < y2:
            return True
    return False


def find_nearest_open(level, xy, radius=4):
    """Snap accidental old saves and NPC positions to the nearest free tile."""
    x, y = xy
    if not solid_at(level, x, y, radius):
        return (float(x), float(y))
    for ring in range(4, 110, 4):
        candidates = []
        for angle in range(0, 360, 20):
            a = math.radians(angle)
            nx, ny = x + math.cos(a) * ring, y + math.sin(a) * ring
            if 24 <= nx <= WORLD_W - 24 and 42 <= ny <= WORLD_H - 23 and not solid_at(level, nx, ny, radius):
                candidates.append((nx, ny))
        if candidates:
            return min(candidates, key=lambda p: (p[0] - x) ** 2 + (p[1] - y) ** 2)
    return (float(level.start[0]), float(level.start[1]))


class NavigationGrid:
    """Compact room-scale A*: click movement and guard patrol share one map."""

    def __init__(self, level, step=6):
        self.level = level
        self.step = step
        self.width = WORLD_W // step + 1
        self.height = WORLD_H // step + 1
        self.clear = {
            (i, j) for i in range(4, self.width - 3)
            for j in range(7, self.height - 3)
            if not solid_at(level, i * step, j * step, 5)
        }

    def closest(self, xy):
        i = round(xy[0] / self.step)
        j = round(xy[1] / self.step)
        if (i, j) in self.clear:
            return (i, j)
        for rad in range(1, 16):
            options = [(i + dx, j + dy) for dx in range(-rad, rad + 1)
                       for dy in range(-rad, rad + 1)
                       if abs(dx) == rad or abs(dy) == rad]
            options = [pt for pt in options if pt in self.clear]
            if options:
                return min(options, key=lambda pt: (pt[0] - i) ** 2 + (pt[1] - j) ** 2)
        return None

    def path(self, start, goal):
        src, dst = self.closest(start), self.closest(goal)
        if src is None or dst is None:
            return []
        if src == dst:
            return [goal] if not solid_at(self.level, *goal) else []
        q = [(0, src)]
        g = {src: 0}
        came = {}
        closed = set()
        while q:
            _, here = heapq.heappop(q)
            if here in closed:
                continue
            closed.add(here)
            if here == dst:
                break
            i, j = here
            for nb in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
                if nb not in self.clear or nb in closed:
                    continue
                cost = g[here] + 1
                if cost < g.get(nb, 1e10):
                    came[nb] = here
                    g[nb] = cost
                    heapq.heappush(q, (cost + abs(nb[0] - dst[0]) + abs(nb[1] - dst[1]), nb))
        if dst not in came:
            return []
        path = []
        cur = dst
        while cur != src:
            path.append((cur[0] * self.step, cur[1] * self.step))
            cur = came[cur]
        path.reverse()
        # Remove collinear waypoints without allowing a shortcut through walls.
        compact = []
        for v in path:
            if len(compact) > 1:
                a, b = compact[-2:]
                if (a[0] == b[0] == v[0]) or (a[1] == b[1] == v[1]):
                    compact[-1] = v
                    continue
            compact.append(v)
        if not solid_at(self.level, *goal):
            compact.append(goal)
        return compact


def make_level(chapter: int) -> Level:
    ch = CHAPTERS[chapter]
    props = list(ROOM_PROPS[chapter])
    objs = [
        Item("uniform", "Clothes left unattended", 90, 278, "coatstand", "A second identity hangs among these coats.")]
    for j, (name, detail) in enumerate(ch["clues"]):
        # Evidence belongs to the public investigation, not the guarded
        # infiltration. The private office contains OPTIONAL, story-rich proof.
        x, y = EVIDENCE_COORDS[chapter][j]
        if RESTRICTED_ZONE[0] - 12 < x < RESTRICTED_ZONE[2] + 12 and y < RESTRICTED_ZONE[3] + 16:
            x, y = 327 + (chapter % 3) * 8, 268 + (j % 2) * 14
        objs.append(Item(f"clue_{j}", name, x, y, EVIDENCE_SHAPES[chapter][j], detail))
    # Quiet optional environmental discoveries also exist: these offer narrative
    # texture but never replace the three mandatory pieces of physical proof.
    optional_coords = [(188, 303), (360, 110), (487, 290)]
    for j, p in enumerate(optional_coords):
        objs.append(Item(f"optional_{j}", f"Margin note {j + 1}", p[0], p[1], "note", ch["cinematic"][j + 6], True))

    # Hiding spots now correspond to actual visible wardrobes, planters, or
    # stacked crates. There are no floating marker letters at their positions.
    props.extend([
        ("wardrobe", 65, 306, 0),
        ("plant", 479, 306, chapter % 3),
        ("crate", 34, 201, chapter % 3),
    ])
    props.append(("coatstand", 90, 263, chapter % 4))
    civilians = [
        Agent(363, 313, "left", coat=(chapter + 1) % 4, hair=(chapter + 2) % 4, skin=1),
        Agent(393, 319, "right", coat=(chapter + 2) % 4, hair=(chapter + 3) % 4, skin=0),
    ]
    level = Level(
        chapter=chapter,
        theme=THEMES[chapter]["name"],
        props=props,
        collisions=build_collisions(props),
        objects=objs,
        witness=Agent(204, 313, "down", coat=(chapter + 1) % 4, hair=chapter % 4, skin=(chapter + 1) % 4),
        killer=Agent(462, 148, "left", coat=(chapter + 2) % 4, hair=(chapter + 3) % 4, skin=1, hat=chapter % 2 == 0),
        civilians=civilians,
        hide_positions=[(81, 320), (485, 319), (52, 212)],
        blend_zones=[(377, 316, 48)],
        patrol=[(229, 246), (412, 247), (405, 302), (270, 287)],
        start=(121, 333),
        cards=[ch["title"], ch["room_name"], ch["victim"]],
    )
    # Characters should never materialize within a visible solid prop.
    level.start = find_nearest_open(level, level.start)
    level.witness.x, level.witness.y = find_nearest_open(level, level.witness.feet)
    level.killer.x, level.killer.y = find_nearest_open(level, level.killer.feet)
    for npc in level.civilians:
        npc.x, npc.y = find_nearest_open(level, npc.feet)
    level.patrol = [find_nearest_open(level, pt) for pt in level.patrol]
    return level


# -----------------------------------------------------------------------------
# PIXEL-ART RENDERER
# All rooms are rendered once at a fixed logical pixel resolution, then scaled
# using nearest-neighbor sampling. The resulting look is deliberate, rather
# than a collection of stroked rectangles redrawn around the player.
# -----------------------------------------------------------------------------

class PixelArt:
    def __init__(self, chapter: int, seed: int = 101):
        self.chapter = chapter
        self.palette = THEMES[chapter]
        self.rng = random.Random(seed + chapter * 1009)
        self.image = Image.new("RGB", (WORLD_W, WORLD_H), self.palette["floor"])
        self.d = ImageDraw.Draw(self.image)
        self.lights = []
        self.particles = []

    def rect(self, xy, fill, outline=None, width=1):
        self.d.rectangle(tuple(map(int, xy)), fill=fill, outline=outline, width=width)

    def line(self, coords, fill, width=1, joint="curve"):
        self.d.line(tuple(int(v) for v in coords), fill=fill, width=width, joint=joint)

    def ellipse(self, box, fill, outline=None, width=1):
        self.d.ellipse(tuple(map(int, box)), fill=fill, outline=outline, width=width)

    def polygon(self, points, fill, outline=None):
        self.d.polygon([(int(x), int(y)) for x, y in points], fill=fill, outline=outline)

    def stroke(self, x, y, w, h, fill, border=(10, 16, 22)):
        self.rect((x, y, x + w, y + h), fill, border)
        self.line((x + 2, y + 2, x + w - 2, y + 2), light(fill, .07))

    def twinkle(self, x, y, color=(239, 201, 129)):
        self.rect((x, y, x + 1, y + 1), color)
        self.rect((x - 2, y, x + 3, y), color)
        self.rect((x, y - 2, x, y + 3), color)

    def noise(self, count=3000):
        # Slightly irregular color variation gives the tiles a hand-crafted
        # texture without an artificial glossy gradient.
        p = self.palette
        for _ in range(count):
            x = self.rng.randrange(20, WORLD_W - 20)
            y = self.rng.randrange(39, WORLD_H - 19)
            col = p["floor2"] if self.rng.random() < .37 else shade(p["floor"], .82)
            self.d.point((x, y), fill=col)

    def floor(self):
        p = self.palette
        self.rect((20, 35, WORLD_W - 20, WORLD_H - 18), p["floor"])
        if self.chapter in {0, 2, 4, 8}:
            for y in range(39, WORLD_H - 18, 18):
                for x in range(20 + (9 if y // 18 % 2 else 0), WORLD_W - 20, 32):
                    self.rect((x, y, min(x + 31, WORLD_W - 20), y + 17),
                              p["floor"] if ((x + y) // 10) % 4 else p["floor2"], p["floor_line"])
                    self.line((x + 3, y + 3, x + 14, y + 3), shade(p["floor_line"], .78))
        elif self.chapter in {1, 3, 6}:
            for y in range(40, WORLD_H - 20, 11):
                self.line((22, y, WORLD_W - 22, y), p["floor_line"])
                for x in range(22 + (13 if (y // 11) % 2 else 0), WORLD_W - 22, 56):
                    self.line((x, y + 1, x, y + 9), shade(p["floor_line"], .80))
        else:
            for y in range(38, WORLD_H - 18, 23):
                for x in range(20, WORLD_W - 20, 23):
                    fill = p["floor2"] if ((x // 23) ^ (y // 23)) & 1 else p["floor"]
                    self.rect((x, y, x + 22, y + 22), fill, p["floor_line"])
        self.noise(750)

    def boundary(self):
        p = self.palette
        self.rect((0, 0, WORLD_W, 38), p["wall"])
        self.rect((0, 0, 19, WORLD_H), p["wall"])
        self.rect((WORLD_W - 19, 0, WORLD_W, WORLD_H), p["wall"])
        self.rect((0, WORLD_H - 17, WORLD_W, WORLD_H), p["wall"])
        self.rect((19, 31, WORLD_W - 19, 36), p["trim"])
        self.rect((19, 37, WORLD_W - 19, 39), shade(p["trim"], .55))
        self.rect((19, WORLD_H - 21, WORLD_W - 19, WORLD_H - 18), shade(p["trim"], .70))
        for x in range(24, WORLD_W - 20, 35):
            self.line((x, 4, x, 28), p["wall2"])
            self.rect((x + 3, 9, x + 29, 23), p["wall2"], shade(p["wall2"], .74))
            self.rect((x + 7, 12, x + 26, 19), shade(p["wall2"], .86))
        for y in range(44, WORLD_H - 25, 39):
            self.line((4, y, 15, y), p["trim"])
            self.line((WORLD_W - 15, y, WORLD_W - 3, y), p["trim"])
        # small understated window light sources set into the far wall
        for wx in (74, 369, 476):
            self.window(wx, 6, 26, 27, self.palette["warm"])

    def window(self, x, y, w=24, h=25, color=(235, 177, 92)):
        # Architectural fixtures stay within interior wall bands; a window
        # that crosses the world border is simply not rendered half-cut.
        if x < 22 or x + w > WORLD_W - 22 or y < 2 or y + h > WORLD_H - 22:
            return
        self.stroke(x, y, w, h, (20, 31, 51), (124, 96, 69))
        self.rect((x + 4, y + 3, x + w - 4, y + h - 4), color)
        self.rect((x + 6, y + 3, x + 8, y + h - 4), shade(color, .78))
        self.line((x + w // 2, y + 3, x + w // 2, y + h - 3), (72, 55, 50))
        self.line((x + 3, y + h // 2, x + w - 4, y + h // 2), (72, 55, 50))
        self.lights.append((x + w / 2, y + h / 2, 40, color))

    def small_rug(self, x, y, w, h, color=None):
        """Render a tightly bounded, pixel-woven rug with no clipped triangles.

        V3's repeated triangle border motifs sometimes extended beyond the
        carpet edge; at nearest-neighbor scaling they became jagged gold
        spikes that looked like rendering artifacts. This version uses small,
        square stitches and muted diamond-shaped rosettes drawn entirely
        inside the patterned border.
        """
        p = self.palette
        color = color or p["rug"]
        edging = p["rug_border"]
        dark = shade(color, .70)
        trim = shade(edging, .76)
        self.rect((x, y, x + w, y + h), dark, edging)
        self.rect((x + 3, y + 3, x + w - 3, y + h - 3), edging)
        self.rect((x + 7, y + 7, x + w - 7, y + h - 7), color)
        self.rect((x + 11, y + 11, x + w - 11, y + h - 11), None, trim)
        # Regular embroidered stitches, always confined to the border.
        for px in range(x + 10, x + w - 9, 10):
            self.rect((px, y + 5, px + 3, y + 6), color)
            self.rect((px, y + h - 6, px + 3, y + h - 5), color)
        for py in range(y + 11, y + h - 10, 11):
            self.rect((x + 5, py, x + 6, py + 3), color)
            self.rect((x + w - 6, py, x + w - 5, py + 3), color)
        # Restrained interior woven rosettes: square/diamond pixel clusters.
        # Not polygons, so nearest-neighbor zoom produces no diagonal spikes.
        if w >= 80 and h >= 47:
            cy = y + h // 2
            for cx in range(x + 30, x + w - 26, 32):
                self.rect((cx - 4, cy - 1, cx + 4, cy + 1), trim)
                self.rect((cx - 1, cy - 4, cx + 1, cy + 4), trim)
                self.rect((cx - 2, cy - 2, cx + 2, cy + 2), color)

    def bookcase(self, x, y, variant=0):
        self.stroke(x, y, 51, 28, (73, 48, 37), (27, 21, 23))
        self.rect((x + 2, y + 2, x + 48, y + 5), (119, 82, 55))
        spine = [(132, 70, 66), (39, 71, 93), (114, 90, 52), (56, 82, 67), (77, 58, 79), (164, 116, 71)]
        for row in range(2):
            yy = y + 7 + row * 10
            for col in range(9):
                xx = x + 5 + col * 5
                h = 7 if (col * 7 + row + variant) % 3 else 5
                color = spine[(col + row * 4 + variant) % len(spine)]
                self.rect((xx, yy + (7 - h), xx + 3, yy + 8), color, (21, 17, 19))
                if col % 3 == 0:
                    self.line((xx + 1, yy + 2, xx + 1, yy + 6), (207, 160, 104))
            self.line((x + 3, yy + 10, x + 48, yy + 10), (146, 103, 69))
        self.rect((x + 3, y + 24, x + 48, y + 27), (41, 27, 24))

    def desk(self, x, y, variant=0):
        self.ellipse((x + 3, y + 29, x + 64, y + 36), (24, 18, 22))
        self.stroke(x, y, 63, 31, (103, 65, 45), (40, 28, 26))
        self.rect((x + 4, y + 4, x + 59, y + 26), (121, 80, 52), (150, 102, 62))
        self.line((x + 5, y + 10, x + 58, y + 10), (86, 50, 35))
        self.line((x + 10, y + 22, x + 53, y + 22), (88, 50, 33))
        self.rect((x + 12, y + 6, x + 27, y + 16), (205, 181, 137), (116, 98, 82))
        self.line((x + 15, y + 10, x + 24, y + 10), (111, 86, 71))
        self.rect((x + 47, y + 11, x + 52, y + 14), (198, 168, 93))
        if variant % 2:
            self.rect((x + 28, y + 17, x + 41, y + 26), (54, 50, 54), (22, 23, 27))
            self.line((x + 30, y + 20, x + 39, y + 20), (169, 154, 134))

    def table(self, x, y, variant=0):
        self.ellipse((x + 2, y + 18, x + 49, y + 27), (31, 23, 26))
        self.ellipse((x, y, x + 50, y + 23), (117, 74, 55), (52, 38, 33))
        self.ellipse((x + 4, y + 3, x + 45, y + 18), (135, 92, 64), (167, 118, 82))
        if variant == 0:
            self.rect((x + 21, y + 7, x + 28, y + 13), (214, 192, 154), (72, 59, 43))
            self.rect((x + 23, y + 5, x + 26, y + 8), (229, 173, 88))

    def armchair(self, x, y, variant=0):
        c = (87, 45, 51) if variant == 0 else (55, 62, 82)
        self.ellipse((x + 3, y + 22, x + 29, y + 34), (32, 25, 28))
        self.stroke(x, y, 30, 24, c, (38, 27, 31))
        self.rect((x + 5, y + 7, x + 25, y + 21), light(c, .05), shade(c, .70))
        self.rect((x + 2, y + 2, x + 7, y + 19), shade(c, .85))
        self.rect((x + 23, y + 2, x + 28, y + 19), shade(c, .85))
        self.line((x + 8, y + 8, x + 22, y + 8), light(c, .13))

    def fireplace(self, x, y):
        self.stroke(x, y, 72, 34, (90, 65, 57), (40, 29, 31))
        self.rect((x + 9, y + 4, x + 63, y + 28), (18, 15, 22), (138, 95, 64))
        self.rect((x + 3, y, x + 68, y + 5), (132, 91, 64), (182, 131, 87))
        self.rect((x + 11, y + 23, x + 60, y + 29), (59, 29, 23))
        self.lights.append((x + 36, y + 18, 96, (244, 135, 64)))
        self.particles.append(("flames", x + 30, y + 15))
        for xx in (x + 20, x + 29, x + 40, x + 53):
            self.polygon([(xx - 4, y + 26), (xx, y + 11 + self.rng.randrange(5)), (xx + 6, y + 26)], (234, 125, 52))
            self.polygon([(xx - 2, y + 24), (xx, y + 16), (xx + 3, y + 24)], (252, 204, 102))

    def clock(self, x, y, variant=0):
        self.ellipse((x - 8, y - 7, x + 8, y + 8), (46, 33, 26), (140, 101, 68))
        self.ellipse((x - 5, y - 5, x + 5, y + 5), (222, 201, 164), (83, 67, 49))
        self.line((x, y, x + 3, y - 2), (36, 31, 28))
        self.line((x, y, x, y - 4), (36, 31, 28))
        for i in range(12):
            a = i * 2 * math.pi / 12
            xx = x + 4 * math.cos(a)
            yy = y + 4 * math.sin(a)
            self.d.point((int(xx), int(yy)), fill=(72, 52, 40))

    def plant(self, x, y, variant=0):
        self.ellipse((x - 9, y + 7, x + 10, y + 15), (42, 30, 26))
        self.ellipse((x - 7, y + 4, x + 8, y + 12), (135, 79, 56), (78, 48, 38))
        greens = [(45, 95, 65), (52, 113, 78), (75, 117, 69), (38, 80, 68)]
        for i in range(9):
            a = i * math.pi * .65 + variant
            r = 8 + (i % 3) * 3
            px = x + math.cos(a) * r
            py = y + math.sin(a) * r * .65
            self.line((x, y + 2, px, py), (34, 75, 57))
            self.ellipse((px - 5, py - 3, px + 5, py + 4), greens[(i + variant) % 4], (32, 70, 52))
        if variant == 2:
            for i in range(3):
                self.ellipse((x - 6 + i * 5, y - 6, x - 3 + i * 5, y - 2), (185, 122, 85))

    def candle(self, x, y, variant=0):
        self.ellipse((x - 4, y + 3, x + 5, y + 6), (126, 96, 56))
        self.rect((x - 2, y - 5, x + 2, y + 4), (220, 201, 161), (131, 112, 86))
        self.polygon([(x - 2, y - 7), (x + 1, y - 13), (x + 3, y - 6)], (255, 185, 75))
        self.lights.append((x, y, 45, (245, 184, 96)))
        self.particles.append(("candle", x, y - 11))

    def painting(self, x, y, variant=0):
        self.stroke(x, y, 30, 24, (131, 93, 53), (57, 45, 41))
        self.rect((x + 4, y + 4, x + 26, y + 20), (31, 45, 60), (172, 131, 80))
        self.ellipse((x + 12, y + 6, x + 18, y + 12), (179, 136, 103))
        self.polygon([(x + 8, y + 19), (x + 11, y + 12), (x + 19, y + 12), (x + 22, y + 19)], (84, 59, 71))
        if variant == 1:
            self.rect((x + 11, y + 14, x + 20, y + 18), (51, 55, 79))

    def pillow_piano(self, x, y, variant=0):
        self.stroke(x, y, 78, 39, (27, 26, 35), (16, 18, 25))
        self.polygon([(x + 7, y + 7), (x + 69, y + 7), (x + 58, y + 33), (x + 19, y + 33)], (41, 41, 53), (96, 74, 62))
        self.rect((x + 8, y + 25, x + 65, y + 36), (215, 201, 168), (24, 25, 29))
        for k in range(12):
            self.line((x + 10 + k * 4, y + 26, x + 10 + k * 4, y + 34), (62, 56, 60))
        for k in (1, 3, 6, 8, 10):
            self.rect((x + 10 + k * 4, y + 26, x + 12 + k * 4, y + 30), (33, 33, 37))

    def scattered_paper(self, x, y, variant=0):
        self.polygon([(x - 7, y - 4), (x + 6, y - 5), (x + 8, y + 5), (x - 6, y + 6)], (215, 191, 153), (102, 79, 58))
        for k in range(3):
            self.line((x - 4, y - 1 + 2 * k, x + 4 - k, y - 1 + 2 * k), (132, 112, 88))
        if variant:
            self.rect((x + 2, y + 1, x + 6, y + 3), (136, 51, 51))

    def bootprints(self, x, y):
        for i in range(4):
            xx = x + i * 6
            yy = y + (i % 2) * 8
            self.ellipse((xx - 3, yy - 5, xx + 2, yy + 2), (57, 46, 44))
            self.ellipse((xx - 2, yy - 3, xx + 1, yy), (92, 77, 68))

    def glass(self, x, y, variant=0):
        for i in range(8):
            a = i * 2.39 + variant
            r = 5 + (i % 3) * 4
            xx = x + r * math.cos(a)
            yy = y + r * math.sin(a)
            self.polygon([(xx - 2, yy + 3), (xx + 3, yy - 5), (xx + 5, yy + 2)], (96, 149, 153), (187, 220, 214))

    def rope(self, x, y):
        pts = []
        for i in range(15):
            pts.append((x - 14 + i * 2, y + math.sin(i * .57) * 4))
        self.d.line(pts, fill=(159, 127, 77), width=3)
        self.d.line(pts, fill=(221, 188, 129), width=1)

    def crate(self, x, y, variant=0):
        self.stroke(x, y, 30, 27, (117, 84, 59), (52, 38, 33))
        self.rect((x + 3, y + 3, x + 26, y + 23), (130, 97, 65), (169, 129, 82))
        self.line((x + 4, y + 4, x + 25, y + 22), (76, 54, 43), 2)
        self.line((x + 4, y + 22, x + 25, y + 4), (76, 54, 43), 2)

    def barrel(self, x, y):
        self.ellipse((x - 9, y - 11, x + 10, y + 9), (78, 56, 42), (32, 31, 28))
        self.ellipse((x - 7, y - 9, x + 8, y + 7), (112, 79, 57), (158, 124, 79))
        self.line((x - 7, y, x + 8, y), (47, 52, 55))
        self.line((x, y - 9, x, y + 7), (47, 52, 55))

    def lantern(self, x, y):
        self.ellipse((x - 6, y + 4, x + 6, y + 10), (34, 26, 29))
        self.stroke(x - 3, y - 4, 7, 13, (234, 169, 73), (75, 65, 53))
        self.line((x - 6, y - 6, x + 6, y - 6), (124, 98, 63))
        self.lights.append((x, y, 63, (236, 161, 79)))
        self.particles.append(("lamp", x, y))

    def water(self, x, y, variant=0):
        self.rect((x, y, x + 113, y + 38), (18, 48, 67), (40, 68, 82))
        for i in range(12):
            xx = x + 6 + i * 8
            yy = y + 6 + (i * 5 + variant * 8) % 25
            self.line((xx, yy, xx + 8, yy), (56, 97, 116))
            self.d.point((xx + 2, yy - 1), (129, 145, 149))

    def stage(self, x, y):
        self.rect((x, y, x + 366, y + 107), (78, 30, 48), (157, 72, 83))
        for xx in range(x, x + 363, 16):
            self.line((xx, y + 7, xx + 4, y + 91), (107, 43, 58))
        self.rect((x + 10, y + 100, x + 356, y + 106), (194, 125, 72))
        for xx in range(x + 19, x + 352, 24):
            self.ellipse((xx, y + 98, xx + 5, y + 103), (244, 202, 108))

    def telescope(self, x, y):
        self.ellipse((x - 12, y + 27, x + 26, y + 41), (31, 29, 37))
        self.line((x + 7, y + 30, x + 31, y + 8), (103, 119, 131), 6)
        self.line((x + 7, y + 30, x - 19, y + 15), (103, 119, 131), 6)
        self.line((x + 6, y + 28, x + 6, y + 50), (129, 135, 142), 5)
        self.polygon([(x - 33, y + 10), (x + 28, y - 10), (x + 35, y + 7), (x - 26, y + 26)], (55, 76, 88),
                     (149, 154, 147))
        self.line((x - 28, y + 10, x + 31, y - 6), (154, 163, 170), 2)
        self.ellipse((x - 39, y + 8, x - 28, y + 24), (26, 38, 54), (144, 143, 146))

    def portrait(self, x, y, variant=0):
        self.stroke(x, y, 34, 30, (133, 92, 54), (65, 48, 42))
        self.rect((x + 4, y + 4, x + 30, y + 26), (36, 46, 63), (188, 134, 76))
        self.ellipse((x + 13, y + 7, x + 21, y + 16), (185, 145, 111))
        self.polygon([(x + 7, y + 25), (x + 10, y + 17), (x + 23, y + 17), (x + 27, y + 25)], (88, 68, 76))
        self.rect((x + 6, y + 26, x + 29, y + 28), (128, 96, 61))

    def small_object(self, kind, x, y, variant=0):
        # Keep item silhouettes crisp and recognizable. No text overlays.
        if kind in {"paper", "letter", "note", "bill", "cue", "sketch", "inventory", "transcript", "starchart",
                    "guestbook", "cargo", "tide", "record"}:
            self.scattered_paper(x, y, variant)
            if kind in {"starchart", "tide", "sketch"}:
                self.line((x - 3, y + 2, x + 4, y - 3), (52, 79, 95))
            if kind in {"bill", "inventory", "cargo"}:
                self.rect((x + 3, y + 2, x + 6, y + 4), (120, 45, 46))
        elif kind in {"clock", "bell"}:
            self.clock(x, y, variant)
        elif kind in {"footprints"}:
            self.bootprints(x, y)
        elif kind in {"key", "gear"}:
            self.ellipse((x - 5, y - 5, x + 3, y + 3), (124, 119, 108), (198, 190, 146))
            self.line((x + 3, y, x + 12, y + 4), (197, 174, 118), 2)
            self.line((x + 8, y + 2, x + 9, y + 7), (197, 174, 118), 2)
        elif kind in {"seal", "stamp", "moths"}:
            self.ellipse((x - 7, y - 5, x + 7, y + 5), (145, 51, 57), (96, 41, 44))
            self.polygon([(x, y - 4), (x - 5, y - 2), (x, y), (x + 5, y - 2)], (208, 189, 146))
            self.polygon([(x, y), (x - 4, y + 4), (x, y + 2), (x + 4, y + 4)], (181, 165, 136))
        elif kind in {"ticket", "film"}:
            self.rect((x - 11, y - 6, x + 12, y + 5), (203, 175, 124), (114, 85, 61))
            for k in range(3):
                self.rect((x - 8 + k * 7, y - 3, x - 4 + k * 7, y + 2), (35, 34, 36))
        elif kind in {"rope"}:
            self.rope(x, y)
        elif kind in {"glass"}:
            self.glass(x, y, variant)
        elif kind in {"velvet"}:
            self.polygon([(x - 9, y - 3), (x + 2, y - 8), (x + 10, y + 4), (x - 3, y + 7)], (102, 30, 53),
                         (160, 76, 82))
        elif kind in {"burned"}:
            self.scattered_paper(x, y, 1)
            self.polygon([(x + 2, y - 5), (x + 8, y - 4), (x + 7, y + 3), (x + 4, y)], (54, 35, 30))
        elif kind in {"passage"}:
            self.rect((x - 10, y - 6, x + 8, y + 10), (22, 28, 37), (107, 84, 63))
            self.line((x - 7, y + 7, x + 7, y - 2), (68, 60, 59))
        else:
            self.scattered_paper(x, y, variant)

    def prop(self, p):
        kind, x, y, variant = p
        if kind in {"rug", "runner", "glassfloor", "stonefloor"}:
            if kind == "rug":
                self.small_rug(x, y, 300, 112)
            elif kind == "runner":
                self.small_rug(x, y, 285, 60)
            elif kind == "glassfloor":
                self.small_rug(x, y, 388, 173, (38, 83, 73))
            elif kind == "stonefloor":
                self.small_rug(x, y, 328, 179, (52, 48, 65))
        elif kind in {"bookcase", "bookshelf"}:
            self.bookcase(x, y, variant)
        elif kind == "desk":
            self.desk(x, y, variant)
        elif kind == "table":
            self.table(x, y, variant)
        elif kind == "armchair":
            self.armchair(x, y, variant)
        elif kind == "fireplace":
            self.fireplace(x, y)
        elif kind == "plant":
            self.plant(x, y, variant)
        elif kind == "piano":
            self.pillow_piano(x, y, variant)
        elif kind in {"clock", "grandfather"}:
            self.clock(x, y, variant)
        elif kind == "candle":
            self.candle(x, y, variant)
        elif kind == "painting":
            self.painting(x, y, variant)
        elif kind == "portrait":
            self.portrait(x, y, variant)
        elif kind == "window":
            self.window(x, y, 31, 26)
        elif kind == "crate":
            self.crate(x, y, variant)
        elif kind == "barrel":
            self.barrel(x, y)
        elif kind == "lantern":
            self.lantern(x, y)
        elif kind == "lamp":
            self.candle(x, y, variant)
        elif kind == "glass":
            self.glass(x, y, variant)
        elif kind == "bench":
            self.stroke(x, y, 48, 17, (112, 71, 49), (42, 30, 29))
            self.rect((x + 4, y + 4, x + 43, y + 12), (143, 97, 61))
        elif kind in {"wardrobe", "counter", "judgebench", "altar", "coffin"}:
            w = {"wardrobe": 32, "counter": 76, "judgebench": 125, "altar": 74, "coffin": 76}[kind]
            h = {"wardrobe": 43, "counter": 22, "judgebench": 47, "altar": 47, "coffin": 32}[kind]
            color = (91, 61, 49) if kind != "coffin" else (58, 54, 62)
            self.stroke(x, y, w, h, color, (37, 30, 28))
            self.rect((x + 4, y + 4, x + w - 4, y + h - 4), light(color, .1), (140, 101, 69))
            if kind == "coffin":
                self.line((x + w // 2, y + 5, x + w // 2, y + h - 5), (185, 155, 99))
        elif kind in {"suitcase"}:
            self.stroke(x, y, 23, 18, (113, 79, 57), (40, 35, 31))
            self.rect((x + 8, y - 4, x + 15, y + 1), (35, 33, 35), (165, 139, 89))
        elif kind == "coatstand":
            self.ellipse((x - 6, y + 21, x + 8, y + 29), (49, 42, 38))
            self.line((x, y - 17, x, y + 25), (93, 68, 50), 3)
            self.line((x - 10, y - 11, x + 10, y - 11), (93, 68, 50), 3)
        elif kind == "pillar":
            self.ellipse((x - 14, y - 4, x + 14, y + 7), (114, 106, 102), (60, 61, 70))
            self.rect((x - 10, y + 3, x + 10, y + 23), (92, 93, 98), (49, 53, 59))
        elif kind == "stage":
            self.stage(x, y)
        elif kind == "curtain":
            for xx in range(x, x + 28, 4):
                self.rect((xx, y, xx + 3, y + 102), (107, 35 + xx % 13, 57))
        elif kind == "footlight":
            self.candle(x, y, 0)
        elif kind == "water":
            self.water(x, y, variant)
        elif kind == "dockfloor":
            self.small_rug(x, y, 418, 183, (85, 69, 52))
        elif kind == "telescope":
            self.telescope(x, y)
        elif kind == "scope":
            self.stroke(x, y, 22, 20, (61, 76, 85), (37, 46, 54))
        elif kind == "globe":
            self.ellipse((x - 12, y - 12, x + 12, y + 12), (51, 91, 112), (160, 131, 83))
            self.polygon([(x - 5, y - 9), (x + 4, y - 3), (x - 3, y + 8), (x - 10, y + 2)], (79, 110, 89))
        elif kind == "statue":
            self.stroke(x, y, 25, 30, (100, 100, 111), (52, 53, 65))
            self.ellipse((x + 6, y - 11, x + 20, y + 5), (120, 120, 127))
        else:
            self.small_object(kind, x, y, variant)

    def vignette(self):
        # Fixed-radius subtle dark edges: pixel art first, atmosphere second.
        overlay = Image.new("RGBA", self.image.size, (0, 0, 0, 0))
        op = ImageDraw.Draw(overlay)
        for n in range(16):
            alpha = int(2.6 * (16 - n))
            op.rectangle((n, n, WORLD_W - n - 1, WORLD_H - n - 1), outline=(6, 10, 20, alpha), width=1)
        self.image = Image.alpha_composite(self.image.convert("RGBA"), overlay).convert("RGB")
        self.d = ImageDraw.Draw(self.image)

    def lighting(self):
        # Warm light falls naturally across nearby floor tiles.
        if not self.lights:
            return
        overlay = Image.new("RGBA", self.image.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)
        for lx, ly, radius, color in self.lights:
            for k in range(int(radius), 0, -7):
                a = max(0, int((1 - k / radius) * 5))
                d.ellipse((lx - k, ly - k * .62, lx + k, ly + k * .62), fill=(*color, a))
        self.image = Image.alpha_composite(self.image.convert("RGBA"), overlay).convert("RGB")
        self.d = ImageDraw.Draw(self.image)

    def render(self, level: Level):
        self.floor()
        self.boundary()
        # Broad rugs are laid first; physical props go on top of them.
        for prop in level.props:
            if prop[0] in {"rug", "runner", "glassfloor", "stonefloor", "dockfloor", "water"}:
                self.prop(prop)
        for prop in level.props:
            if prop[0] not in {"rug", "runner", "glassfloor", "stonefloor", "dockfloor", "water"}:
                self.prop(prop)
        # Re-draw clue items on top of furniture so they are visibly discoverable.
        for j, item in enumerate(level.objects):
            if not item.secret and item.id != "uniform":
                self.small_object(item.kind, item.x, item.y, j)
        # Dense hand-placed little visual details, instead of floating UI symbols.
        for _ in range(115):
            x = self.rng.randint(25, WORLD_W - 26)
            y = self.rng.randint(45, WORLD_H - 25)
            if self.rng.random() < .22:
                self.d.point((x, y), fill=(154, 119, 87))
        self.lighting()
        self.vignette()
        return self.image


# -----------------------------------------------------------------------------
# DIRECTIONAL CHARACTER ANIMATION
# Characters are 24x32 low-resolution pixel figures, not Tk shapes pretending
# to be sprites. Walks have independently phased legs, arms, coat tails, and a
# subtle body bob. All four directions have distinct geometry.
# -----------------------------------------------------------------------------

SKIN_SWATCHES = [
    (199, 146, 116),
    (231, 186, 146),
    (163, 107, 78),
    (112, 77, 66),
]
HAIR_SWATCHES = [
    (63, 39, 33),
    (136, 83, 46),
    (35, 35, 43),
    (188, 172, 143),
]
COAT_SWATCHES = [
    (100, 70, 78),
    (47, 75, 97),
    (67, 88, 73),
    (125, 93, 67),
]
ACCESSORY_COLORS = [
    (218, 182, 101),
    (180, 193, 202),
    (163, 99, 112),
    (95, 155, 148),
]

# HAND-CRAFTED 24x26 CHARACTER ART ATLAS
# Each row is a raster line. These shapes are used on case cards,
# inventory drawings, deduction threads and little in-world flourishes.
# . transparent, o outline, p paper, g gold, b blue, r red, l green,
# w steel, c leather, f skin. The pixels are embedded in the one .py file.
ICON_RASTERS = {
    'clock': (
        '........................',
        '........................',
        '.........ccccc..........',
        '.........ccccc..........',
        '.........ccccco.........',
        '.......oocccccooo.......',
        '......ooooggggoooo......',
        '.....ooogggcggggooo.....',
        '....ooogcgoopcgggooo....',
        '....oogggpoopppgggoo....',
        '....ooggppooppppcgoo....',
        '...oogcpppoopppppggoo...',
        '...ooggpppoopppppggoo...',
        '...oocgpppoopppppcgoo...',
        '...ooggppppooopppggoo...',
        '...ooggpppppppoooggoo...',
        '....oocgppppppppogoo....',
        '....oogggppppppgggoo....',
        '....oooggcppppcggooo....',
        '.....ooogggcggggooo.....',
        '......ooooggggoooo......',
        '.......oooooooooo.......',
        '.........oooooo.........',
        '........................',
        '........................',
        '........................',
    ),
    'footprints': (
        '........................',
        '.......p................',
        '......ppppp.............',
        '.......p.pp.............',
        '......ooopp.............',
        '.....orrco..............',
        '....orrrrco.............',
        '....orrrrco.............',
        '....orrrrco.............',
        '....ocrrcco......p......',
        '....occccco.....ppp.....',
        '.....occco.......p......',
        '......ooo...............',
        '.............ooo........',
        '............occco.......',
        '...........ocrrcco......',
        '...........orrrrco......',
        '...........orrrrco......',
        '...........orrrrco......',
        '...........ocrrcco......',
        '............occco.......',
        '.............ooo........',
        '........................',
        '........................',
        '........................',
        '........................',
    ),
    'letter': (
        '........................',
        '........................',
        '..................o.....',
        '....ooooooooooooooo.....',
        '....oopoooooooooooo.....',
        '....ooppprppppppppo.....',
        '....oopprrrpppppppoo....',
        '....ooppprrrppppppoo....',
        '.....oppccrrrcccppro....',
        '.....oppppprrpppprrr....',
        '.....opppppprrpprrro....',
        '.....oppccccrrrcrrpo....',
        '.....oppppppprrrrrpoo...',
        '.....ooppppppprrrppoo...',
        '.....oopcccccccrpppoo...',
        '.....ooppppppppppppoo...',
        '.....oopppppppppppppo...',
        '.....oopccccccccppppo...',
        '......opppppppppppppoo..',
        '......opppppppppppppoo..',
        '......opppppppoooooooo..',
        '......opooooooooo.......',
        '......oooooo............',
        '......o.................',
        '........................',
        '........................',
    ),
    'ticket': (
        '........................',
        '........................',
        '........................',
        '........................',
        '........................',
        '........................',
        '.oooooooooooooooooooooo.',
        '.oggggggggggggggggggggo.',
        '.ogccccccccccccccccccgo.',
        '.ogcppppppppppppppppcgo.',
        '.ogcpppcccpcccpcccppcgo.',
        '.oocpppcccpcccpcccppcoo.',
        'oooopppcccpcccpcccppoooo',
        'oooopppcccpcccpcccppoooo',
        '.oocpppcccpcccpcccppcoo.',
        '.ogcppppppppppppppppcgo.',
        '.ogcppppppppppppppppcgo.',
        '.ogccccccccccccccccccgo.',
        '.oggggggggggggggggggggo.',
        '.oooooooooooooooooooooo.',
        '........................',
        '........................',
        '........................',
        '........................',
        '........................',
        '........................',
    ),
    'paper': (
        '........................',
        '........................',
        '..................o.....',
        '....ooooooooooooooo.....',
        '....oopoooooooooooo.....',
        '....ooppppppppppppo.....',
        '....ooppppppppppppoo....',
        '....ooppppppppppppoo....',
        '.....oppccccccccppoo....',
        '.....opppppppppppppo....',
        '.....opppppppppppppo....',
        '.....oppcccccccccppo....',
        '.....opppppppppppppoo...',
        '.....ooppppppppppppoo...',
        '.....oopccccccccpppoo...',
        '.....ooppppppppppppoo...',
        '.....oopppppppppppppo...',
        '.....oopccccccccppppo...',
        '......opppppppppppppoo..',
        '......opppppppppppppoo..',
        '......opppppppoooooooo..',
        '......opooooooooo.......',
        '......oooooo............',
        '......o.................',
        '........................',
        '........................',
    ),
    'ledger': (
        '........................',
        '........................',
        '........................',
        '........................',
        '..o...................o.',
        '..ooooo..........oooooo.',
        '..oooooooooggoooooooooo.',
        '..oopooooooggooooooopoo.',
        '..oopppooooggooooppppoo.',
        '..ooppppppoggopppppppoo.',
        '..oopccpppoggopppccccoo.',
        '..oopppcccoggocccppppoo.',
        '..ooppppppoggopppppppoo.',
        '..oopccpppoggopppccccoo.',
        '..oopppcccoggocccppppoo.',
        '..oopppppppggopppppppoo.',
        '..oopccppppggopppccccoo.',
        '..oopppcccpggocccppppoo.',
        '..oooooppppggoppppooooo.',
        '..oooooooopggopoooooooo.',
        '.......ooooggooooo......',
        '...........gg...........',
        '........................',
        '........................',
        '........................',
        '........................',
    ),
    'key': (
        '........................',
        '........................',
        '........................',
        '........................',
        '.....ooooo..............',
        '....ooooooo.............',
        '...ooogggooo............',
        '..ooogggggooo...........',
        '..oogggogggoo...........',
        '..ooggoooggoo...........',
        '..oogggogggoo...........',
        '..ooogggggoog...........',
        '...ooogggooogg..........',
        '....ooooooggogg.........',
        '.....ooooo.ggogg...g....',
        '............ggogg.ggg...',
        '.............ggogggggg..',
        '..............ggggggg...',
        '...............ggggg....',
        '................ggggg...',
        '.................ggogg..',
        '..................ggogg.',
        '...................ggo..',
        '....................g...',
        '........................',
        '........................',
    ),
    'bill': (
        '........................',
        '........................',
        '..................o.....',
        '....ooooooooooooooo.....',
        '....oopoooooooooooo.....',
        '....ooppppppppppppo.....',
        '....ooppppppppppppoo....',
        '....ooppppppppppppoo....',
        '.....oppccccccccppoo....',
        '.....opppppppppppppo....',
        '.....opppppppppppppo....',
        '.....oppcccccccccppo....',
        '.....opppppppppppppoo...',
        '.....ooppppppppppppoo...',
        '.....oopccccccccpppoo...',
        '.....ooppppppppppppoo...',
        '.....oopppppppppppppo...',
        '.....oopccccccccppppo...',
        '......oppppppppooooooo..',
        '......opppppppporrrooo..',
        '......opppppppoorrrooo..',
        '......opoooooooooooo....',
        '......oooooo............',
        '......o.................',
        '........................',
        '........................',
    ),
    'bell': (
        '........................',
        '........................',
        '..........cccc..........',
        '..........cccc..........',
        '..........cccc..........',
        '..........cccc..........',
        '........gggggggg........',
        '........ggggggggg.......',
        '.......gggggggggg.......',
        '.......ggggggggggg......',
        '......ggggggggggggg.....',
        '......ggggggggggggg.....',
        '......ggggggggggggg.....',
        '......ggggggggggggg.....',
        '......ggggggggggggg.....',
        '......ggggggggggggg.....',
        '......ggggggggggggg.....',
        '.....ggggggggggggggg....',
        '...ggggggggooogggggggg..',
        '....ooooooocccooooooo...',
        '....ooooooocccooooooo...',
        '..........occco.........',
        '...........ooo..........',
        '........................',
        '........................',
        '........................',
    ),
    'cue': (
        '........................',
        '........................',
        '..................o.....',
        '....ooooooooooooooo.....',
        '....oopoooooooooooo.....',
        '....ooppppppppppppo.....',
        '....oopppppppppprpoo....',
        '....ooppppppppprrroo....',
        '.....oppcccccccrrpoo....',
        '.....opppppppprrrppo....',
        '.....oppppppprrrpppo....',
        '.....oppcccccrrccppo....',
        '.....opppppprrrppppoo...',
        '.....ooppppprrpppppoo...',
        '.....oopcccrrrccpppoo...',
        '.....ooppprrrppppppoo...',
        '.....ooppprrppppppppo...',
        '.....oopcrrrccccppppo...',
        '......oppprpppppppppoo..',
        '......opppppppppppppoo..',
        '......opppppppoooooooo..',
        '......opooooooooo.......',
        '......oooooo............',
        '......o.................',
        '........................',
        '........................',
    ),
    'velvet': (
        '........................',
        '........................',
        '........................',
        '....oo.............oo...',
        '....orooo.......oooro...',
        '...orrrrrooooooorrrrro..',
        '...orrrrrrppppprrrrrro..',
        '..orrrrrrrppppprrrrrrro.',
        '..orrrrrrrppppprrrrrrro.',
        '.orrrrrrrrrppprrrrrrrrro',
        '.oorrrrrrrrppprrrrrrrroo',
        '...oorrrrrrppprrrrrroo..',
        '.....ocrrrrppprrrcoo....',
        '......crrrrrprrrrco.....',
        '......crrrrrprrrrco.....',
        '......crrrrrprrrrco.....',
        '......crrrrrrrrrrco.....',
        '......crrrrrrrrrrco.....',
        '......crrrrrrrrrrcro....',
        '.....ocrrrrrrrrrrcro....',
        '.....ocrrrrrrrrrrcro....',
        '.....ocrrrrrrrrrrcro....',
        '.....orrrrrrrrrrrrro....',
        '.....orrrrrrrrrrrrro....',
        '.....ooooooooooooooo....',
        '........................',
    ),
    'film': (
        '........................',
        '........................',
        '........................',
        '...gggggggggggggggggg...',
        '...goooooooooooooooog...',
        '...goooooooooooooooog...',
        '...gppoobbbbbbbbboppg...',
        '...gppoobbbbbbbbboppg...',
        '...goooobbbgggbbbooog...',
        '...goooobbgggggbbooog...',
        '...gppoobgggggggboppg...',
        '...gppoobgggggggboppg...',
        '...goooobgggggggbooog...',
        '...goooobgggggggbooog...',
        '...gppoobbgggggbboppg...',
        '...gppoobbbgggbbboppg...',
        '...goooobbbbbbbbbooog...',
        '...goooobbbbbbbbbooog...',
        '...gppoobbbbbbbbboppg...',
        '...gppoobbbbbbbbboppg...',
        '...goooooooooooooooog...',
        '...goooooooooooooooog...',
        '...gggggggggggggggggg...',
        '........................',
        '........................',
        '........................',
    ),
    'burned': (
        '........................',
        '.......................r',
        '.....oooo............rrr',
        '.....opppoooooooo...rrrr',
        '.....oppppppppppporrrrrr',
        '.....opppppppppppprrrrrr',
        '.....oppppppppppppprrrrr',
        '.....occcccccccrppprrrr.',
        '.....oppppppppprrrpprrr.',
        '.....opppppppppprrrrrrr.',
        '.....opppppppppprrrrrrr.',
        '.....occcccccccpprrrrrr.',
        '....opppppppppppprrrrrr.',
        '....oppppppppppppprrrrr.',
        '....opcccccccccppprrrrr.',
        '....opppppppppppprrrrrr.',
        '....opppppppppppprrrrrr.',
        '....oppppppppppprrrrrrr.',
        '....oppppppppppprrrrrr..',
        '....opppppppppprrrrrrr..',
        '....ooooooooppprrrrrrr..',
        '............oorrrrrrrr..',
        '..................rrrr..',
        '.....................r..',
        '........................',
        '........................',
    ),
    'seal': (
        '........................',
        '........................',
        '........................',
        '..........ooooo.........',
        '........oorrrrroo.......',
        '......oorrrrrrrrroo.....',
        '.....orrrrgggggrrrro....',
        '.....orrrgggrgggrrro....',
        '....orrrgggrrrrggrrro...',
        '....orrgggrrrrrrrgrro...',
        '...orrggrrrrrrrrrrrrro..',
        '...orrgrrrrrrrrrrggrro..',
        '...orrgggggrrrrggggrro..',
        '...orrggggrrrrrggggrro..',
        '...orrggggrrrrrrgggrro..',
        '....orrggrrrrrrrggrro...',
        '....orrrgrrgggrrrrrro...',
        '.....orrrgggggggrrro....',
        '.....orrrrgggggrrrro....',
        '......oorrrrrrrrroo.....',
        '........oorrrrroo.......',
        '..........ooooo.........',
        '........................',
        '........................',
        '........................',
        '........................',
    ),
    'sketch': (
        '........................',
        '........................',
        '..................o.....',
        '....ooooooooooooooo.....',
        '....oopoooooooooooo.....',
        '....ooppppppppppppo.....',
        '....ooppppppppppppoo....',
        '....ooppppppppppppoo....',
        '.....oppcccccbbbppoo....',
        '.....oppppppbbbbpppo....',
        '.....oppppppbbpbbppo....',
        '.....oppcccbbbcbbppo....',
        '.....oppppbbbppbbppoo...',
        '.....oopppbbppppbbpoo...',
        '.....oopcbbbccccbbpoo...',
        '.....oopbbbpppppbbpoo...',
        '.....oopbbpppppppbbpo...',
        '.....oobbbccccccpbbpo...',
        '......opbpppppppppppoo..',
        '......opppppppppppppoo..',
        '......opppppppoooooooo..',
        '......opooooooooo.......',
        '......oooooo............',
        '......o.................',
        '........................',
        '........................',
    ),
    'glass': (
        '........................',
        '........................',
        '........w..........www..',
        '.......ww......wwwwbbw..',
        '......wbbw..wwwbbbbbw...',
        '......wbbw..wbbbbbbbw...',
        '.....wbbbbw..wbbbbbw....',
        '....wbbbbbw..wbbbbbw....',
        '...wwbbbbbbw..wbbbw.....',
        '.....wwwbbbw..wbbbw.....',
        '........wwwbw..wbw......',
        '...........ww..wbw......',
        '................w.......',
        '.....bbbbbbb....w...bb..',
        '.....bwwwwwb.....bbbwb..',
        '......bwwwb....bbwwwwb..',
        '......bwwwb..bbwwwwwb...',
        '......bwwwb...bwwwwwb...',
        '.......bwb.....bwwwwb...',
        '.......bwb......bwwwb...',
        '.......bwb......bwwwb...',
        '........b........bwb....',
        '........b.........bb....',
        '...................b....',
        '........................',
        '........................',
    ),
    'inventory': (
        '........................',
        '........................',
        '..................o.....',
        '....ooooooooooooooo.....',
        '....oopoooooooooooo.....',
        '....ooppppppppppppo.....',
        '....ooppppppppppppoo....',
        '....ooppppppppppppoo....',
        '.....oppccccccccppoo....',
        '.....opppppppppppppo....',
        '.....opppppppppppppo....',
        '.....oppcccccccccppo....',
        '.....opppppppppppppoo...',
        '.....ooppppppppppppoo...',
        '.....oopccccccccpppoo...',
        '.....ooppppppppppppoo...',
        '.....oopppppppppppppo...',
        '.....oopccccccccppppo...',
        '......oppppppppooooooo..',
        '......opppppppporrrooo..',
        '......opppppppoorrrooo..',
        '......opoooooooooooo....',
        '......oooooo............',
        '......o.................',
        '........................',
        '........................',
    ),
    'note': (
        '........................',
        '........................',
        '..................o.....',
        '....ooooooooooooooo.....',
        '....oopoooooooooooo.....',
        '....ooppppppppppppo.....',
        '....ooppppppppppppoo....',
        '....ooppppppppppppoo....',
        '.....oppccccccccppoo....',
        '.....opppppppppppppo....',
        '.....opppppppppppppo....',
        '.....oppcccccccccppo....',
        '.....opppppppppppppoo...',
        '.....ooppppppppppppoo...',
        '.....oopccccccccpppoo...',
        '.....ooppppppppppppoo...',
        '.....oopppppppppppppo...',
        '.....oopccccccccppppo...',
        '......opppppppppppppoo..',
        '......opppppppppppppoo..',
        '......opppppppoooooooo..',
        '......opooooooooo.......',
        '......oooooo............',
        '......o.................',
        '........................',
        '........................',
    ),
    'tide': (
        '........................',
        '........................',
        '........................',
        '........................',
        '........................',
        '.....b.......b........b.',
        '...bbbbb...bbbbb....bbb.',
        '.bbbwwbbbbbbwwbbbbbbbww.',
        '.bww..wwbbww..wwbbbww...',
        '.w......ww......www.....',
        '........................',
        '.....b.......b........b.',
        '...bbbbb...bbbbb....bbb.',
        '.bbbwwbbbbbbwwbbbbbbbww.',
        '.bww..wwbbww..wwbbbww...',
        '.w......ww......www.....',
        '........................',
        '.....b.......b........b.',
        '...bbbbb...bbbbb....bbb.',
        '.bbbwwbbbbbbwwbbbbbbbww.',
        '.bww..wwbbww..wwbbbww...',
        '.w......ww......www.....',
        '........................',
        '........................',
        '........................',
        '........................',
    ),
    'rope': (
        '........................',
        '........................',
        '........................',
        '...cgc..cgc..cgc..cgc...',
        '...cgc..cgc..cgc..cgc...',
        '..cgc..cgc..cgc..cgc....',
        '..cgc..cgc..cgc..cgc....',
        '.cgc..cgc..cgc..cgc.....',
        '.cgcc.cgcc.cgcc.cgcc....',
        '.ccgc.ccgc.ccgc.ccgc....',
        '..ccgc.ccgc.ccgc.ccgc...',
        '...cgcc.cgcc.cgcc.cgcc..',
        '...ccgc.ccgc.ccgc.ccgc..',
        '....cgc..cgc..cgc..cgc..',
        '...cgc..cgc..cgc..cgc...',
        '...cgc..cgc..cgc..cgc...',
        '..cgc..cgc..cgc..cgc....',
        '..cgc..cgc..cgc..cgc....',
        '.cgc..cgc..cgc..cgc.....',
        '.cgcc.cgcc.cgcc.cgcc....',
        '.ccgccccgccccgccccgccc..',
        '..ccggcccggcccggcccggcc.',
        '....ccg..ccg..ccg..ccg..',
        '.....c....c....c....c...',
        '........................',
        '........................',
    ),
    'cargo': (
        '........................',
        '........................',
        '..................o.....',
        '....ooooooooooooooo.....',
        '....oopoooooooooooo.....',
        '....ooppppppppppppo.....',
        '....ooppppppppppppoo....',
        '....ooppppppppppppoo....',
        '.....oppccccccccppoo....',
        '.....opppppppppppppo....',
        '.....opppppppppppppo....',
        '.....oppcccccccccppo....',
        '.....opppppppppppppoo...',
        '.....ooppppppppppppoo...',
        '.....oopccccccccpppoo...',
        '.....ooppppppppppppoo...',
        '.....oopppppppppppppo...',
        '.....oopccccccccppppo...',
        '......oppppppppooooooo..',
        '......opppppppporrrooo..',
        '......opppppppoorrrooo..',
        '......opoooooooooooo....',
        '......oooooo............',
        '......o.................',
        '........................',
        '........................',
    ),
    'starchart': (
        '........................',
        '........................',
        '..................o.....',
        '....ooooooooooooooo.....',
        '....oopoooooooooooo.....',
        '....ooppppppppppppo.....',
        '....ooppppppppppppoo....',
        '....ooppppppppppppoo....',
        '.....oppcccccbbbppoo....',
        '.....oppppppbbbbpppo....',
        '.....oppppppbbpbbppo....',
        '.....oppcccbbbcbbppo....',
        '.....oppppbbbppbbppoo...',
        '.....oopppbbppppbbpoo...',
        '.....oopcbbbccccbbpoo...',
        '.....oopbbbpppppbbpoo...',
        '.....oopbbpppppppbbpo...',
        '.....oobbbccccccpbbpo...',
        '......opbpppppppppppoo..',
        '......opppppppppppppoo..',
        '......opppppppoooooooo..',
        '......opooooooooo.......',
        '......oooooo............',
        '......o.................',
        '........................',
        '........................',
    ),
    'gear': (
        '........................',
        '...........ooo..........',
        '...........owo..........',
        '...........ooo..........',
        '....oooooo..............',
        '....owooooooooo.........',
        '...oooogooooooooo.......',
        '..oooggooowwwwwooo......',
        '..ooggooowwwwwwwooo.....',
        '..ooggoowwwwwwwwwoo.....',
        '..oogoowwwwooowwwwoo....',
        '.oooooowwwooooowwwoo..oo',
        '.owoooowwwooooowwwoo..ow',
        '.oooooowwwooooowwwoo..oo',
        '.....oowwwwooowwwwoo....',
        '......oowwwwwwwwwoogg...',
        '......ooowwwwwwwoooggg..',
        '.......ooowwwwwoooggg...',
        '........ooooooooogooo...',
        '..........ooooo.ggowo...',
        '.................gooog..',
        '..................ggogg.',
        '...........ooo.....ggo..',
        '...........owo......g...',
        '...........ooo..........',
        '........................',
    ),
    'guestbook': (
        '........................',
        '........................',
        '..................o.....',
        '....ooooooooooooooo.....',
        '....oopoooooooooooo.....',
        '....ooppppppppppppo.....',
        '....ooppppppppppppoo....',
        '....ooppppppppppppoo....',
        '.....oppccccccccppoo....',
        '.....opppppppppppppo....',
        '.....opppppppppppppo....',
        '.....oppcccccccccppo....',
        '.....opppppppppppppoo...',
        '.....ooppppppppppppoo...',
        '.....oopccccccccpppoo...',
        '.....ooppppppppppppoo...',
        '.....oopppppppppppppo...',
        '.....oopccccccccppppo...',
        '......opppppppppppppoo..',
        '......opppppppppppppoo..',
        '......opppppppoooooooo..',
        '......opooooooooo.......',
        '......oooooo............',
        '......o.................',
        '........................',
        '........................',
    ),
    'transcript': (
        '........................',
        '........................',
        '..................o.....',
        '....ooooooooooooooo.....',
        '....oopoooooooooooo.....',
        '....ooppppppppppppo.....',
        '....ooppppppppppppoo....',
        '....ooppppppppppppoo....',
        '.....oppccccccccppoo....',
        '.....opppppppppppppo....',
        '.....opppppppppppppo....',
        '.....oppcccccccccppo....',
        '.....opppppppppppppoo...',
        '.....ooppppppppppppoo...',
        '.....oopccccccccpppoo...',
        '.....ooppppppppppppoo...',
        '.....oopppppppppppppo...',
        '.....oopccccccccppppo...',
        '......opppppppppppppoo..',
        '......oggggggggpppppoo..',
        '......oggggggggooooooo..',
        '......oggggggggoo.......',
        '......oooooo............',
        '......o.................',
        '........................',
        '........................',
    ),
    'stamp': (
        '........................',
        '........................',
        '........................',
        '..........ooooo.........',
        '........oorrrrroo.......',
        '......oorrrrrrrrroo.....',
        '.....orrrrgggggrrrro....',
        '.....orrrgggrgggrrro....',
        '....orrrgggrrrrggrrro...',
        '....orrgggrrrrrrrgrro...',
        '...orrggrrrrrrrrrrrrro..',
        '...orrgrrrrrrrrrrggrro..',
        '...orrgggggrrrrggggrro..',
        '...orrggggrrrrrggggrro..',
        '...orrggggrrrrrrgggrro..',
        '....orrggrrrrrrrggrro...',
        '....orrrgrrgggrrrrrro...',
        '.....orrrgggggggrrro....',
        '.....orrrrgggggrrrro....',
        '......oorrrrrrrrroo.....',
        '........oorrrrroo.......',
        '..........ooooo.........',
        '........................',
        '........................',
        '........................',
        '........................',
    ),
    'passage': (
        '........................',
        '........................',
        '........................',
        '........................',
        '....ooooooooooooooooo...',
        '....occccccccccccccco...',
        '....occccccccccccccco...',
        '....occgggggggggggcco...',
        '....occgooooooooogcco...',
        '....occgooooooooogcco...',
        '....occgooooooooogcco...',
        '....occgooooooooogcco...',
        '....occgooooggooogcco...',
        '....occgoooggggoogcco...',
        '....occgoooggggoogcco...',
        '....occgooooggooogcco...',
        '....occgooooggooogcco...',
        '....occgooooggooogcco...',
        '....occgooooggooogcco...',
        '....occgooooooooogcco...',
        '....occgggggggggggcco...',
        '....occccccccccccccco...',
        '....occccccccccccccco...',
        '....ooooooooooooooooo...',
        '........................',
        '........................',
    ),
    'moths': (
        '........................',
        '........................',
        '........................',
        '.....o...w.....w...o....',
        '....ogo..w.....w..ogo...',
        '...ogggo..w...w..ogggo..',
        '...oggggo.w...w.oggggo..',
        '..oggggggow...woggggggo.',
        '..ogggggggowowogggggggo.',
        '...ogggggggwowgggggggo..',
        '...oggggggggoogggggggo..',
        '...oggggggggoogggggggo..',
        '....ogggggggooggggggo...',
        '....ooooggoooooggoooo...',
        '......oooogooogoooo.....',
        '....oogggggooogggggoo...',
        '....ogggggggooggggggo...',
        '.....oggggggoogggggo....',
        '.....ogggggooogggggo....',
        '......ogggo.ooogggo.....',
        '......oggo..oo.oggo.....',
        '.......oo.......oo......',
        '.......o.........o......',
        '........................',
        '........................',
        '........................',
    ),
    'portrait': (
        '........................',
        '........................',
        '..ooooooooooooooooooooo.',
        '..ogggggggggggggggggggo.',
        '..ogggggggggggggggggggo.',
        '..oggcccccccccccccccggo.',
        '..oggcbbbbbbbbbbbbbcggo.',
        '..oggcbbbbbooobbbbbcggo.',
        '..oggcbbbbofffobbbbcggo.',
        '..oggcbbbofffffobbbcggo.',
        '..oggcbbbofffffobbbcggo.',
        '..oggcbbbofffffobbbcggo.',
        '..oggcbbbbofffobbbbcggo.',
        '..oggcbbbbbooobbbbbcggo.',
        '..oggcbbooooooooobbcggo.',
        '..oggcbborrrrrrrobbcggo.',
        '..oggcborrrrrrrrrobcggo.',
        '..oggcborrrrrrrrrobcggo.',
        '..oggcorrrrrrrrrrrocggo.',
        '..oggcorrrrrrrrrrrocggo.',
        '..oggorrrrrrrrrrrrroggo.',
        '..oggoooooooooooooooggo.',
        '..ogggggggggggggggggggo.',
        '..ogggggggggggggggggggo.',
        '..ooooooooooooooooooooo.',
        '........................',
    ),
    'record': (
        '........................',
        '........................',
        '..................o.....',
        '....ooooooooooooooo.....',
        '....oopoooooooooooo.....',
        '....ooppppppppppppo.....',
        '....ooppppppppppppoo....',
        '....ooppppppppppppoo....',
        '.....oppccccgggcppoo....',
        '.....opppppgooogpppo....',
        '.....opppppgooogpppo....',
        '.....oppcccgooogcppo....',
        '.....opppppgooogpppoo...',
        '.....oopppppgggppppoo...',
        '.....oopccccccccpppoo...',
        '.....ooppppppppppppoo...',
        '.....oopppppppppppppo...',
        '.....oopccccccccppppo...',
        '......opppppppppppppoo..',
        '......opppppppppppppoo..',
        '......opppppppoooooooo..',
        '......opooooooooo.......',
        '......oooooo............',
        '......o.................',
        '........................',
        '........................',
    ),
    'lock': (
        '........................',
        '........................',
        '...........ooo..........',
        '.........ooooooo........',
        '....ooooooooooooooooo...',
        '....occcooowwwoooccco...',
        '....occooowwwwwooocco...',
        '....occooowwwwwooocco...',
        '....occooowwwwwooocco...',
        '....occooowwwwwooocco...',
        '....occooowwwwwooocco...',
        '....occgooowwwooogcco...',
        '....ooooooooooooooooo...',
        '....oogggggggggggggoo...',
        '....oogggggggggggggoo...',
        '....oogggggggggggggoo...',
        '....oogggggggggggggoo...',
        '....oogggggggggggggoo...',
        '....oogggggggggggggoo...',
        '....oogggggggggggggoo...',
        '....oogggggggggggggoo...',
        '....ooooooooooooooooo...',
        '....occccccccccccccco...',
        '....ooooooooooooooooo...',
        '........................',
        '........................',
    ),
    'mask': (
        '........................',
        '........................',
        '........................',
        '...ooooooooooooooooooo..',
        '...opppppppppppppppppo..',
        '...opppppppppppppppppo..',
        '...opppppppppppppppppo..',
        '...opppppppppppppppppo..',
        '...opppooooppppooooppo..',
        '...oppooooooppoooooopo..',
        '...oppooooooppoooooopo..',
        '...oppooooooppoooooopo..',
        '...opppooooppppooooppo..',
        '...opppppppppppppppppo..',
        '...opppppppppppppppppo..',
        '...opppppppppppprppppo..',
        '....opppprppppprrrppo...',
        '....oppprrrppprrrppo....',
        '.....oppprrrrrrppppo....',
        '......opppprrrppppo.....',
        '.......opppprppppo......',
        '.......oppppppppo.......',
        '........opppppppo.......',
        '.........ooooooo........',
        '........................',
        '........................',
    ),
    'lantern': (
        '........................',
        '........................',
        '........................',
        '........................',
        '.........ccccccc........',
        '.........ccccccc........',
        '...........ggg..........',
        '.......ooooggggooo......',
        '.......ogggggggggo......',
        '.......ogggggggggo......',
        '.......ogpppgggpgo......',
        '.......ogppppgppgo......',
        '.......ogpppppppgo......',
        '.......ogpppppppgo......',
        '.......ogpppppppgo......',
        '.......ogpppppppgo......',
        '.......ogpppppppgo......',
        '.......ogpppppppgo......',
        '.......ogpppppppgo......',
        '.......ogggggggggo......',
        '.......ogggggggggo......',
        '.......ooooooooooo......',
        '........................',
        '........................',
        '........................',
        '........................',
    ),
    'eye': (
        '........................',
        '........................',
        '........................',
        '........................',
        '........................',
        '...........ooo..........',
        '.......oooopppoooo......',
        '.....oopppppppppppoo....',
        '....oppppppbbbppppppo...',
        '....opppppbbbbbpppppo...',
        '...opppppbbbbbbbpppppo..',
        '..opppppbbbboobbbpppppo.',
        '..opppppbbboooobbpppppo.',
        '.oppppppbbboooobbppppppo',
        '..opppppbbbboobbbpppppo.',
        '...opppppbbbbbbbpppppo..',
        '...oppppppbbbbbppppppo..',
        '....oppppppbbbppppppo...',
        '.....oopppppppppppoo....',
        '.......oooopppoooo......',
        '...........ooo..........',
        '........................',
        '........................',
        '........................',
        '........................',
        '........................',
    ),
    'watch': (
        '........................',
        '........................',
        '.........ccccc..........',
        '.........ccccc..........',
        '.........ccccco.........',
        '.......oocccccooo.......',
        '......ooooggggoooo......',
        '.....ooogggcggggooo.....',
        '....ooogcgoopcgggooo....',
        '....oogggpoopppgggoo....',
        '....ooggppooppppcgoo....',
        '...oogcpppoopppppggoo...',
        '...ooggpppoopppppggoo...',
        '...oocgpppoopppppcgoo...',
        '...ooggppppooopppggoo...',
        '...ooggpppppppoooggoo...',
        '....oocgppppppppogoo....',
        '....oogggppppppgggoo....',
        '....oooggcppppcggooo....',
        '.....ooogggcggggooo.....',
        '......ooooggggoooo......',
        '.......oooooooooo.......',
        '.........oooooo.........',
        '........................',
        '........................',
        '........................',
    ),
    'crowd': (
        '........................',
        '........................',
        '........................',
        '.....oooo...............',
        '....offffo....oooo......',
        '...offffffo..offffo.....',
        '...offffffo.offffffo....',
        '...offffffo.offffffo....',
        '....offffooooofffffo....',
        '.....oooooffffofffo.....',
        '.ooooooooffffffooo......',
        '.obbbbbboffffffoooooooo.',
        '.obbbbbboffffffobbbbbbo.',
        '.obbbbbbboffffobbbbbbbo.',
        '.obbbbbbbboooobbbbbbbbo.',
        '.obbbbooooooooooooobbbo.',
        '.obbbbobbbbbbbbbbbobbbo.',
        'obbbbbobbbbbbbbbbbobbbo.',
        'obbbbbobbbbbbbbbbbobbbbo',
        'obbbbbobbbbbbbbbbbobbbbo',
        'obbbbbobbbbbbbbbbbobbbbo',
        'obbbbbobbbbbbbbbbbobbbbo',
        'obbbbobbbbbbbbbbbbbobbbo',
        'oooooobbbbbbbbbbbbbobbbo',
        '.....obbbbbbbbbbbbbooooo',
        '.....obbbbbbbbbbbbbo....',
    ),
    'coat': (
        '........................',
        '........................',
        '........................',
        '....oo.............oo...',
        '....orooo.......oooro...',
        '...orrrrrooooooorrrrro..',
        '...orrrrrrppppprrrrrro..',
        '..orrrrrrrppppprrrrrrro.',
        '..orrrrrrrppppprrrrrrro.',
        '.orrrrrrrrrppprrrrrrrrro',
        '.oorrrrrrrrppprrrrrrrroo',
        '...oorrrrrrppprrrrrroo..',
        '.....ocrrrrppprrrcoo....',
        '......crrrrrprrrrco.....',
        '......crrrrrprrrrco.....',
        '......crrrrrprrrrco.....',
        '......crrrrrrrrrrco.....',
        '......crrrrrrrrrrco.....',
        '......crrrrrrrrrrcro....',
        '.....ocrrrrrrrrrrcro....',
        '.....ocrrrrrrrrrrcro....',
        '.....ocrrrrrrrrrrcro....',
        '.....orrrrrrrrrrrrro....',
        '.....orrrrrrrrrrrrro....',
        '.....ooooooooooooooo....',
        '........................',
    ),
    'archive': (
        '........................',
        '........................',
        '........................',
        '........................',
        '..o...................o.',
        '..ooooo..........oooooo.',
        '..oooooooooggoooooooooo.',
        '..oopooooooggooooooopoo.',
        '..oopppooooggooooppppoo.',
        '..ooppppppoggopppppppoo.',
        '..oopccpppoggopppccccoo.',
        '..oopppcccoggocccppppoo.',
        '..ooppppppoggopppppppoo.',
        '..oopccpppoggopppccccoo.',
        '..oopppcccoggocccppppoo.',
        '..oopppppppggopppppppoo.',
        '..oopccppppggopppccccoo.',
        '..oopppcccpggocccppppoo.',
        '..oooooppppggoppppooooo.',
        '..oooooooopggopoooooooo.',
        '.......ooooggooooo......',
        '...........gg...........',
        '........................',
        '........................',
        '........................',
        '........................',
    ),
    'keyring': (
        '........................',
        '........................',
        '........................',
        '........................',
        '.....ooooo..............',
        '....ooooooo.............',
        '...ooogggooo............',
        '..ooogggggooo...........',
        '..oogggogggoo...........',
        '..ooggoooggoo...........',
        '..oogggogggoo...........',
        '..ooogggggoog...........',
        '...ooogggooogg..........',
        '....ooooooggogg.........',
        '.....ooooo.ggogg...g....',
        '............ggogg.ggg...',
        '.............ggogggggg..',
        '..............ggggggg...',
        '...............ggggg....',
        '................ggggg...',
        '.................ggogg..',
        '..................ggogg.',
        '...................ggo..',
        '....................g...',
        '........................',
        '........................',
    ),
    'knife': (
        '........................',
        '........................',
        '....................o...',
        '...................owo..',
        '..................owwwo.',
        '.................owwwo..',
        '.................owwwo..',
        '................owwwo...',
        '...............owwwwo...',
        '..............owwwwo....',
        '.............owwwwo.....',
        '............owwwwwo.....',
        '............owwwwo......',
        '...........owwwwo.......',
        '.........cowwwwwo.......',
        '........cccwwwwo........',
        '.......ccccwwwwo........',
        '......ccccccwwo.........',
        '....cccccccwwo..........',
        '...cccccccwwo...........',
        '..cccccccwwo............',
        '.ccccccwwwo.............',
        '..ccccowwo..............',
        '..ccc..oo...............',
        '...c....................',
        '........................',
    ),
    'moon': (
        '........................',
        '........................',
        '........................',
        '..........oo............',
        '........oogg............',
        '......ooggg.............',
        '.....oggggg.............',
        '.....ogggg..............',
        '....oggggg..............',
        '....oggggg..............',
        '...ogggggg..............',
        '...ogggggg..............',
        '...oggggggg.............',
        '...oggggggg.............',
        '...ogggggggg............',
        '....oggggggg............',
        '....ogggggggg...........',
        '.....oggggggggg.........',
        '.....ogggggggggggggo....',
        '......oogggggggggoo.....',
        '........oogggggoo.......',
        '..........ooooo.........',
        '........................',
        '........................',
        '........................',
        '........................',
    ),
    'rain': (
        '........................',
        '........................',
        '........................',
        '........................',
        '........................',
        '.....b.......b........b.',
        '...bbbbb...bbbbb....bbb.',
        '.bbbwwbbbbbbwwbbbbbbbww.',
        '.bww..wwbbww..wwbbbww...',
        '.w......ww......www.....',
        '........................',
        '.....b.......b........b.',
        '...bbbbb...bbbbb....bbb.',
        '.bbbwwbbbbbbwwbbbbbbbww.',
        '.bww..wwbbww..wwbbbww...',
        '.w......ww......www.....',
        '........................',
        '.....b.......b........b.',
        '...bbbbb...bbbbb....bbb.',
        '.bbbwwbbbbbbwwbbbbbbbww.',
        '.bww..wwbbww..wwbbbww...',
        '.w......ww......www.....',
        '........................',
        '........................',
        '........................',
        '........................',
    ),
    'glove': (
        '........................',
        '........................',
        '........................',
        '............oo..........',
        '..........ooco....o.....',
        '..........occco...ooo...',
        '..........occco..occco..',
        '......o...occco..occco..',
        '....ooco..occco.occcco..',
        '...occco.occcccoocccco..',
        '...occccoocccccoccccco..',
        '...occccoocccccoccccco..',
        '...occcccoccccccccccco..',
        '...occcccocccccccccco...',
        '....occccccccccccccco...',
        '....occccccccccccccco...',
        '....occccccccccccccco...',
        '....occccccccccccccco...',
        '....occccccccccccccco...',
        '.....occcccccccccccco...',
        '.....occccccccccccco....',
        '......occccccccccoo.....',
        '......occccccccco.......',
        '.......ooooooooo........',
        '........................',
        '........................',
    ),
    'theatre': (
        '........................',
        '........................',
        '........................',
        '...ooooooooooooooooooo..',
        '...opppppppppppppppppo..',
        '...opppppppppppppppppo..',
        '...opppppppppppppppppo..',
        '...opppppppppppppppppo..',
        '...opppooooppppooooppo..',
        '...oppooooooppoooooopo..',
        '...oppooooooppoooooopo..',
        '...oppooooooppoooooopo..',
        '...opppooooppppooooppo..',
        '...opppppppppppppppppo..',
        '...opppppppppppppppppo..',
        '...opppppppppppprppppo..',
        '....opppprppppprrrppo...',
        '....oppprrrppprrrppo....',
        '.....oppprrrrrrppppo....',
        '......opppprrrppppo.....',
        '.......opppprppppo......',
        '.......oppppppppo.......',
        '........opppppppo.......',
        '.........ooooooo........',
        '........................',
        '........................',
    ),
    'compass': (
        '........................',
        '........................',
        '........................',
        '.........oooooo.........',
        '.......ooggggggoo.......',
        '......ogggggoggggo......',
        '.....ogggggoogggggo.....',
        '....oggggggobogggggo....',
        '....ogggggobbogggggo....',
        '...oggggggobbbogggggo...',
        '...ogggggobbobogggggo...',
        '...oggggoooogoboogggo...',
        '...oggggooggggooggggo...',
        '...oggggoooogoroogggo...',
        '...ogggggorrorogggggo...',
        '....ogggggorrroggggo....',
        '....ogggggorrogggggo....',
        '.....ogggggoroggggo.....',
        '......oggggooggggo......',
        '.......oogggoggoo.......',
        '.........oooooo.........',
        '........................',
        '........................',
        '........................',
        '........................',
        '........................',
    ),
    'skull': (
        '........................',
        '........................',
        '..........oooooo........',
        '........ooppppppoo......',
        '.......oppppppppppo.....',
        '......oppppppppppppo....',
        '......oppppppppppppo....',
        '.....oppppppppppppppo...',
        '.....opppoopppppooppo...',
        '.....oppoooopppoooopo...',
        '.....oppoooopppoooopo...',
        '.....oppoooopppoooopo...',
        '......oppoopppppoopo....',
        '......oppppppopppppo....',
        '.......oooooooooooo.....',
        '.......oppppooopppo.....',
        '.......opppoooooppo.....',
        '.......oppppppppppo.....',
        '.......opopppopppoo.....',
        '.......opopppopppoo.....',
        '.......opopppopppoo.....',
        '.......opopppopppoo.....',
        '.......oooooooooooo.....',
        '........................',
        '........................',
        '........................',
    ),
    'match': (
        '........................',
        '.......................r',
        '.....oooo............rrr',
        '.....opppoooooooo...rrrr',
        '.....oppppppppppporrrrrr',
        '.....opppppppppppprrrrrr',
        '.....oppppppppppppprrrrr',
        '.....occcccccccrppprrrr.',
        '.....oppppppppprrrpprrr.',
        '.....opppppppppprrrrrrr.',
        '.....opppppppppprrrrrrr.',
        '.....occcccccccpprrrrrr.',
        '....opppppppppppprrrrrr.',
        '....oppppppppppppprrrrr.',
        '....opcccccccccppprrrrr.',
        '....opppppppppppprrrrrr.',
        '....opppppppppppprrrrrr.',
        '....oppppppppppprrrrrrr.',
        '....oppppppppppprrrrrr..',
        '....opppppppppprrrrrrr..',
        '....ooooooooppprrrrrrr..',
        '............oorrrrrrrr..',
        '..................rrrr..',
        '.....................r..',
        '........................',
        '........................',
    ),
    'vial': (
        '........................',
        '........................',
        '.........ooooooo........',
        '.........owwwwwo........',
        '.........owwwwwo........',
        '.........owwwwwo........',
        '.........owwwwwo........',
        '.........owwwwwo........',
        '.........ooooooo........',
        '.........owwwwwo........',
        '........owwwwwwwo.......',
        '........owwwwwwwo.......',
        '........owwwwwwwo.......',
        '.......owwwwwwwwwo......',
        '.......owwwwwwwwwo......',
        '.......lllllllllll......',
        '......olllllllllllo.....',
        '......olllllllllllo.....',
        '......lllllllllllll.....',
        '.....olllllllllllllo....',
        '.....olllllllllllllo....',
        '........................',
        '........................',
        '........................',
        '........................',
        '........................',
    ),
    'book': (
        '........................',
        '........................',
        '........................',
        '........................',
        '..o...................o.',
        '..ooooo..........oooooo.',
        '..oooooooooggoooooooooo.',
        '..oopooooooggooooooopoo.',
        '..oopppooooggooooppppoo.',
        '..ooppppppoggopppppppoo.',
        '..oopccpppoggopppccccoo.',
        '..oopppcccoggocccppppoo.',
        '..ooppppppoggopppppppoo.',
        '..oopccpppoggopppccccoo.',
        '..oopppcccoggocccppppoo.',
        '..oopppppppggopppppppoo.',
        '..oopccppppggopppccccoo.',
        '..oopppcccpggocccppppoo.',
        '..oooooppppggoppppooooo.',
        '..oooooooopggopoooooooo.',
        '.......ooooggooooo......',
        '...........gg...........',
        '........................',
        '........................',
        '........................',
        '........................',
    ),
    'feather': (
        '........................',
        '........................',
        '....................oo..',
        '................oooowo..',
        '............oooowwwwo...',
        '..........oowwwwwwwwo...',
        '.........owwwwwwwwwwo...',
        '.........owwwwwwwwwo....',
        '........owwwwwwwcwwo....',
        '.......owwwwwwwcwwwo....',
        '.......owwwwwwcwwwwo....',
        '......owwwwwwcwwwwo.....',
        '.....owwwwwwwcwwwwo.....',
        '.....owwwwwwcwwwwo......',
        '....owwwwwwcwwwoo.......',
        '....owwwwwcwwwo.........',
        '....owwwwcwwwo..........',
        '....owwwcwwoo...........',
        '....owwcwwo.............',
        '...owwwcwo..............',
        '...owwcoo...............',
        '...owco.................',
        '...oc...................',
        '........................',
        '........................',
        '........................',
    ),
    'message': (
        '........................',
        '........................',
        '..................o.....',
        '....ooooooooooooooo.....',
        '....oopoooooooooooo.....',
        '....ooppprppppppppo.....',
        '....oopprrrpppppppoo....',
        '....ooppprrrppppppoo....',
        '.....oppccrrrcccppro....',
        '.....oppppprrpppprrr....',
        '.....opppppprrpprrro....',
        '.....oppccccrrrcrrpo....',
        '.....oppppppprrrrrpoo...',
        '.....ooppppppprrrppoo...',
        '.....oopcccccccrpppoo...',
        '.....ooppppppppppppoo...',
        '.....oopppppppppppppo...',
        '.....oopccccccccppppo...',
        '......opppppppppppppoo..',
        '......opppppppppppppoo..',
        '......opppppppoooooooo..',
        '......opooooooooo.......',
        '......oooooo............',
        '......o.................',
        '........................',
        '........................',
    ),
    'anchor': (
        '........................',
        '........................',
        '...........ooo..........',
        '..........ogggo.........',
        '.........ogggggo........',
        '.........ogggggo........',
        '.........ogggggo........',
        '..........ogggo.........',
        '...........ooo..........',
        '...........www..........',
        '...........www..........',
        '...........www..........',
        '...........www..........',
        '...........www..........',
        '....wwww...www...wwww...',
        '....wwww...www...wwww...',
        '....wwwww..www..wwwww...',
        '.....wwwww.www.wwwww....',
        '......wwww.www.wwww.....',
        '.......wwwwwwwwwww......',
        '........wwwwwwwww.......',
        '........wwwwwwwww.......',
        '.........wwwwwww........',
        '..........wwwww.........',
        '...........w.w..........',
        '........................',
    ),
    'scales': (
        '........................',
        '........................',
        '........................',
        '............gg..........',
        '............gg..........',
        '............gg..........',
        '............gg..........',
        '............gg..........',
        '...gggwgggggggggggwggg..',
        '...gggwwgggggggggwwggg..',
        '.....w.w....gg...w.w....',
        '.....w..w...gg..w..w....',
        '.....w..w...gg..w..w....',
        '.....w...w..gg.w...w....',
        '....w....w..gg.w....w...',
        '....wwwwwww.ggwwwwwww...',
        '............gg..........',
        '............gg..........',
        '............gg..........',
        '............gg..........',
        '............gg..........',
        '.......ggggggggggg......',
        '.......ggggggggggg......',
        '.......ggggggggggg......',
        '........................',
        '........................',
    ),
    'flower': (
        '........................',
        '........................',
        '...........ooo..........',
        '.........oollloo........',
        '.........olllllo........',
        '........olllllllo.......',
        '......ooolllllllooo.....',
        '....oollloollloollloo...',
        '....olllllolllolllllo...',
        '...olllllllggglllllllo..',
        '...ollllllgggggllllllo..',
        '...olllllggggggglllllo..',
        '....olloogggggggoollo...',
        '....ooollgggggggllooo...',
        '.....ollllgggggllllo....',
        '....ollllllgggllllllo...',
        '....olllllllolllllllo...',
        '....olllllllolllllllo...',
        '.....olllllo.olllllo....',
        '.....oollloo.oollloo....',
        '.......ooo.....ooo......',
        '........................',
        '........................',
        '........................',
        '........................',
        '........................',
    ),
    'pocket': (
        '........................',
        '........................',
        '.........ccccc..........',
        '.........ccccc..........',
        '.........ccccco.........',
        '.......oocccccooo.......',
        '......ooooggggoooo......',
        '.....ooogggcggggooo.....',
        '....ooogcgoopcgggooo....',
        '....oogggpoopppgggoo....',
        '....ooggppooppppcgoo....',
        '...oogcpppoopppppggoo...',
        '...ooggpppoopppppggoo...',
        '...oocgpppoopppppcgoo...',
        '...ooggppppooopppggoo...',
        '...ooggpppppppoooggoo...',
        '....oocgppppppppogoo....',
        '....oogggppppppgggoo....',
        '....oooggcppppcggooo....',
        '.....ooogggcggggooo.....',
        '......ooooggggoooo......',
        '.......oooooooooo.......',
        '.........oooooo.........',
        '........................',
        '........................',
        '........................',
    ),
    'globe': (
        '........................',
        '........................',
        '............g...........',
        '..........oogooo........',
        '........oobbglbboo......',
        '.......obbblgllbbbo.....',
        '......obbbblgllbbbbo....',
        '.....obbbbblgllbbbbbo...',
        '.....obbbbllglllbbbbo...',
        '.....obbbbllglllbbbbo...',
        '....obbbbbllglllbbbbbo..',
        '....obbbbbllglllbbbbbo..',
        '...gggggggggggggggggggg.',
        '....obbbbbllglllbbbbbo..',
        '....obbbbbllglllbbbbbo..',
        '.....obbbbllglllbbbbo...',
        '.....obbbbllglllbbbbo...',
        '.....obbbbblgllbbbbbo...',
        '......obbbblgllbbbbo....',
        '.......obbblgllbbbo.....',
        '........oobbglbboo......',
        '..........oogooo........',
        '............g...........',
        '........................',
        '........................',
        '........................',
    ),
    'footstep': (
        '........................',
        '.......p................',
        '......ppppp.............',
        '.......p.pp.............',
        '......ooopp.............',
        '.....orrco..............',
        '....orrrrco.............',
        '....orrrrco.............',
        '....orrrrco.............',
        '....ocrrcco......p......',
        '....occccco.....ppp.....',
        '.....occco.......p......',
        '......ooo...............',
        '.............ooo........',
        '............occco.......',
        '...........ocrrcco......',
        '...........orrrrco......',
        '...........orrrrco......',
        '...........orrrrco......',
        '...........ocrrcco......',
        '............occco.......',
        '.............ooo........',
        '........................',
        '........................',
        '........................',
        '........................',
    ),
    'portrait_gold': (
        '........................',
        '........................',
        '..ooooooooooooooooooooo.',
        '..ogggggggggggggggggggo.',
        '..ogggggggggggggggggggo.',
        '..oggcccccccccccccccggo.',
        '..oggcbbbbbbbbbbbbbcggo.',
        '..oggcbbbbbooobbbbbcggo.',
        '..oggcbbbbofffobbbbcggo.',
        '..oggcbbbofffffobbbcggo.',
        '..oggcbbbofffffobbbcggo.',
        '..oggcbbbofffffobbbcggo.',
        '..oggcbbbbofffobbbbcggo.',
        '..oggcbbbbbooobbbbbcggo.',
        '..oggcbbooooooooobbcggo.',
        '..oggcbborrrrrrrobbcggo.',
        '..oggcborrrrrrrrrobcggo.',
        '..oggcborrrrrrrrrobcggo.',
        '..oggcorrrrrrrrrrrocggo.',
        '..oggcorrrrrrrrrrrocggo.',
        '..oggorrrrrrrrrrrrroggo.',
        '..oggoooooooooooooooggo.',
        '..ogggggggggggggggggggo.',
        '..ogggggggggggggggggggo.',
        '..ooooooooooooooooooooo.',
        '........................',
    ),
    'candle': (
        '........................',
        '........................',
        '........................',
        '........................',
        '.........ccccccc........',
        '.........ccccccc........',
        '...........ggg..........',
        '.......ooooggggooo......',
        '.......ogggggggggo......',
        '.......ogggggggggo......',
        '.......ogpppgggpgo......',
        '.......ogppppgppgo......',
        '.......ogpppppppgo......',
        '.......ogpppppppgo......',
        '.......ogpppppppgo......',
        '.......ogpppppppgo......',
        '.......ogpppppppgo......',
        '.......ogpppppppgo......',
        '.......ogpppppppgo......',
        '.......ogggggggggo......',
        '.......ogggggggggo......',
        '.......ooooooooooo......',
        '........................',
        '........................',
        '........................',
        '........................',
    ),
    'cobweb': (
        'wwwwwwwwwwwwwwwwwwwwwwww',
        'wwwwwwwww...w......w....',
        'wwwwwwww.wwwwww....w....',
        'wwwwwww.www.w..wwwwww...',
        'wwww.wwww..ww......w.www',
        'wwwww.ww.ww.wwww...w....',
        'wwwwwwwwww.ww...wwww....',
        'www.www.w.w.www....www..',
        'ww.ww.ww.w.ww..ww..w..ww',
        'w.ww.ww.w.w.ww...www....',
        'w.ww.w.w.w.ww.ww...ww...',
        'w.w.w.w.w.w.ww..w..w.ww.',
        'wwwwwwwwwwwww.w..w.w...w',
        'w.w..w.w.w.w...w..ww....',
        'w.w..w.w..w.w...w..ww...',
        'w..w.w..w.w..w...w.w.ww.',
        'w..w..w.w..w..w...ww...w',
        'w..w..w..w..w..w...ww...',
        'w..w..w..w...w..w..w.w..',
        'wwwwwwwwwwwwwwwwwwww..w.',
        'w..w...w..w...w..w.....w',
        'w...w..w...w...w..w.....',
        'w...w...w..w...w...w....',
        'w...w...w...w...w...w...',
        '........................',
        '........................',
    ),
}

ICON_COLORS = {
    "o": (20, 25, 34, 255),
    "p": (221, 202, 159, 255),
    "g": (221, 169, 87, 255),
    "b": (70, 98, 127, 255),
    "r": (150, 65, 77, 255),
    "l": (77, 133, 90, 255),
    "w": (194, 197, 185, 255),
    "c": (117, 78, 55, 255),
    "f": (193, 147, 114, 255),
}


class IconLibrary:
    """Draw actual low-resolution evidence stamps from the embedded atlas."""

    def __init__(self):
        self.cache = {}

    def photo(self, kind, zoom=3, dim=False):
        key = (kind, zoom, dim)
        if key in self.cache:
            return self.cache[key]
        rows = ICON_RASTERS.get(kind, ICON_RASTERS["note"])
        im = Image.new("RGBA", (24, 26), (0, 0, 0, 0))
        px = im.load()
        for yy, row in enumerate(rows):
            for xx, symbol in enumerate(row[:24]):
                if symbol in ICON_COLORS:
                    rgba = ICON_COLORS[symbol]
                    if dim:
                        rgba = (rgba[0] // 2, rgba[1] // 2, rgba[2] // 2, 190)
                    px[xx, yy] = rgba
        im = im.resize((24 * zoom, 26 * zoom), Image.Resampling.NEAREST)
        result = ImageTk.PhotoImage(im)
        self.cache[key] = result
        return result


class AmbientParticles:
    """Low-cost animated motes, sparks, water and floating ash in world space."""

    def __init__(self, chapter):
        self.chapter = chapter
        self.rng = random.Random(9060 + chapter * 41)
        self.dust = []
        self.embers = []
        self.sparks = []
        for i in range(22):
            self.dust.append([
                self.rng.uniform(25, WORLD_W - 25),
                self.rng.uniform(50, WORLD_H - 25),
                self.rng.uniform(.18, .8),
                self.rng.uniform(8, 30),
                self.rng.uniform(-.3, .3),
            ])
        for i in range(8):
            self.embers.append([
                self.rng.uniform(205, 298),
                self.rng.uniform(45, 100),
                self.rng.uniform(1, 3),
                self.rng.uniform(.2, 2.5),
            ])
        for i in range(7):
            self.sparks.append([
                self.rng.uniform(25, WORLD_W - 25),
                self.rng.uniform(50, WORLD_H - 30),
                self.rng.uniform(.4, 1.6),
                self.rng.uniform(0, 6.28),
            ])

    def render(self, canvas, projector, elapsed, focus=False):
        theme = THEMES[self.chapter]["name"]
        # Night dust moves independently from the character animation; it is
        # visible over the floor, not an animated background slideshow.
        if theme in {"manor", "hotel", "archive", "court", "crypt", "observatory"}:
            for i, (wx, wy, sz, drift, bend) in enumerate(self.dust):
                px = wx + math.sin(elapsed * .23 + i) * drift
                py = wy + math.cos(elapsed * .31 + i * 1.8) * 11
                sx, sy = projector(px, py)
                if VIEW_X < sx < VIEW_X + VIEW_W and VIEW_Y < sy < VIEW_Y + VIEW_H:
                    size = max(1, int(sz * PIXEL_SCALE))
                    canvas.create_rectangle(sx, sy, sx + size, sy + size,
                                            fill="#8b7c77" if i % 4 else "#bd9664", outline="", tags="world_render")
        if theme in {"manor", "theater", "archive", "crypt"}:
            for i, (wx, wy, sz, phase) in enumerate(self.embers):
                px = wx + math.sin(elapsed * (1 + phase) + i) * 8
                py = wy - (elapsed * (5 + phase * 2) + i * 13) % 68
                sx, sy = projector(px, py)
                if VIEW_X < sx < VIEW_X + VIEW_W and VIEW_Y < sy < VIEW_Y + VIEW_H:
                    canvas.create_rectangle(sx, sy, sx + sz, sy + sz,
                                            fill="#d8a563" if i % 2 else "#9f624a", outline="", tags="world_render")
        if theme in {"greenhouse", "docks"}:
            for i, (wx, wy, sz, phase) in enumerate(self.sparks):
                px = wx + math.sin(elapsed * .8 + phase) * 7
                py = wy + math.cos(elapsed * .9 + phase) * 9
                sx, sy = projector(px, py)
                if VIEW_X < sx < VIEW_X + VIEW_W and VIEW_Y < sy < VIEW_Y + VIEW_H:
                    radius = sz + .8 * math.sin(elapsed * 2 + i)
                    canvas.create_oval(sx - radius, sy - radius, sx + radius, sy + radius,
                                       fill="#97c5a5" if theme == "greenhouse" else "#5f91a4", outline="",
                                       tags="world_render")


# Room plans share wall/collision geometry with their paintings. Each room is
# built as a separate navigable space, rather than three copies of one backdrop.
# Objects are logical parts of each room and nothing is labelled on the floor.

ROOM_TITLES = [
    ("Grand hall", "Butler's archive", "Under the hearth"),
    ("Station concourse", "Dispatch office", "Old service tunnel"),
    ("Hotel lobby", "Doctor's surgery", "Coal cellar"),
    ("Auditorium", "Backstage office", "Fly gallery"),
    ("Reading room", "Registrar's study", "Forgotten stacks"),
    ("Glass atrium", "Patron's laboratory", "Root cellar"),
    ("Quayside office", "Harbormaster's cabin", "Smuggler's drain"),
    ("Observation hall", "Director's office", "Old instrument vault"),
    ("Court hall", "Magistrate's chambers", "Buried evidence vault"),
    ("Family chapel", "Evelyn's chamber", "Founder's ossuary"),
]

SECRET_FEATURES = [
    ((274, 97), "the fireplace latch", "The fireplace rolls aside; a stair descends through the ash."),
    ((274, 94), "the abandoned freight lift", "The disused freight lift opens on an older service stair."),
    ((90, 145), "the false back of the wardrobe",
     "The wardrobe gives way to a stone passage used by the hotel's staff."),
    ((411, 100), "the seam in the stage curtain", "Behind the velvet, a narrow service stair runs beneath the stage."),
    ((416, 94), "the loose archive shelving", "The shelf pivots and reveals a forgotten stair of stacked stone."),
    ((466, 108), "the maintenance hatch behind the glass", "An iron grate beneath the glass opens over brick steps."),
    ((269, 115), "the concealed dockside hatch",
     "Salt-soaked boards lift from a stone stair to the old drainage route."),
    ((316, 117), "the telescope's service latch", "A brass catch releases a narrow stair under the dome."),
    ((275, 126), "the judge's hidden panel", "The magistrate's bench slides aside, exposing a foundation stair."),
    ((328, 221), "the concealed portrait hinge", "The founder's portrait moves on a hinge; worn stone steps descend."),
]

ROOM_MOODS = [
    ("A live fire keeps the cold from the family's empty chairs.", "The steward's books are too neat to be honest.",
     "Coal dust gives way to older stone. Someone went to great lengths to hide this."),
    ("Steam whistles beneath a vaulted roof.", "There are two manifests, and only one was shown to the authorities.",
     "A disused platform runs beneath the modern station."),
    ("Polished marble conceals the smell of disinfectant.",
     "The doctor's locked records are laid out beside an examination couch.",
     "The hotel's abandoned heating passage hides old patient files."),
    ("Empty seats face a stage still bright with ghost light.", "Cue books and black velvet fill the cramped office.",
     "Above the scenery, the theater keeps its oldest secrets."),
    ("Dust softens every step in the municipal archive.", "The registrar's personal records contradict the city's.",
     "Behind the shelves, a second catalogue has escaped the fire."),
    ("Rain taps a thousand small panes of glass.", "Iris's research sits beneath the patron's lock.",
     "Roots push through the bricks as though the garden is reclaiming them."),
    ("The tide speaks louder than anyone in the harbor office.",
     "Unregistered cargo has been entered in a private ledger.",
     "The drains point toward a quay missing from every chart."),
    ("The dome trembles against the night wind.", "The director's sightline ends at the courthouse tower.",
     "The brass instruments share a secret mechanism."),
    ("Every footstep returns as an accusation.", "Sealed judgments line the private chambers.",
     "The original verdict lies behind the courthouse's foundation."),
    ("The family portraits seem to watch you leave.", "Evelyn arranged the truth like a trap.",
     "The crypt is older than the manor above it."),
]

PRIVATE_PROPS = [
    [("bookcase", 148, 68, 0), ("bookcase", 217, 68, 1), ("desk", 348, 100, 1), ("armchair", 395, 245, 0),
     ("painting", 290, 42, 1), ("clock", 464, 54, 1), ("wardrobe", 468, 295, 0)],
    [("bench", 153, 84, 0), ("desk", 365, 95, 0), ("suitcase", 223, 146, 0), ("clock", 287, 51, 0),
     ("coatstand", 474, 285, 0), ("crate", 389, 261, 0)],
    [("counter", 145, 78, 0), ("desk", 345, 95, 0), ("bell", 337, 94, 0), ("armchair", 399, 271, 0),
     ("wardrobe", 474, 284, 1), ("plant", 192, 294, 1)],
    [("piano", 148, 77, 0), ("desk", 342, 103, 0), ("film", 377, 105, 0), ("velvet", 436, 250, 0),
     ("wardrobe", 470, 280, 0), ("coatstand", 200, 271, 0)],
    [("bookcase", 147, 70, 1), ("bookcase", 213, 70, 2), ("desk", 347, 105, 0), ("clock", 460, 45, 0),
     ("bookcase", 465, 265, 0), ("armchair", 215, 279, 0)],
    [("plant", 167, 77, 2), ("plant", 226, 79, 1), ("desk", 340, 104, 0), ("plant", 450, 272, 0),
     ("bench", 183, 273, 0), ("glass", 389, 112, 1)],
    [("crate", 165, 69, 1), ("crate", 198, 71, 0), ("desk", 343, 96, 0), ("barrel", 457, 279, 0), ("rope", 213, 272, 0),
     ("lantern", 308, 52, 0)],
    [("telescope", 203, 86, 0), ("desk", 346, 104, 0), ("bookshelf", 456, 270, 1), ("scope", 192, 266, 0),
     ("globe", 428, 91, 0), ("clock", 304, 52, 2)],
    [("judgebench", 143, 82, 0), ("desk", 342, 105, 0), ("bookshelf", 450, 272, 0), ("portrait", 280, 47, 0),
     ("bench", 170, 281, 1)],
    [("altar", 164, 76, 0), ("desk", 345, 105, 0), ("portrait", 286, 48, 2), ("statue", 459, 260, 0),
     ("candle", 328, 98, 0), ("coffin", 176, 272, 0)],
]

PASSAGE_PROPS = [
    [("bookcase", 150, 133, 0), ("crate", 382, 262, 0)],
    [("crate", 160, 118, 0), ("barrel", 379, 274, 0)],
    [("barrel", 170, 113, 0), ("crate", 385, 269, 1)],
    [("crate", 167, 128, 1), ("rope", 391, 280, 0)],
    [("bookcase", 148, 128, 1), ("bookcase", 374, 269, 2)],
    [("plant", 165, 132, 2), ("plant", 393, 280, 1)],
    [("crate", 164, 123, 1), ("barrel", 392, 273, 0)],
    [("scope", 160, 135, 0), ("crate", 378, 266, 2)],
    [("bookshelf", 155, 130, 0), ("crate", 384, 274, 1)],
    [("statue", 162, 125, 1), ("coffin", 349, 266, 0)],
]


def room_architecture_walls(room):
    if room == 1:
        # Vestibule -> narrow opening -> records room. The east room has a
        # second southern partition, open around the center for a real route.
        return [(112, 39, 122, 172), (112, 241, 122, 356),
                (160, 238, 270, 247), (326, 238, 517, 247)]
    if room == 2:
        # Stone vault and a narrower stair throat, with a crossing at y=223.
        return [(20, 60, 119, 294), (429, 60, 528, 294),
                (126, 221, 252, 234), (308, 221, 422, 234)]
    return []


def make_room(chapter, room):
    world = make_level(chapter)
    if room == 0:
        world.collisions = build_collisions(world.props)
        return world
    if room == 1:
        world.props = list(PRIVATE_PROPS[chapter])
        world.objects = [Item("private_file", "The private register", 458, 155,
                              "paper", SECRET_REVEALS[chapter])]
        world.witness = Agent(46, 46)
        world.killer = Agent(450, 106, "down", coat=(chapter + 2) % 4,
                             hair=(chapter + 1) % 4, skin=1, hat=chapter % 2 == 0)
        world.civilians = []
        world.hide_positions = [(91, 309), (495, 305)]
        world.blend_zones = []
        world.patrol = [(171, 202), (273, 201), (366, 205), (460, 203)]
        world.start = (56, 209)
    else:
        world.props = list(PASSAGE_PROPS[chapter])
        world.objects = [Item("archive_secret", "A letter within the stonework",
                              348, 163, "note", SECRET_REVEALS[chapter])]
        world.witness = Agent(45, 45)
        world.killer = Agent(45, 45)
        world.civilians = []
        world.hide_positions = []
        world.blend_zones = []
        world.patrol = []
        world.start = (280, 317)
    world.collisions = build_collisions(world.props) + room_architecture_walls(room)
    world.start = find_nearest_open(world, world.start)
    world.killer.x, world.killer.y = find_nearest_open(world, world.killer.feet)
    for obj in world.objects:
        if solid_at(world, obj.x, obj.y, 3):
            obj.x, obj.y = find_nearest_open(world, (obj.x, obj.y), 3)
    world.patrol = [find_nearest_open(world, pt) for pt in world.patrol]
    return world


class RoomPainter(PixelArt):
    def __init__(self, chapter, room, hearth_open=False):
        super().__init__(chapter)
        self.room = room
        self.hearth_open = hearth_open

    def _portal_details(self):
        p = self.palette
        if self.room == 0:
            # A panelled staff door belongs to the eastern wall. Nothing is
            # drawn as an unrelated black hatch in the middle of the floor.
            self.rect((518, 179, 547, 249), (72, 49, 43), p["trim"], 2)
            self.rect((523, 186, 542, 241), (88, 58, 47), (132, 91, 69))
            self.rect((525, 191, 540, 211), (57, 41, 37), (117, 84, 65))
            self.rect((525, 215, 540, 236), (57, 41, 37), (117, 84, 65))
            self.ellipse((525, 214, 529, 218), (211, 166, 88))
            # The real fireplace is in the north wall at x=238..310. Its side
            # latch is just below the marble surround, inside reach.
            if self.chapter == 0:
                self.rect((303, 83, 309, 89), (107, 71, 47), (169, 124, 73))
                self.ellipse((305, 84, 307, 86), (232, 177, 90))
            if self.chapter == 0 and self.hearth_open:
                self.rect((248, 53, 299, 88), (11, 17, 25), (143, 96, 69), 2)
                self.rect((254, 58, 293, 85), (20, 22, 31))
                for i in range(5):
                    self.line((254 + i * 2, 64 + i * 4, 293 - i * 2, 64 + i * 4), (80 + i * 7, 67 + i * 5, 62 + i * 3),
                              2)
                self.rect((238, 45, 244, 79), (111, 76, 61), (144, 98, 69))
            if self.chapter != 0:
                fx, fy = SECRET_FEATURES[self.chapter][0]
                # A small brass hinge is placed on an existing architectural
                # feature, not a freestanding black hatch on the floor.
                self.rect((fx - 3, fy - 3, fx + 3, fy + 3), (102, 69, 48), (166, 123, 69))
                self.ellipse((fx - 1, fy - 1, fx + 1, fy + 1), (233, 179, 94))
                if self.hearth_open:
                    self.rect((fx - 13, fy - 13, fx + 13, fy - 5), (18, 21, 29), (125, 95, 72))
                    for yy in range(fy - 11, fy - 3, 3):
                        self.line((fx - 9, yy, fx + 9, yy), (115, 93, 79))
        elif self.room == 1:
            self.rect((0, 178, 30, 236), (79, 54, 46), (169, 122, 71), 2)
            self.rect((9, 185, 29, 229), (35, 31, 38), (136, 98, 68))
            self.ellipse((18, 207, 22, 211), (222, 185, 108))
            # divider walls have substantial depth; door jambs show where
            # a person passes between vestibule and archive.
            self.rect((112, 39, 122, 172), p["wall"], p["trim"])
            self.rect((112, 241, 122, 356), p["wall"], p["trim"])
            self.rect((112, 169, 122, 175), (153, 119, 88))
            self.rect((112, 236, 122, 241), (153, 119, 88))
            self.rect((160, 238, 270, 247), p["wall"], p["trim"])
            self.rect((326, 238, 517, 247), p["wall"], p["trim"])
            self.rect((266, 238, 275, 247), (141, 106, 74))
            self.rect((321, 238, 330, 247), (141, 106, 74))
            for x in (160, 232, 365, 434):
                self.rect((x, 45, x + 29, 60), (62, 44, 45), (130, 96, 67))
        else:
            # The cellar entry opens onto actual descending steps along the
            # south wall; arch and floor match the narrow stairwell.
            self.rect((245, 340, 314, 373), (38, 35, 43), (122, 102, 84), 2)
            self.rect((254, 343, 305, 366), (19, 22, 31), (91, 79, 75))
            for y in range(345, 363, 5):
                self.line((259, y, 301, y), (122, 109, 94), 2)
            self.ellipse((242, 337, 259, 355), (88, 77, 66), (140, 121, 94))
            self.ellipse((301, 337, 318, 355), (88, 77, 66), (140, 121, 94))

    def render_room(self, level):
        if self.room == 0:
            # Hand-painted top-down hall, retaining its chapter-unique props.
            self.floor()
            self.boundary()
            for prop in level.props:
                if prop[0] in {"rug", "runner", "glassfloor", "stonefloor", "dockfloor", "water"}:
                    self.prop(prop)
            for prop in level.props:
                if prop[0] not in {"rug", "runner", "glassfloor", "stonefloor", "dockfloor", "water"}:
                    self.prop(prop)
            self._portal_details()
        else:
            self.floor()
            self.boundary()
            if self.room == 1:
                self._private_architecture()
            else:
                self._underground_architecture()
            for prop in level.props:
                self.prop(prop)
            self._portal_details()
        for idx, obj in enumerate(level.objects):
            if obj.id not in {"uniform"}:
                self.small_object(obj.kind, obj.x, obj.y, idx)
        self.lighting()
        self.vignette()
        return self.image

    def _private_architecture(self):
        p = self.palette
        # A narrow entry vestibule and two connected office spaces. The
        # materials vary by location; wall geometry matches collision shapes.
        self.rect((22, 40, 111, 356), shade(p["floor"], .79))
        for y in range(48, 350, 24):
            self.line((24, y, 108, y), shade(p["floor_line"], .84))
        self.small_rug(144, 182, 182, 34, color=shade(p["rug"], .87))
        self.rect((347, 65, 504, 221), shade(p["floor"], 1.08), shade(p["trim"], .65))
        for x in range(359, 502, 23):
            for y in range(75, 219, 23):
                self.rect((x, y, x + 21, y + 21),
                          p["floor2"] if ((x + y) // 23) % 2 else shade(p["floor"], 1.12),
                          shade(p["floor_line"], .8))
        # Lamps and discreet files read as a work area, not a public hall.
        for x in (174, 283, 471):
            self.rect((x, 43, x + 23, 59), (46, 51, 63), p["trim"])
            self.rect((x + 6, 47, x + 17, 55), p["warm"])
            self.lights.append((x + 12, 52, 36, p["warm"]))
        self.small_rug(372, 259, 102, 50, color=shade(p["rug"], .71))
        if self.chapter in {1, 6}:
            for x in (198, 252, 308):
                self.line((x, 265, x, 347), shade(p["trim"], .85), 2)
        elif self.chapter in {3, 8}:
            self.rect((240, 42, 302, 61), (113, 54, 62), (163, 99, 69))
        elif self.chapter == 5:
            for x in (175, 215, 295):
                self.plant(x, 274, 2)
        elif self.chapter == 7:
            self.ellipse((224, 260, 306, 336), None, (104, 128, 147), 2)

    def _underground_architecture(self):
        slate = (33, 37, 45) if self.chapter != 5 else (31, 49, 42)
        mortar = (74, 71, 76) if self.chapter != 5 else (76, 87, 77)
        self.rect((20, 39, 527, 357), slate)
        # Hand-laid masonry: alternating brick joints, different from the
        # manor parquet or office tiles, and fully pixel-aligned.
        for y in range(43, 357, 14):
            for x in range(24 + ((y // 14) % 2) * 20, 526, 41):
                self.rect((x, y, min(x + 39, 526), min(y + 12, 356)),
                          (44 + ((x + y) % 4) * 2, 48 + ((x // 17) % 4) * 2, 57 + ((y // 17) % 3) * 2), mortar)
        # Corridor is cut between two heavy buttress walls.
        self.rect((124, 79, 425, 355), (50, 48, 51), mortar)
        for yy in range(85, 349, 25):
            for xx in range(129 + (12 if yy // 25 % 2 else 0), 422, 36):
                self.rect((xx, yy, xx + 34, yy + 23), (55, 52, 54), (82, 74, 70))
        self.rect((20, 60, 119, 294), (26, 29, 36), (93, 79, 73), 2)
        self.rect((429, 60, 528, 294), (26, 29, 36), (93, 79, 73), 2)
        for y in range(69, 284, 29):
            self.line((23, y, 116, y), (70, 64, 65))
            self.line((432, y, 525, y), (70, 64, 65))
        self.rect((126, 221, 252, 234), (35, 38, 45), (110, 91, 77))
        self.rect((308, 221, 422, 234), (35, 38, 45), (110, 91, 77))
        self.small_rug(256, 86, 47, 121, color=(60, 53, 62))
        # The stairs descend away from camera and end at an actual landing.
        self.rect((247, 95, 314, 188), (29, 32, 40), (105, 91, 80), 2)
        for i in range(8):
            sy = 102 + i * 10
            self.rect((251 + i // 3, sy, 310 - i // 3, sy + 6),
                      (62 + i * 3, 59 + i * 3, 62 + i * 2), (96, 83, 75))
        for x, y in ((135, 101), (408, 101), (155, 297), (391, 297)):
            self.rect((x - 4, y - 7, x + 4, y + 4), (121, 85, 58), (45, 37, 38))
            self.ellipse((x - 2, y - 9, x + 2, y - 4), (233, 178, 94))
            self.lights.append((x, y, 40, (225, 163, 91)))


class SpriteFactory:
    """An in-memory sprite sheet generator with cached PhotoImage frames."""

    def __init__(self):
        self.cache: dict[tuple, ImageTk.PhotoImage] = {}
        self.avatar_previews: dict[tuple, ImageTk.PhotoImage] = {}
        self.shadow: Optional[ImageTk.PhotoImage] = None

    def build(self, coat, hair, skin, facing, walk, hat, accessory=0, ghost=False):
        im = Image.new("RGBA", (24, 34), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        sk = SKIN_SWATCHES[skin % len(SKIN_SWATCHES)]
        ha = HAIR_SWATCHES[hair % len(HAIR_SWATCHES)]
        co = COAT_SWATCHES[coat % len(COAT_SWATCHES)]
        edge = (22, 26, 35)
        seam = shade(co, .7)
        white = (224, 215, 193)
        pin = ACCESSORY_COLORS[accessory % 4]
        step = (0, 1, 0, -1, 0, 1)[walk % 6]
        swing = (0, 2, 3, 0, -2, -3)[walk % 6]
        bob = 1 if walk in (1, 4) else 0
        # Soft ground shadow anchors characters to the tilemap.
        d.ellipse((4, 29, 20, 33), fill=(6, 12, 21, 80))
        d.rectangle((9, 23 + max(0, step), 11, 30), fill=edge)
        d.rectangle((13, 23 + max(0, -step), 15, 30), fill=edge)
        d.rectangle((8, 27 + max(0, step), 12, 30), fill=(23, 21, 27))
        d.rectangle((12, 27 + max(0, -step), 16, 30), fill=(23, 21, 27))

        if facing == "down":
            d.polygon([(7, 14 + bob), (17, 14 + bob), (19, 27), (5, 27)], fill=co, outline=edge)
            d.polygon([(6, 15), (9, 17), (7 + swing // 2, 24), (4, 24)], fill=co, outline=edge)
            d.polygon([(18, 15), (15, 17), (17 - swing // 2, 24), (20, 24)], fill=co, outline=edge)
            d.polygon([(10, 15), (14, 15), (13, 23), (11, 23)], fill=white)
            d.rectangle((11, 17, 13, 24), fill=(113, 43, 51))
            d.rectangle((6, 20, 8, 23), fill=seam)
            d.rectangle((16, 20, 18, 23), fill=seam)
            d.rectangle((16, 18, 17, 19), fill=pin)
            d.rectangle((8, 8 + bob, 16, 16 + bob), fill=sk, outline=edge)
            d.rectangle((7, 6 + bob, 17, 11 + bob), fill=ha)
            d.rectangle((7, 10 + bob, 9, 13 + bob), fill=ha)
            d.rectangle((15, 10 + bob, 17, 13 + bob), fill=ha)
            d.point((10, 12 + bob), fill=(31, 26, 31))
            d.point((14, 12 + bob), fill=(31, 26, 31))
            d.line((11, 15 + bob, 13, 15 + bob), fill=shade(sk, .70))
        elif facing == "up":
            d.polygon([(7, 14 + bob), (17, 14 + bob), (19, 27), (5, 27)], fill=co, outline=edge)
            d.polygon([(6, 15), (9, 17), (7 + swing // 2, 24), (4, 24)], fill=co, outline=edge)
            d.polygon([(18, 15), (15, 17), (17 - swing // 2, 24), (20, 24)], fill=co, outline=edge)
            d.line((12, 16, 12, 27), fill=seam)
            d.rectangle((7, 7 + bob, 17, 15 + bob), fill=ha, outline=edge)
            d.rectangle((8, 6 + bob, 16, 10 + bob), fill=ha)
            d.rectangle((9, 13 + bob, 15, 16 + bob), fill=shade(ha, .80))
            d.rectangle((5, 18, 7, 23), fill=seam)
            d.rectangle((17, 18, 19, 23), fill=seam)
        else:
            flip = facing == "left"
            d.polygon([(8, 14 + bob), (16, 14 + bob), (17, 27), (7, 27)], fill=co, outline=edge)
            d.polygon([(7, 17), (10, 17), (8 + swing // 2, 23), (5, 23)], fill=co, outline=edge)
            d.polygon([(15, 17), (18, 17), (19, 23), (15 - swing // 2, 23)], fill=co, outline=edge)
            d.rectangle((11, 15, 12, 24), fill=white)
            d.rectangle((9, 8 + bob, 16, 15 + bob), fill=sk, outline=edge)
            d.rectangle((8, 6 + bob, 16, 10 + bob), fill=ha)
            d.rectangle((8, 9 + bob, 10, 14 + bob), fill=ha)
            d.point((15, 12 + bob), fill=(24, 22, 27))
            d.polygon([(16, 12 + bob), (19, 13 + bob), (16, 14 + bob)], fill=sk)
            if flip:
                im = im.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                d = ImageDraw.Draw(im)
        if hat:
            # Everyone else wears a plain fedora; guards wear a very distinct
            # navy peaked cap, golden stripe and visible brass shoulder patch.
            if accessory == 3:
                d.rectangle((5, 5 + bob, 19, 8 + bob), fill=(18, 39, 74), outline=(10, 18, 35))
                d.rectangle((8, 2 + bob, 16, 7 + bob), fill=(22, 47, 83), outline=(10, 18, 35))
                d.line((7, 7 + bob, 17, 7 + bob), fill=(238, 192, 99), width=2)
                d.rectangle((16, 17, 19, 20), fill=(230, 185, 81))
                d.rectangle((17, 18, 18, 19), fill=(65, 78, 104))
            else:
                d.rectangle((6, 6 + bob, 18, 8 + bob), fill=(28, 30, 38), outline=(13, 18, 27))
                d.rectangle((9, 2 + bob, 15, 7 + bob), fill=(38, 37, 46), outline=(17, 19, 27))
                d.line((9, 6 + bob, 15, 6 + bob), fill=(145, 100, 73))
        if ghost:
            a = im.getchannel("A")
            a = a.point(lambda value: value // 2)
            im.putalpha(a)
        return im

    def photo(self, coat, hair, skin, facing, walk, hat=False, accessory=0, zoom=3, ghost=False):
        key = (coat, hair, skin, facing, walk, hat, accessory, zoom, ghost)
        if key not in self.cache:
            base = self.build(coat, hair, skin, facing, walk, hat, accessory, ghost=ghost)
            base = base.resize((24 * zoom, 34 * zoom), Image.Resampling.NEAREST)
            self.cache[key] = ImageTk.PhotoImage(base)
        return self.cache[key]


# -----------------------------------------------------------------------------
# MAIN MENU ILLUSTRATION
# A moody manor scene independent from the top-down world view: the title screen
# echoes the reference's silhouettes, blue-black stone, glowing windows, moon,
# rain, trees, and paved reflections.
# -----------------------------------------------------------------------------

class TitleIllustration:
    def __init__(self):
        self.rng = random.Random(112233)

    def render(self):
        w, h = 584, 388
        im = Image.new("RGB", (w, h), (6, 17, 35))
        d = ImageDraw.Draw(im)
        for y in range(h):
            blue = clamp(26 + int(13 * math.sin(y / 106)) - y // 38, 7, 44)
            d.line((0, y, w, y), fill=(7, 15 + blue // 5, blue + 16))
        for i in range(110):
            x = self.rng.randrange(w)
            y = self.rng.randrange(226)
            d.rectangle((x, y, x + 1, y + 1), fill=self.rng.choice([(53, 74, 123), (79, 93, 149), (116, 123, 173)]))
        d.ellipse((414, 31, 476, 93), fill=(238, 206, 132), outline=(250, 224, 161), width=2)
        for px, py, r in [(435, 48, 5), (457, 60, 7), (436, 74, 4)]:
            d.ellipse((px - r, py - r, px + r, py + r), fill=(218, 188, 120))
        for i in range(9):
            xx = i * 70 - 22
            yy = 142 + (i % 3) * 18
            d.polygon([(xx - 18, yy + 31), (xx + 17, yy - 25), (xx + 56, yy + 31)], fill=(12, 26, 51))
            d.rectangle((xx - 18, yy + 30, xx + 56, 259), fill=(14, 29, 52))

        # Each block is a complete facade at its own depth. Roofs and wall
        # details are painted BEFORE the windows. Owner masks identify the
        # unobscured rectangle fragments: no cropped / hanging windows.
        buildings = [
            (50, 143, 158, 301, 0),
            (145, 112, 302, 312, 1),
            (278, 124, 430, 310, 0),
            (407, 150, 531, 304, 0),
            (230, 78, 329, 306, 2),
        ]
        owner = Image.new("I", (w, h), -1)
        od = ImageDraw.Draw(owner)
        for index, (x1, y1, x2, y2, kind) in enumerate(buildings):
            roof = y1 - (27 if kind != 2 else 42)
            stone = (20 + kind * 3, 36 + kind * 4, 65 + kind * 3)
            d.rectangle((x1, y1, x2, y2), fill=stone, outline=(40, 61, 89), width=1)
            od.rectangle((x1, y1, x2, y2), fill=index)
            d.polygon([(x1 - 13, y1 + 3), ((x1 + x2) // 2, roof), (x2 + 13, y1 + 3)], fill=(18, 32, 61),
                      outline=(45, 63, 101))
            od.polygon([(x1 - 13, y1 + 3), ((x1 + x2) // 2, roof), (x2 + 13, y1 + 3)], fill=-1)
            # Restrained masonry marks, none drawn across a window later.
            for yy in range(y1 + 15, y2 - 10, 20):
                for xx in range(x1 + 8, x2 - 8, 32):
                    if self.rng.random() < .58:
                        d.line((xx, yy, xx + 10, yy), fill=(35, 52, 77))
        owners = owner.load()
        for index, (x1, y1, x2, y2, kind) in enumerate(buildings):
            pane_w, pane_h = 21, 34
            for xx in range(x1 + 11, x2 - pane_w - 9, 37):
                for yy in range(y1 + 25, y2 - pane_h - 13, 52):
                    # The full frame and a two-pixel safety zone must be
                    # owned by the same facade at this exact depth.
                    pts = [
                        (xx - 3, yy - 3), (xx + pane_w + 3, yy - 3),
                        (xx - 3, yy + pane_h + 3), (xx + pane_w + 3, yy + pane_h + 3),
                        (xx + pane_w // 2, yy + pane_h // 2),
                    ]
                    if any(not (0 <= ax < w and 0 <= ay < h) or owners[ax, ay] != index for ax, ay in pts):
                        continue
                    lit = self.rng.random() < .86
                    frame = (61, 64, 73)
                    glow = (231, 173, 77) if lit else (10, 20, 41)
                    d.rectangle((xx, yy, xx + pane_w, yy + pane_h), fill=glow, outline=frame, width=2)
                    d.line((xx + 10, yy + 2, xx + 10, yy + pane_h - 2), fill=(81, 64, 60), width=2)
                    d.line((xx + 1, yy + 17, xx + pane_w - 1, yy + 17), fill=(81, 64, 60), width=2)
                    if lit:
                        d.rectangle((xx + 4, yy + 4, xx + 7, yy + 8), fill=(252, 213, 126))
        # Door and garden steps are in the foreground of the frontage.
        d.rectangle((254, 251, 300, 322), fill=(80, 51, 43), outline=(145, 99, 65), width=2)
        d.rectangle((263, 263, 291, 313), fill=(191, 131, 76), outline=(224, 164, 100), width=2)
        d.ellipse((287, 285, 291, 289), fill=(247, 216, 148))
        for yy in range(316, 331, 5):
            d.rectangle((244 - (yy - 316), yy, 309 + (yy - 316), yy + 2), fill=(62, 68, 83))
        d.polygon([(245, 322), (315, 322), (416, 387), (136, 387)], fill=(23, 38, 58))
        for yy in range(328, 386, 9):
            offset = self.rng.randrange(-21, 22)
            d.line((277 - (yy - 320) * 2 + offset, yy, 279 + (yy - 320) * 2 + offset, yy), fill=(43, 67, 87))
            if self.rng.random() < .62:
                d.line((269 + offset, yy + 2, 289 + offset, yy + 2), fill=(147, 117, 74))
        for tx, ty, sc in [(26, 345, 1.3), (559, 344, 1.2), (75, 355, .8), (508, 354, .8)]:
            d.line((tx, ty, tx - 5, ty - 113 * sc), fill=(12, 24, 41), width=9)
            for k in range(5):
                ry = ty - 30 - k * 20 * sc
                d.line((tx, ry, tx - 30 + 8 * k, ry - 25), fill=(15, 28, 47), width=6)
                d.line((tx, ry, tx + 34 - 6 * k, ry - 23), fill=(15, 28, 47), width=6)
                for j in range(6):
                    px = tx + self.rng.randint(-36, 36)
                    py = ry + self.rng.randint(-24, 9)
                    d.rectangle((px, py, px + 9, py + 7),
                                fill=self.rng.choice([(12, 29, 45), (15, 37, 54), (18, 43, 60)]))
        for _ in range(42):
            rx, ry = self.rng.randrange(180, 396), self.rng.randrange(322, 387)
            if abs(rx - 278) < (ry - 310) * 1.7:
                d.line((rx, ry, rx + self.rng.randrange(3, 23), ry),
                       fill=self.rng.choice([(98, 90, 76), (141, 111, 71), (64, 85, 105)]))
        return im


# Woody's PPR

manor_hints = [
    "Everyone keeps quoting the exact same time. Take a closer look at the clock in the study.",
    "Someone came in from the storm tonight. Check the floor for anything they left behind.",
    "Not every paper in this house burned completely. What was someone so desperate to destroy?",
]


def get_hint(found_clues):
    for i in range(len(manor_hints)):
        if i not in found_clues:
            return manor_hints[i]
    return "You have all the evidence. Time to make your deduction."


class BlackwellGame:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Blackwell: Into the Shadows")
        root.configure(bg=C["black"])
        # Start at the game's full design size and let macOS/PyCharm maximize it.
        root.geometry(f"{SW}x{SH}")
        root.minsize(900, 600)
        root.resizable(True, True)
        self.canvas = tk.Canvas(root, width=SW, height=SH, bg=C["black"], highlightthickness=0)
        self.canvas.pack()
        self.font_small = "Courier New"
        self.font_title = "Georgia"
        self.buttons: list[tuple[tuple[float, float, float, float], Callable]] = []
        self.mouse = (-100, -100)
        self.held: set[str] = set()
        self.release_jobs: dict[str, str] = {}
        self.click_destination: Any = None
        self.click_path = []
        self.screen = "menu"
        self.overlay = None
        self.screen_return = None
        self.avatar = {"name": "Jack", "skin": 0, "hair": 0, "coat": 1, "hat": 0, "accessory": 0}
        self.unlocked = 0
        self.chapter = 0
        self.finished = False
        self.progress: dict[str, dict] = {}
        self.seen: set[int] = set()
        self.notes: set[int] = set()
        self.solved: set[int] = set()
        self.witness_spoken = False
        self.wrong_attempts = 0
        self.deduction_mistakes: set[int] = set()
        self.spotted_count = 0
        self.hush = 0.0
        self.world = make_level(0)
        self.room_index = 0
        self.secret_unlocked = False
        self.room_positions = {}
        self.room_art_cache = OrderedDict()
        self.transition_to = None
        self.transition_from = 0
        self.transition_time = 0.0
        self.transition_started_at = 0.0
        self.transition_switched = False
        self.transition_duration = 1.7
        self.player = Agent(*self.world.start)
        self.watchmen: list[PatrolGuard] = []
        self.exposure = 0.0
        self.peak_exposure = 0.0
        self.hidden = False
        self.blending = False
        self.crouched = False
        self.running = False
        self.focus = False
        self.disguise = None  # None / "staff" / "guest"
        self.cover_blown = False
        self.scrutiny = 0.0
        self.coins = 3
        self.decoy = None
        self.decoy_expire = 0.0
        self.infiltration_uncovered = False
        self.restricted_warning_at = -9.0
        self.cam_x = 0.0
        self.cam_y = 0.0
        self.world_raw = None
        self.world_photo = None
        self.world_pil = None
        self.scene_lights = []
        self.dynamic_lights = []
        self.title_photo = None
        self.title_pil = None
        self.thumbnails: dict[int, ImageTk.PhotoImage] = {}
        self.sprite_factory = SpriteFactory()
        self.icons = IconLibrary()
        self.ambient = AmbientParticles(0)
        self.flash_timer = 0.0
        self.toast_text = ""
        self.toast_timer = 0.0
        self.alert_caption = ""
        self.alert_caption_timer = 0.0
        self.time_alive = 0.0
        self.tick_count = 0
        self._last_chrome_signature = None
        self._chrome_updated_at = 0.0
        self._world_nodes = {}
        self._world_particles = {}
        self._scene_emitters = {}
        self._world_alerts = {}
        self._world_sparkle = []
        self._world_decoy = []
        self._focus_was_active = False
        self.last_tick = time.perf_counter()
        self.cutscene_step = 0
        self.dialogue_step = 0
        self.confront_step = 0
        self.deduction_chosen = None
        self.end_grade = ""
        # Developer tools are opened with on-screen buttons (no function keys).
        self.debug_return_screen = "menu"
        self.debug_return_overlay = None
        self.debug_target_chapter = self.chapter
        self.debug_score = 0
        self.debug_score_override = False
        self.ui_scroll = 0
        self.name_entry: Optional[tk.Entry] = None
        self.name_entry_open = False
        self.particles = [(random.Random(i * 121 + 5).randrange(584), random.Random(i * 312 + 7).randrange(388)) for i
                          in range(65)]
        self.load()
        self.make_title()
        self.prepare_chapter(self.chapter, reset=False)
        self.screen = "menu"
        root.bind("<KeyPress>", self.key_down)
        root.bind("<KeyRelease>", self.key_up)
        root.bind("<Button-1>", self.click)
        root.bind("<Motion>", self.motion)
        root.bind("<MouseWheel>", self.wheel)
        root.bind("<FocusOut>", lambda ev: self.clear_held())
        root.protocol("WM_DELETE_WINDOW", self.quit)
        self.redraw()
        self.root.after(int(STEP_INTERVAL * 1000), self.update)

    # -------- data and files --------
    def save(self):
        self.cache_progress()
        data = {
            "version": VERSION,
            "avatar": self.avatar,
            "unlocked": self.unlocked,
            "chapter": self.chapter,
            "finished": self.finished,
            "progress": self.progress,
        }
        # Write beside the real save and swap it in, so a crash mid-write
        # cannot leave a truncated file behind.
        tmp = SAVE_FILE.with_name(SAVE_FILE.name + ".tmp")
        try:
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            os.replace(tmp, SAVE_FILE)
        except OSError as exc:
            traceback.print_exception(exc)
            self.toast("Your progress could not be saved to disk.")

    def cache_progress(self):
        if self.screen not in {"game", "menu", "profile", "select", "help"}:
            return
        self.progress[str(self.chapter)] = {
            "seen": sorted(self.seen),
            "solved": sorted(self.solved),
            "notes": sorted(self.notes),
            "witness_spoken": self.witness_spoken,
            "wrong_attempts": self.wrong_attempts,
            "deduction_mistakes": sorted(self.deduction_mistakes),
            "spotted_count": self.spotted_count,
            "disguise": self.disguise,
            "cover_blown": self.cover_blown,
            "coins": self.coins,
            "infiltration_uncovered": self.infiltration_uncovered,
            "player": [int(self.player.x), int(self.player.y)],
            "room": self.room_index,
            "peak_exposure": round(self.peak_exposure, 1),
            "secret_unlocked": self.secret_unlocked,
            "room_positions": {str(k): list(v) for k, v in self.room_positions.items()},
        }

    def load(self):
        data = None
        for path in (SAVE_FILE, OLD_SAVE_FILE):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                break
            except (OSError, ValueError, TypeError):
                continue
        if not isinstance(data, dict):
            return
        old_avatar = data.get("avatar", {})
        if isinstance(old_avatar, dict):
            self.avatar.update({key: value for key, value in old_avatar.items() if key in self.avatar})
        for key, size in (("skin", 4), ("hair", 4), ("coat", 4), ("hat", 2), ("accessory", 4)):
            self.avatar[key] = as_int(self.avatar[key]) % size
        self.avatar["name"] = str(self.avatar["name"])[:22] or "Detective"
        self.unlocked = clamp(as_int(data.get("unlocked", 0)), 0, 9)
        self.chapter = clamp(as_int(data.get("chapter", 0)), 0, self.unlocked)
        self.finished = bool(data.get("finished", False))
        self.progress = data.get("progress", {}) if isinstance(data.get("progress", {}), dict) else {}
        if not SAVE_FILE.exists():
            # Smoothly migrate from the previous prototype save format.
            self.progress = {}

    def prepare_chapter(self, number, reset=False):
        self.chapter = int(clamp(number, 0, 9))
        self.world = make_room(self.chapter, 0)
        self.room_art_cache = OrderedDict()
        self.nav = NavigationGrid(self.world)
        self._scene_ready = False
        self._background_id = None
        self.click_path = []
        self.ambient = AmbientParticles(self.chapter)
        state = {} if reset else self.progress.get(str(self.chapter), {})
        if not isinstance(state, dict):
            state = {}

        def saved_ids(key, limit):
            values = state.get(key, [])
            if not isinstance(values, list):
                return set()
            return {n for n in (as_int(v, -1) for v in values) if 0 <= n < limit}

        self.seen = saved_ids("seen", 3)
        # 0-2 are the margin notes; 3 and 4 are the two secret documents.
        self.notes = saved_ids("notes", 5)
        self.solved = saved_ids("solved", 3)
        self.witness_spoken = bool(state.get("witness_spoken", False))
        self.wrong_attempts = as_int(state.get("wrong_attempts", 0))
        self.deduction_mistakes = saved_ids("deduction_mistakes", 3)
        self.spotted_count = as_int(state.get("spotted_count", 0))
        self.disguise = state.get("disguise") if state.get("disguise") in {"staff", "guest"} else None
        self.cover_blown = bool(state.get("cover_blown", False))
        self.scrutiny = 0.0
        self.coins = clamp(as_int(state.get("coins", 3), 3), 0, 5)
        self.decoy = None
        self.decoy_expire = 0.0
        self.infiltration_uncovered = bool(state.get("infiltration_uncovered", False))
        self.secret_unlocked = bool(state.get("secret_unlocked", False))
        self.room_index = 0
        saved_positions = state.get("room_positions", {})
        if not isinstance(saved_positions, dict):
            saved_positions = {}
        self.room_positions = {int(k): pt for k, v in saved_positions.items()
                               if k in {"0", "1", "2"} and (pt := as_point(v)) is not None}
        target_room = as_int(state.get("room", 0)) if not reset else 0
        if target_room not in (0, 1, 2):
            target_room = 0
        # "player" is where the detective stood in the room they saved in;
        # switch_room() below restores it from room_positions.
        saved_player = as_point(state.get("player"))
        if saved_player is not None:
            self.room_positions[target_room] = saved_player
        self.restricted_warning_at = -9.0
        self.peak_exposure = clamp(float(as_int(state.get("peak_exposure", 0))), 0.0, 100.0)
        x, y = self.world.start
        self.player = Agent(float(x), float(y), coat=int(self.avatar["coat"]), hair=int(self.avatar["hair"]),
                            skin=int(self.avatar["skin"]), hat=bool(self.avatar["hat"]),
                            accessory=int(self.avatar["accessory"]))
        # Guards belong to the private wing; switch_room() creates them.
        self.watchmen = []
        self.exposure = 0.0
        self.hidden = False
        self.blending = False
        self.crouched = False
        self.running = False
        self.click_destination = None
        self.last_tick = time.perf_counter()
        self.world_pil = None
        self.world_photo = None
        self.scene_lights = []
        self.cam_x = clamp(self.player.x - VISIBLE_W / 2, 0, WORLD_W - VISIBLE_W)
        self.cam_y = clamp(self.player.y - VISIBLE_H / 2, 0, WORLD_H - VISIBLE_H)
        self.overlay = None
        self.cutscene_step = 0
        self.dialogue_step = 0
        self.confront_step = 0
        self.focus = False
        self.clear_held()
        self.switch_room(target_room, arriving=True)

    def room_portals(self):
        # Transitions are attached to architectural features, not to unrelated
        # dark squares in the middle of an otherwise identical room.
        if self.room_index == 0:
            return [("staff", (506, 214), "Open the service door"),
                    ("secret", find_nearest_open(self.world, SECRET_FEATURES[self.chapter][0]),
                     "Inspect " + SECRET_FEATURES[self.chapter][1])]
        if self.room_index == 1:
            return [("hall", (48, 209), "Return through the service door")]
        return [("hall", (276, 321), "Climb the concealed stair")]

    def secret_requirements_met(self):
        # The detective recognizes the pull-ring only after comparing soot,
        # the altered timeline, and the witness account. The fireplace is
        # still a physical fireplace, not a menu disguised as a hatch.
        return 0 in self.seen and 1 in self.seen and self.witness_spoken

    def portal_nearby(self):
        for key, pos, description in self.room_portals():
            if distance(self.player.feet, pos) < 35:
                return key, pos, description
        return None

    def refresh_room_art(self):
        cache_key = (self.chapter, self.room_index, bool(self.secret_unlocked) if self.room_index == 0 else False)
        if cache_key not in self.room_art_cache:
            painter = RoomPainter(self.chapter, self.room_index,
                                  hearth_open=self.secret_unlocked)
            image = painter.render_room(self.world)
            scaled = image.resize((WORLD_W * PIXEL_SCALE, WORLD_H * PIXEL_SCALE), Image.Resampling.NEAREST)
            self.room_art_cache[cache_key] = (image, ImageTk.PhotoImage(scaled), painter.lights)
        self.room_art_cache.move_to_end(cache_key)
        self.world_pil, self.world_photo, self.scene_lights = self.room_art_cache[cache_key]
        # Tk photos are native allocations, not just lightweight Python refs.
        # Keep the current and last few rooms, not every room from ten cases.
        while len(self.room_art_cache) > 4:
            self.room_art_cache.popitem(last=False)

    def switch_room(self, dest, arriving=False):
        if not arriving:
            self.room_positions[self.room_index] = list(self.player.feet)
        old_room = self.room_index
        self.room_index = dest
        self.world = make_room(self.chapter, dest)
        self.nav = NavigationGrid(self.world)
        # Every doorway has a matching destination threshold. In particular,
        # the hidden passage enters BELOW the fireplace, not another hall.
        secret_exit = find_nearest_open(self.world, SECRET_FEATURES[self.chapter][0])
        door_spawns = {0: (486, 213) if old_room == 1 else secret_exit,
                       1: (56, 209), 2: (278, 319)}
        # Arriving (loading a chapter) resumes where the detective last stood
        # in that room, or at the room's entrance on a first visit.
        if arriving:
            spawn = self.room_positions.get(dest, self.world.start)
        else:
            spawn = door_spawns[dest]
        self.player.x, self.player.y = find_nearest_open(self.world, spawn)
        self.player.vx = self.player.vy = 0
        self.click_destination = None
        self.click_path = []
        self.hidden = self.blending = False
        self.exposure = 0
        if dest == 1:
            self.watchmen = [
                PatrolGuard(Agent(*self.world.patrol[0], "right", coat=1, hair=2, skin=0,
                                  hat=True, accessory=3), list(self.world.patrol), "security"),
                PatrolGuard(Agent(418, 145, "left", coat=1, hair=2, skin=1,
                                  hat=True, accessory=3), [(358, 151), (468, 151), (470, 197), (359, 197)], "enforcer"),
            ]
            for g in self.watchmen:
                g.actor.x, g.actor.y = find_nearest_open(self.world, g.actor.feet)
                g.route = [find_nearest_open(self.world, pos) for pos in g.route]
        else:
            self.watchmen = []
        self._scene_ready = False
        self._background_id = None
        self.refresh_room_art()
        self.cam_x = clamp(self.player.x - VISIBLE_W / 2, 0, WORLD_W - VISIBLE_W)
        self.cam_y = clamp(self.player.y - VISIBLE_H / 2, 0, WORLD_H - VISIBLE_H)
        if not arriving:
            if dest not in self.room_positions:
                self.show_caption(ROOM_MOODS[self.chapter][dest], duration=5.5)
            self.save()
        self.redraw()

    def begin_room_transition(self, dest, action):
        self.transition_to = dest
        self.transition_from = self.room_index
        self.transition_time = 0.0
        self.transition_started_at = time.perf_counter()
        self.transition_switched = False
        self.transition_action = action
        self.overlay = "room_transition"
        self.clear_held()
        self.redraw()

    def use_portal(self, key):
        if key == "secret":
            if not self.secret_unlocked:
                if not self.secret_requirements_met():
                    if 0 in self.seen and 1 in self.seen:
                        self.show_caption("The scratches suggest a moving panel. The witness may know what shifted it.")
                    else:
                        self.show_caption("The fitting looks unusual, but you cannot yet see what it operates.")
                    return
                self.secret_unlocked = True
                self.room_art_cache.pop((self.chapter, 0, True), None)
                self.refresh_room_art()
                self.show_caption(SECRET_FEATURES[self.chapter][2])
            self.begin_room_transition(2, "descend")
        elif key == "staff":
            self.begin_room_transition(1, "door")
        elif key == "hall":
            self.begin_room_transition(0, "ascend" if self.room_index == 2 else "door")

    def draw_room_transition(self):
        self.canvas.delete("room_transition_fx")
        t = clamp(self.transition_time / self.transition_duration, 0.0, 1.0)
        # Animated vignette and overhead stone staircase. The detective moves
        # down the steps in discrete pixel frames as the room changes behind it.
        self.canvas.create_rectangle(0, 0, SW, SH, fill="#06111b", outline="",
                                     tags="room_transition_fx")
        mx, my = SW // 2, SH // 2
        self.canvas.create_rectangle(mx - 263, my - 213, mx + 263, my + 213,
                                     fill="#111b29", outline="#78624d", width=3,
                                     tags="room_transition_fx")
        for j in range(12):
            yy = my - 188 + j * 32
            left = mx - 181 + j // 3 * 5
            right = mx + 181 - j // 3 * 5
            color = "#39414b" if (j + t * 12) % 3 < 1 else "#2c3540"
            self.canvas.create_rectangle(left, yy, right, yy + 28, fill=color,
                                         outline="#62707a", width=2, tags="room_transition_fx")
            self.canvas.create_line(left + 18, yy + 5, right - 18, yy + 5, fill="#7a716c",
                                    tags="room_transition_fx")
        py = my - 159 + t * 310 if self.transition_action == "descend" else my + 143 - t * 305
        px = mx + int(5 * math.sin(self.time_alive * 8))
        self.canvas.create_oval(px - 12, py - 12, px + 12, py + 10, fill="#172331", outline="#9b7558",
                                tags="room_transition_fx")
        self.canvas.create_rectangle(px - 8, py - 27, px + 8, py - 8, fill="#634654", outline="#211c26",
                                     tags="room_transition_fx")
        self.canvas.create_oval(px - 7, py - 43, px + 7, py - 25, fill="#d4aa8a", outline="#342d33",
                                tags="room_transition_fx")
        title = "THE HIDDEN WAY" if self.transition_action in {"descend", "ascend"} else "BEYOND THE DOOR"
        sub = (SECRET_FEATURES[self.chapter][2]
               if self.transition_action == "descend" else
               "Footsteps echo upwards. The concealed panel slides shut behind you."
               if self.transition_action == "ascend" else
               "The lock turns. A different part of the building waits beyond.")
        self.canvas.create_text(mx, 124, text=title, fill=C["gold"],
                                font=(self.font_title, 29, "bold"), tags="room_transition_fx")
        self.canvas.create_text(mx, 736, text=sub, fill=C["ivory"],
                                font=(self.font_small, 14), tags="room_transition_fx")

    def make_title(self):
        self.title_pil = TitleIllustration().render()
        scale = 2
        doubled = self.title_pil.resize((self.title_pil.width * scale, self.title_pil.height * scale),
                                        Image.Resampling.NEAREST)
        self.title_photo = ImageTk.PhotoImage(doubled)

    def new_investigation(self):
        has_progress = self.unlocked > 0 or any(
            isinstance(state, dict) and (state.get("seen") or state.get("solved"))
            for state in self.progress.values())
        if has_progress and not messagebox.askyesno(
                "New investigation",
                "Start again from Chapter I?\n\nEvery saved case, clue and deduction will be erased.",
                icon="warning", default="no", parent=self.root):
            return
        self.start_game(0, new=True)

    def start_game(self, chapter=None, new=False):
        if new:
            self.unlocked = 0
            self.finished = False
            self.progress = {}
            self.thumbnails.clear()
            chapter = 0
        else:
            self.cache_progress()
        idx = self.chapter if chapter is None else int(chapter)
        self.prepare_chapter(idx, reset=new)
        self.debug_score_override = False
        self.report_score = None
        self.screen = "game"
        state = self.progress.get(str(idx))
        if new or not (isinstance(state, dict) and state.get("seen")):
            self.cutscene_step = 0
            self.overlay = "cinematic"
        self.save()
        self.redraw()

    def return_menu(self):
        self.clear_held()
        self.hide_entry()
        self.save()
        self.overlay = None
        self.screen = "menu"
        self.screen_return = None
        self.redraw()

    def quit(self):
        self.save()
        self.root.destroy()

    # -------- drawing helpers --------
    def rect(self, x1, y1, x2, y2, fill, outline="", width=1):
        return self.canvas.create_rectangle(x1, y1, x2, y2, fill=fill, outline=outline, width=width)

    def line(self, *coords, fill=None, width=1, smooth=False, dash=None):
        return self.canvas.create_line(*coords, fill=fill or C["thin"], width=width, smooth=smooth, dash=dash)

    def text(self, x, y, content, size=13, color=None, width=None, bold=False, anchor="nw", serif=False, spacing1=0):
        return self.canvas.create_text(
            x, y,
            text=content,
            fill=color or C["ivory"],
            font=(self.font_title if serif else self.font_small, size, "bold" if bold else "normal"),
            width=width,
            anchor=anchor,
        )

    def frame_box(self, x1, y1, x2, y2, fill=None, border=None, inner=True):
        self.rect(x1, y1, x2, y2, fill or C["panel"], border or C["edge"], 2)
        if inner:
            self.rect(x1 + 4, y1 + 4, x2 - 4, y2 - 4, fill or C["panel"], C["thin"])
            for x in (x1 + 10, x2 - 10):
                for y in (y1 + 10, y2 - 10):
                    self.rect(x - 2, y - 2, x + 2, y + 2, C["gold_dim"])

    def button(self, x, y, w, h, label, callback, enabled=True, primary=False, size=13):
        hover = x <= self.mouse[0] <= x + w and y <= self.mouse[1] <= y + h
        fill = C["panel_high"] if enabled else C["panel"]
        if hover and enabled:
            fill = "#233f5b"
        stroke = C["gold"] if primary and enabled else C["edge"]
        if not enabled:
            stroke = C["thin"]
        self.rect(x, y, x + w, y + h, fill, stroke, 2 if primary else 1)
        if primary:
            self.rect(x + 4, y + 4, x + w - 4, y + h - 4, fill, C["gold_dim"])
        self.text(x + w / 2, y + h / 2, label, size, C["ivory"] if enabled else C["muted"], bold=primary,
                  anchor="center")
        if enabled:
            self.buttons.append(((x, y, x + w, y + h), callback))

    def progress_marks(self, x, y, complete, count=3, color=None):
        for j in range(count):
            col = color or C["gold"]
            if j < complete:
                self.canvas.create_polygon(x + j * 28, y + 8, x + j * 28 + 7, y, x + j * 28 + 14, y + 8, x + j * 28 + 7,
                                           y + 16, fill=col, outline=C["gold_dim"])
            else:
                self.canvas.create_oval(x + j * 28, y, x + j * 28 + 14, y + 14, outline=C["edge"])

    def icon_draw(self, x, y, kind, zoom=3, dim=False, anchor="nw"):
        img = self.icons.photo(kind, zoom=zoom, dim=dim)
        self.canvas.create_image(x, y, image=img, anchor=anchor)

    def moth(self, x, y, scale=1, color=None):
        color = color or C["gold"]
        self.canvas.create_polygon(x, y, x - 11 * scale, y - 5 * scale, x - 10 * scale, y + 6 * scale, x, y + 4 * scale,
                                   fill=color)
        self.canvas.create_polygon(x, y, x + 11 * scale, y - 5 * scale, x + 10 * scale, y + 6 * scale, x, y + 4 * scale,
                                   fill=color)
        self.canvas.create_polygon(x, y + 4 * scale, x - 7 * scale, y + 10 * scale, x - 2 * scale, y + 11 * scale,
                                   fill=color)
        self.canvas.create_polygon(x, y + 4 * scale, x + 7 * scale, y + 10 * scale, x + 2 * scale, y + 11 * scale,
                                   fill=color)
        self.line(x, y - 4 * scale, x, y + 10 * scale, fill=C["black"], width=max(1, scale))

    def draw_outer_frame(self, title="", subtitle=""):
        self.rect(0, 0, SW, SH, C["black"])
        self.rect(12, 10, SW - 12, SH - 12, C["midnight"], C["edge"], 2)
        self.line(26, 61, SW - 26, 61, fill=C["edge"], width=1)
        if title:
            self.text(30, 21, title, 21, C["ivory"], serif=True)
        if subtitle:
            self.text(30, 66, subtitle, 12, C["muted"])

    def toast(self, message, duration=3.0):
        self.toast_text = message
        self.toast_timer = duration

    def show_caption(self, message, duration=4.5):
        self.alert_caption = message
        self.alert_caption_timer = duration

    def hide_entry(self):
        if self.name_entry is not None and self.name_entry.winfo_exists():
            self.name_entry.place_forget()
        self.name_entry_open = False

    def draw_title(self):
        self.draw_outer_frame("BLACKWELL: INTO THE SHADOWS", "A TEN-CHAPTER NOIR MYSTERY")
        # The hero art is deliberately given space; this is not a wall of menus.
        self.canvas.create_image(30, 92, image=self.title_photo, anchor="nw")
        self.rect(30, 92, 1197, 861, "", C["edge"], 2)
        # Ambient rain composited in front of the painted mansion.
        for i, (base_x, base_y) in enumerate(self.particles):
            px = 30 + ((base_x * 2 + self.time_alive * (20 + i % 7 * 9)) % 1166)
            py = 92 + ((base_y * 2 + self.time_alive * (71 + i % 9 * 9)) % 767)
            self.line(px, py, px - 4, py + 10, fill="#476787", width=1)
        # Dark panel on left gives the typography a legible silhouette.
        self.rect(64, 153, 536, 786, "#091729", "#294560")
        self.text(96, 190, "BLACKWELL", 46, C["ivory"], serif=True, bold=True)
        self.text(98, 260, "INTO THE", 30, C["ivory"], serif=True, bold=True)
        self.text(96, 310, "SHADOWS", 40, C["ivory"], serif=True, bold=True)
        self.line(98, 364, 450, 364, fill=C["gold"], width=2)
        self.text(100, 379, "Truth hides in the details.", 14, C["muted"])
        self.button(96, 461, 310, 46, "CONTINUE", lambda: self.start_game(), primary=True)
        self.button(96, 521, 310, 44, "NEW INVESTIGATION", self.new_investigation)
        self.button(96, 578, 310, 44, "CHAPTER SELECT", lambda: self.open_screen("select"))
        self.button(96, 635, 310, 44, "DETECTIVE PROFILE", lambda: self.open_screen("profile"))
        self.button(96, 692, 310, 44, "SETTINGS / CONTROLS", lambda: self.open_screen("help"))
        self.text(96, 740, "'Every clue has a story.\n Somebody is writing ours.'", 12, C["cyan"])
        # Smaller file drawer instead of the previous wall of labels.
        self.frame_box(1215, 92, 1412, 861, fill=C["panel"], inner=False)
        self.moth(1307, 139, 2, C["gold"])
        self.text(1237, 191, "CASE FILES", 16, C["gold"], serif=True)
        for idx in range(10):
            ch = CHAPTERS[idx]
            y = 233 + idx * 56
            col = C["ivory"] if idx <= self.unlocked else C["muted"]
            self.text(1231, y, f"{roman(idx)}. {ch['title']}", 11, col, width=172)
            if idx <= self.unlocked:
                self.line(1232, y + 25, 1391, y + 25, fill=C["thin"])
        self.text(1234, 807, f"{self.unlocked + 1} OF 10 OPEN", 10, C["cyan"])

    def open_screen(self, screen):
        if self.screen != screen:
            self.screen_return = (self.screen, self.overlay)
        self.hide_entry()
        self.screen = screen
        self.redraw()

    def draw_chapter_select(self):
        self.draw_outer_frame("CASE FILES", "Choose a chapter from the same unfolding investigation.")
        for idx, ch in enumerate(CHAPTERS):
            col, row = idx % 5, idx // 5
            x = 42 + col * 281
            y = 124 + row * 340
            allowed = idx <= self.unlocked
            fill = C["panel"] if allowed else "#0a1727"
            border = C["gold"] if allowed and idx == self.chapter else C["edge"]
            self.frame_box(x, y, x + 261, y + 316, fill, border, inner=False)
            if idx not in self.thumbnails:
                lev = make_level(idx)
                full = PixelArt(idx).render(lev)
                crop = full.crop((48, 53, 497, 265)).resize((248, 130), Image.Resampling.NEAREST)
                if not allowed:
                    crop = ImageEnhance.Brightness(crop).enhance(.42)
                self.thumbnails[idx] = ImageTk.PhotoImage(crop)
            self.canvas.create_image(x + 7, y + 8, image=self.thumbnails[idx], anchor="nw")
            case_icon = ["moths", "ticket", "lock", "mask", "archive", "flower", "anchor", "globe", "scales", "candle"][
                idx]
            self.icon_draw(x + 196, y + 152, case_icon, zoom=2, dim=not allowed)
            self.text(x + 14, y + 158, f"CHAPTER {roman(idx)}", 11, C["cyan"] if allowed else C["muted"])
            self.text(x + 14, y + 184, ch["title"], 17, C["ivory"] if allowed else C["muted"], serif=True, bold=True,
                      width=234)
            self.text(x + 14, y + 233, ch["place"], 11, C["muted"], width=234)
            if allowed:
                self.button(x + 13, y + 267, 232, 32, "OPEN CASE", lambda n=idx: self.start_game(n))
            else:
                self.text(x + 16, y + 277, "SEALED", 11, C["gold_dim"])
        self.button(48, 808, 180, 40, "BACK", self.go_back)

    def draw_profile(self):
        self.draw_outer_frame("DETECTIVE PROFILE", "The person you create will carry every chapter of this story.")
        self.frame_box(45, 108, 550, 773)
        self.frame_box(579, 108, 1396, 773)
        self.text(80, 143, "THE INVESTIGATOR", 17, C["gold"], serif=True)
        self.sprite_preview(235, 263, zoom=8)
        self.text(80, 579, self.avatar["name"], 22, C["ivory"], serif=True)
        self.text(80, 621, "Sometimes the face in the case file\nis the last thing anyone remembers.", 12, C["muted"])
        self.text(624, 149, "NAME", 12, C["gold"])
        if self.name_entry is None or not self.name_entry.winfo_exists():
            self.name_entry = tk.Entry(self.root, bg="#142942", fg=C["ivory"], font=(self.font_small, 18),
                                       relief="flat", insertbackground=C["gold"])
        if not self.name_entry_open:
            self.name_entry.delete(0, "end")
            self.name_entry.insert(0, self.avatar["name"])
        self.name_entry.place(x=624, y=185, width=395, height=43)
        self.name_entry_open = True
        for row, (title, key, options) in enumerate([
            ("SKIN TONE", "skin", ["Warm", "Light", "Brown", "Deep"]),
            ("HAIR", "hair", ["Chestnut", "Auburn", "Raven", "Silver"]),
            ("COAT", "coat", ["Burgundy", "Midnight", "Olive", "Tobacco"]),
            ("HAT", "hat", ["No hat", "Fedora"]),
            ("ACCESSORY", "accessory", ["Brass", "Silver", "Red", "Jade"]),
        ]):
            y = 269 + row * 80
            self.text(626, y, title, 13, C["gold"])
            self.button(869, y - 3, 37, 31, "‹", lambda k=key: self.cycle_avatar(k, -1), size=18)
            self.text(1000, y + 14, options[int(self.avatar[key]) % len(options)], 14, C["ivory"], anchor="center")
            self.button(1098, y - 3, 37, 31, "›", lambda k=key: self.cycle_avatar(k, 1), size=18)
        self.button(1125, 679, 217, 43, "CONFIRM PROFILE", self.confirm_profile, primary=True)
        self.button(48, 808, 180, 40, "BACK", self.go_back)

    def sprite_preview(self, x, y, zoom=8):
        image = self.sprite_factory.photo(
            int(self.avatar["coat"]), int(self.avatar["hair"]), int(self.avatar["skin"]),
            "down", (self.tick_count // 6) % 6, bool(self.avatar["hat"]),
            int(self.avatar["accessory"]), zoom=zoom,
        )
        self.canvas.create_image(x, y, image=image, anchor="n")

    def cycle_avatar(self, key, delta):
        if self.name_entry is not None and self.name_entry.winfo_exists():
            self.avatar["name"] = self.name_entry.get().strip()[:22] or self.avatar["name"]
        size = 2 if key == "hat" else 4
        self.avatar[key] = (int(self.avatar[key]) + delta) % size
        self.player.coat = int(self.avatar["coat"])
        self.player.skin = int(self.avatar["skin"])
        self.player.hair = int(self.avatar["hair"])
        self.player.hat = bool(self.avatar["hat"])
        self.player.accessory = int(self.avatar["accessory"])
        self.save()
        self.redraw()

    def confirm_profile(self):
        if self.name_entry is not None and self.name_entry.winfo_exists():
            self.avatar["name"] = self.name_entry.get().strip()[:22] or "Detective"
        self.hide_entry()
        self.save()
        self.return_menu()

    def profile_return(self):
        if self.name_entry is not None and self.name_entry.winfo_exists():
            self.avatar["name"] = self.name_entry.get().strip()[:22] or "Detective"
        self.hide_entry()
        self.return_menu()

    def draw_help(self):
        self.draw_outer_frame("HOW TO PLAY",
                              "A less cluttered interface. The evidence is in the world, not under floating letters.")
        self.frame_box(60, 119, 927, 766)
        self.frame_box(951, 119, 1380, 766)
        self.text(95, 150, "CONTROLS", 22, C["gold"], serif=True)
        instruction_rows = [
            ("WASD / ARROWS", "Move freely through doors and around furniture."),
            ("CTRL", "Move slowly and quietly. Guards still see you in open view."),
            ("SPACE", "Continue dialogue and story moments."),
            ("E", "Examine nearby physical evidence or speak to people."),
            ("J", "Open your field journal and collected documents."),
            ("TAB", "Open the evidence board and build real deductions."),
            ("H", "Enter or leave nearby concealment."),
            ("B", "Blend into a nearby small group if you move slowly."),
            ("E / COATSTAND", "Choose a staff or guest disguise for infiltration."),
            ("V", "Hold to preview each guard's line-of-sight patrol."),
            ("Q", "Toss a coin to draw a guard toward its sound."),
            ("ESC", "Close an overlay or return to the title screen."),
            ("MOUSE", "Choose dialogue, evidence and destinations."),
        ]
        for j, (key, explanation) in enumerate(instruction_rows):
            yy = 210 + j * 39
            self.text(99, yy, key, 12, C["cyan"])
            self.text(283, yy, explanation, 12, C["ivory"], width=565)
        self.text(978, 150, "THE MYSTERY", 21, C["gold"], serif=True)
        self.text(978, 212, wrapped(
            "Walk into a room. Look at the clock, the footprints, the note. "
            "Get close enough to study them; only then does the journal have a reason to remember them.", 37
        ), 13, C["ivory"], width=357)
        self.text(978, 370, wrapped(
            "Your accusations require three distinct deductions. The truth is built by matching "
            "evidence against plausible alternative explanations; clicking an unexplored clue proves nothing.", 37
        ), 13, C["ivory"], width=357)
        self.text(978, 557, wrapped(
            "Inspect the public rooms without pressure. Navy-uniformed guards control the private offices. Watch their routes, wait for an opening, or wear staff clothing; experienced guards recognize strangers.",
            37
        ), 13, C["ivory"], width=357)
        self.button(66, 802, 186, 40, "BACK", self.go_back)

    # -------- world projection --------
    def world_to_screen(self, wx, wy):
        return (VIEW_X + (wx - self.cam_x) * PIXEL_SCALE,
                VIEW_Y + (wy - self.cam_y) * PIXEL_SCALE)

    def screen_to_world(self, sx, sy):
        return (self.cam_x + (sx - VIEW_X) / PIXEL_SCALE,
                self.cam_y + (sy - VIEW_Y) / PIXEL_SCALE)

    def projected_sprite(self, agent, walking=None, ghost=False):
        x, y = self.world_to_screen(agent.x, agent.y)
        if not (VIEW_X - 90 <= x <= VIEW_X + VIEW_W + 90 and VIEW_Y - 120 <= y <= VIEW_Y + VIEW_H + 70):
            return
        frame = int(agent.frame) % 6 if walking is None else walking
        coat, hat, accessory = agent.coat, agent.hat, agent.accessory
        if agent is self.player and self.disguise and not self.cover_blown:
            if self.disguise == "staff":
                coat, hat, accessory = (self.chapter + 2) % len(COAT_SWATCHES), True, 1
            else:
                coat, hat, accessory = (self.chapter + 1) % len(COAT_SWATCHES), False, 2
        img = self.sprite_factory.photo(coat, agent.hair, agent.skin, agent.facing,
                                        frame, hat, accessory, PIXEL_SCALE, ghost)
        self.canvas.create_image(x, y, image=img, anchor="s", tags="world_render")

    def world_emitter(self, x, y, base=10, color="#b78751", alpha=False):
        sx, sy = self.world_to_screen(x, y)
        flicker = (math.sin(self.time_alive * 13 + x * .2) + 1) * 1.2
        self.canvas.create_oval(sx - base - flicker, sy - base * .7, sx + base + flicker, sy + base * .7,
                                outline=color, stipple="gray75", tags="world_render")

    def world_sparkle(self, x, y):
        sx, sy = self.world_to_screen(x, y)
        glow = 2 + abs(math.sin(self.time_alive * 3)) * 4
        col = C["gold"]
        self.canvas.create_line(sx - glow, sy, sx + glow, sy, fill=col, tags="world_render")
        self.canvas.create_line(sx, sy - glow, sx, sy + glow, fill=col, tags="world_render")

    def _hud_signature(self):
        """The sidebar changes only when visible information changes."""
        nearby = self.nearest_object()
        portal = self.portal_nearby()
        return (self.chapter, self.room_index, len(self.seen), len(self.solved),
                self.witness_spoken, self.disguise, self.cover_blown,
                self.coins, self.hidden, self.blending, self.crouched,
                round(self.exposure / 5), bool(self.toast_timer), self.toast_text if self.toast_timer else "",
                bool(self.alert_caption_timer), self.alert_caption if self.alert_caption_timer else "",
                nearby[0] if nearby else None, portal[0] if portal else None,
                self.avatar['name'])

    def draw_game_scene(self):
        """Keep all moving canvas objects alive and move them in place.

        Canvas item creation/deletion is relatively costly on macOS/Aqua Tk.
        V8 rebuilt dozens of particles and sprites every frame; this version
        allocates them once per room and changes only their coordinates.
        """
        first = (not getattr(self, "_scene_ready", False)
                 or self.overlay is not None
                 or not self.canvas.find_withtag("chrome"))
        if first:
            self.canvas.delete("all")
            self._background_id = None
            self._world_nodes = {}
            self._world_particles = {}
            self._scene_emitters = {}
            self._world_alerts = {}
            self._world_sparkle = []
            self._world_decoy = []
            self._focus_was_active = False
            self._last_chrome_signature = None
            self.buttons.clear()

        self._render_world_layer()
        signature = self._hud_signature()
        if first or (signature != self._last_chrome_signature and
                     self.time_alive - self._chrome_updated_at >= 0.22):
            self.canvas.delete("chrome")
            self.buttons.clear()
            # Tag the newly drawn HUD once so subsequent frames keep it intact.
            before = set(self.canvas.find_all())
            self._render_game_chrome()
            for item_id in self.canvas.find_all():
                if item_id not in before:
                    self.canvas.addtag_withtag("chrome", item_id)
            self._last_chrome_signature = signature
            self._chrome_updated_at = self.time_alive
        self.canvas.tag_lower("world_background")
        self.canvas.tag_lower("world_render", "chrome")
        if self.overlay is not None:
            self.buttons.clear()
            self.draw_overlay()
        self._scene_ready = self.overlay is None

    def _move_particle(self, key, px, py, size, color, oval=False):
        """Create only on first use; update coordinates during animation."""
        x, y = self.world_to_screen(px, py)
        if not (VIEW_X < x < VIEW_X + VIEW_W and VIEW_Y < y < VIEW_Y + VIEW_H):
            x, y = -100, -100
        if oval:
            coords = (x - size, y - size, x + size, y + size)
        else:
            coords = (x, y, x + size, y + size)
        item = self._world_particles.get(key)
        if item is None:
            if oval:
                item = self.canvas.create_oval(*coords, fill=color, outline="", tags="world_render")
            else:
                item = self.canvas.create_rectangle(*coords, fill=color, outline="", tags="world_render")
            self._world_particles[key] = item
        else:
            self.canvas.coords(item, *coords)

    def _animate_particles(self):
        # The atmosphere has its own low-frequency cadence. Character input
        # and camera scrolling remain at the full simulation rate.
        if self.tick_count % 3 != 0 and self._world_particles:
            return
        theme = THEMES[self.chapter]["name"]
        elapsed = self.time_alive
        if theme in {"manor", "hotel", "archive", "court", "crypt", "observatory"}:
            for i, (wx, wy, sz, drift, bend) in enumerate(self.ambient.dust):
                x = wx + math.sin(elapsed * .23 + i) * drift
                y = wy + math.cos(elapsed * .31 + i * 1.8) * 11
                self._move_particle(("dust", i), x, y, max(1, int(sz * PIXEL_SCALE)),
                                    "#bd9664" if i % 4 == 0 else "#8b7c77")
        if theme in {"manor", "theater", "archive", "crypt"}:
            for i, (wx, wy, sz, phase) in enumerate(self.ambient.embers):
                x = wx + math.sin(elapsed * (1 + phase) + i) * 8
                y = wy - (elapsed * (5 + phase * 2) + i * 13) % 68
                self._move_particle(("ember", i), x, y, sz,
                                    "#d8a563" if i % 2 else "#9f624a")
        if theme in {"greenhouse", "docks"}:
            for i, (wx, wy, sz, phase) in enumerate(self.ambient.sparks):
                x = wx + math.sin(elapsed * .8 + phase) * 7
                y = wy + math.cos(elapsed * .9 + phase) * 9
                radius = sz + .8 * math.sin(elapsed * 2 + i)
                self._move_particle(("spark", i), x, y, radius,
                                    "#97c5a5" if theme == "greenhouse" else "#5f91a4", oval=True)

    def _set_world_sprite(self, agent, ghost=False):
        x, y = self.world_to_screen(agent.x, agent.y)
        if not (VIEW_X - 90 <= x <= VIEW_X + VIEW_W + 90 and
                VIEW_Y - 120 <= y <= VIEW_Y + VIEW_H + 70):
            entry = self._world_nodes.get(id(agent))
            if entry is not None and not entry[2]:
                self.canvas.itemconfigure(entry[0], state="hidden")
                entry[2] = True
            return
        frame = int(agent.frame) % 6
        coat, hat, accessory = agent.coat, agent.hat, agent.accessory
        if agent is self.player and self.disguise and not self.cover_blown:
            if self.disguise == "staff":
                coat, hat, accessory = (self.chapter + 2) % len(COAT_SWATCHES), True, 1
            else:
                coat, hat, accessory = (self.chapter + 1) % len(COAT_SWATCHES), False, 2
        state = (coat, agent.hair, agent.skin, agent.facing, frame, hat, accessory,
                 PIXEL_SCALE, ghost)
        key = id(agent)
        entry = self._world_nodes.get(key)
        if entry is None:
            photo = self.sprite_factory.photo(*state[:4], state[4], state[5], state[6],
                                              state[7], state[8])
            item = self.canvas.create_image(x, y, image=photo, anchor="s", tags="world_render")
            self._world_nodes[key] = [item, state, False]
        else:
            item, old_state, was_hidden = entry
            self.canvas.coords(item, round(x), round(y))
            if was_hidden:
                self.canvas.itemconfigure(item, state="normal")
                entry[2] = False
            if old_state != state:
                photo = self.sprite_factory.photo(*state[:4], state[4], state[5], state[6],
                                                  state[7], state[8])
                self.canvas.itemconfigure(item, image=photo)
                entry[1] = state
        # Actors are layered by their feet, so a detective can pass behind NPCs.
        self.canvas.tag_raise(item)

    def _render_world_layer(self):
        bgx, bgy = self.world_to_screen(0, 0)
        bgx, bgy = round(bgx), round(bgy)
        if self._background_id is None:
            self._background_id = self.canvas.create_image(
                bgx, bgy, image=self.world_photo, anchor="nw", tags="world_background")
        else:
            self.canvas.coords(self._background_id, bgx, bgy)

        self._animate_particles()
        if self.room_index != 2:
            for entry in self.world.props:
                if entry[0] not in {"candle", "lantern", "fireplace"}:
                    continue
                x, y = self.world_to_screen(entry[1], entry[2])
                r = 4 + (math.sin(self.time_alive * 13 + entry[1] * .2) + 1) * 1.2
                key = (entry[1], entry[2])
                item = self._scene_emitters.get(key)
                coords = (x - r, y - r * .7, x + r, y + r * .7)
                if item is None:
                    self._scene_emitters[key] = self.canvas.create_oval(
                        *coords, outline="#b78751", stipple="gray75", tags="world_render")
                elif self.tick_count % 2 == 0:
                    self.canvas.coords(item, *coords)

        actors = [*([self.world.witness] if self.room_index == 0 else []),
                  *([self.world.killer] if self.room_index == 1 else []),
                  *self.world.civilians,
                  *(guard.actor for guard in self.watchmen), self.player]
        actors.sort(key=lambda actor: actor.y)
        for actor in actors:
            if actor in self.world.civilians:
                actor.frame = self.time_alive * .4
            self._set_world_sprite(actor, ghost=(actor is self.player and self.hidden))

        for guard in self.watchmen:
            key = id(guard)
            mode = guard.mode
            item = self._world_alerts.get(key)
            if mode not in {"curious", "investigate", "search", "pursue"}:
                if item is not None:
                    self.canvas.itemconfigure(item, state="hidden")
                continue
            x, y = self.world_to_screen(guard.actor.x, guard.actor.y)
            warning = "!" if mode == "pursue" else "?"
            if item is None:
                item = self.canvas.create_text(x, y - 104, text=warning,
                                               font=(self.font_small, 19, "bold"),
                                               fill=C["red"] if warning == "!" else C["gold"], tags="world_render")
                self._world_alerts[key] = item
            else:
                self.canvas.coords(item, x, y - 104)
                self.canvas.itemconfigure(item, text=warning,
                                          fill=C["red"] if warning == "!" else C["gold"], state="normal")

        # Sightlines are optional; do not pay for them when the player is not
        # holding V. Retain all non-focus objects through the next frame.
        if self.focus:
            self.canvas.delete("focus_fx")
            for guard in self.watchmen:
                self.draw_watchman_cone(guard)
                route = [self.world_to_screen(*pt) for pt in guard.route]
                for a, b in zip(route, route[1:] + route[:1]):
                    self.canvas.create_line(*a, *b, fill="#657d94", dash=(2, 8),
                                            tags=("world_render", "focus_fx"))
            self._focus_was_active = True
        elif self._focus_was_active:
            self.canvas.delete("focus_fx")
            self._focus_was_active = False

        if self.decoy is not None and self.time_alive < self.decoy_expire:
            x, y = self.world_to_screen(*self.decoy)
            radius = 5 + 23 * max(0.0, 1 - (self.decoy_expire - self.time_alive) / 1.35)
            if not self._world_decoy:
                self._world_decoy = [
                    self.canvas.create_oval(0, 0, 1, 1, outline="#c9b478", dash=(3, 5), tags="world_render"),
                    self.canvas.create_oval(0, 0, 1, 1, fill="#d7c08a", outline="", tags="world_render")]
            self.canvas.coords(self._world_decoy[0], x - radius, y - radius * .55, x + radius, y + radius * .55)
            self.canvas.coords(self._world_decoy[1], x - 3, y - 2, x + 3, y + 2)
            for item in self._world_decoy:
                self.canvas.itemconfigure(item, state="normal")
        elif self._world_decoy:
            for item in self._world_decoy:
                self.canvas.itemconfigure(item, state="hidden")

        near = self.nearest_object()
        visible = (near is not None and near[0].startswith("clue_") and
                   int(near[0][5:]) not in self.seen and
                   math.sin(self.time_alive * 5) > .45)
        if visible:
            _, xy, _ = near
            x, y = self.world_to_screen(xy[0] + 4, xy[1] - 8)
            size = 2 + abs(math.sin(self.time_alive * 3)) * 4
            if not self._world_sparkle:
                self._world_sparkle = [
                    self.canvas.create_line(x - size, y, x + size, y, fill=C["gold"], tags="world_render"),
                    self.canvas.create_line(x, y - size, x, y + size, fill=C["gold"], tags="world_render")]
            else:
                self.canvas.coords(self._world_sparkle[0], x - size, y, x + size, y)
                self.canvas.coords(self._world_sparkle[1], x, y - size, x, y + size)
                for item in self._world_sparkle:
                    self.canvas.itemconfigure(item, state="normal")
        elif self._world_sparkle:
            for item in self._world_sparkle:
                self.canvas.itemconfigure(item, state="hidden")

    def _render_game_chrome(self):
        ch = CHAPTERS[self.chapter]
        self.rect(0, 0, SW, VIEW_Y - 1, C["midnight"])
        self.rect(0, VIEW_Y, VIEW_X - 1, VIEW_Y + VIEW_H + 1, C["midnight"])
        self.rect(VIEW_X + VIEW_W + 1, VIEW_Y, SW, VIEW_Y + VIEW_H + 1, C["midnight"])
        self.rect(0, VIEW_Y + VIEW_H + 1, SW, SH, C["midnight"])
        self.rect(VIEW_X, VIEW_Y, VIEW_X + VIEW_W, VIEW_Y + VIEW_H,
                  "", C["edge"], 2)
        self.rect(0, 0, SW, 86, C["midnight"])
        self.line(26, 86, SW - 25, 86, fill=C["edge"])
        self.text(34, 17, "BLACKWELL: INTO THE SHADOWS", 18, C["gold"], serif=True)
        self.text(34, 50, f"CASE {roman(self.chapter)}   /   {ch['place'].upper()}",
                  12, C["muted"])
        self.button(900, 26, 112, 40, "BACK", self.go_back)
        self.draw_game_sidebar()
        self.draw_game_footer(self.nearest_object())
        if self.toast_timer > 0:
            self.draw_toast()

    def draw_watchman_cone(self, watchman):
        """Sightline guides available on V: narrow, line-of-sight clipped rays."""
        actor = watchman.actor
        x, y = self.world_to_screen(actor.x, actor.y)
        base = {"right": 0, "down": math.pi / 2, "left": math.pi,
                "up": -math.pi / 2}.get(actor.facing, 0)
        max_range = 98 if watchman.rank == "enforcer" else 91
        for offset in (-.56, -.28, 0, .28, .56):
            t = base + offset
            last = actor.feet
            for d in range(5, max_range, 5):
                v = (actor.x + math.cos(t) * d, actor.y + math.sin(t) * d)
                if self.obstructed(*v, radius=1):
                    break
                last = v
            tx, ty = self.world_to_screen(*last)
            self.canvas.create_line(x, y, tx, ty, fill="#b1a27c" if abs(offset) else "#dac28e",
                                    dash=(3, 7), tags=("world_render", "focus_fx"))

    def draw_game_sidebar(self):
        x1, x2 = 1041, 1413
        self.frame_box(x1, 103, x2, 780, fill=C["panel"])
        self.moth(1102, 158, scale=2)
        self.text(1156, 138, "FIELD NOTES", 19, C["ivory"], serif=True)
        self.line(1070, 211, 1380, 211, fill=C["thin"])
        self.text(1071, 227, ROOM_TITLES[self.chapter][self.room_index].upper(), 11, C["cyan"])
        status = ROOM_MOODS[self.chapter][self.room_index]
        self.text(1071, 252, wrapped(status, 29), 11, C["ivory"], width=298)
        self.text(1071, 318, "EVIDENCE", 11, C["gold"])
        self.progress_marks(1074, 340, len(self.seen))
        self.text(1194, 318, "DEDUCTION", 11, C["gold"])
        self.progress_marks(1197, 340, len(self.solved), color=C["cyan"])
        self.line(1070, 391, 1380, 391, fill=C["thin"])
        self.text(1071, 412, "SECURITY AWARENESS", 11, C["muted"])
        self.rect(1074, 443, 1360, 454, "#192c3d", C["edge"])
        self.rect(1075, 444, 1075 + 2.84 * self.exposure, 453, C["red"])
        if self.hidden:
            state = "Concealed"
            state_color = C["green"]
        elif self.blending:
            state = "Anonymous in the crowd"
            state_color = C["green"]
        elif self.crouched:
            state = "Keeping low"
            state_color = C["cyan"]
        else:
            state = "Unseen" if self.exposure < 20 else "Watched"
            state_color = C["muted"] if self.exposure < 20 else C["red"]
        self.text(1075, 467, state, 12, state_color)
        identity = (COVER_IDENTITIES[self.chapter][0 if self.disguise == "staff" else 1]
                    if self.disguise else "Your own clothes")
        if self.cover_blown:
            identity = "Cover compromised"
        short_identity = identity if len(identity) <= 20 else identity[:18] + "…"
        self.text(1075, 484, f"Cover: {short_identity}", 10,
                  C["red"] if self.cover_blown else C["cyan"], width=219)
        self.text(1367, 484, f"DISTRACTIONS  {self.coins}", 10, C["muted"], anchor="ne")
        self.line(1070, 511, 1380, 511, fill=C["thin"])
        self.text(1071, 526, "CURRENT THREAD", 11, C["gold"])
        if self.room_index == 2:
            objective = "Read the surviving records. The concealed route may reveal what the public archives omit."
        elif self.room_index == 1 and len(self.solved) < 3:
            objective = "The private wing holds guarded records. Study them carefully, then return to your deductions."
        elif len(self.seen) < 3:
            objective = "Explore the public room. Each object tells part of the story; the staff door leads elsewhere."
        elif not self.witness_spoken:
            objective = "Interview the witness. Physical clues alone cannot establish the full timeline."
        elif len(self.solved) < 3:
            objective = "Compare the testimony with your evidence. Test each conclusion on the board."
        else:
            objective = "The combined proof identifies the killer. Find a safe approach to the private rooms."
        self.text(1073, 553, wrapped(objective, 39), 12, C["ivory"], width=290)
        self.button(1068, 672, 137, 43, "JOURNAL", lambda: self.open_overlay("journal"))
        self.button(1218, 672, 160, 43, "EVIDENCE", lambda: self.open_overlay("board"), primary=True)
        self.text(1072, 733, "GOLD BADGE + NAVY CAP = SECURITY", 10, C["muted"])

    def draw_game_footer(self, near):
        portal = self.portal_nearby()
        if portal is not None:
            near = (portal[0], portal[1], "E  " + portal[2])
        self.rect(26, 793, 1412, 875, C["midnight"], C["edge"])
        self.text(45, 814, "WASD Move    CTRL Quiet walk    E Interact    Q Coin    V Sightlines", 12, C["muted"])
        if near:
            key, pos, display = near
            self.text(46, 844, f"{display}   •   E", 13, C["gold"])
        elif self.alert_caption_timer > 0:
            self.text(46, 842, wrapped(self.alert_caption, 88), 12, C["cyan"], width=830)
        else:
            self.text(46, 842, "Nothing here is as ordinary as it looks.", 12, C["cyan"])
        self.text(1369, 820, f"{self.avatar['name']}", 11, C["gold"], anchor="ne")

    def draw_toast(self):
        self.rect(142, 695, 871, 769, C["panel_high"], C["gold"])
        self.text(160, 710, "FIELD OBSERVATION", 11, C["gold"])
        self.text(160, 735, self.toast_text, 12, C["ivory"], width=680)

    def ui_modal(self, x1=112, y1=94, x2=1328, y2=782, title=""):
        self.rect(x1, y1, x2, y2, C["midnight"], C["gold"], 2)
        self.rect(x1 + 6, y1 + 6, x2 - 6, y2 - 6, C["midnight"], C["thin"])
        self.line(x1 + 26, y1 + 72, x2 - 26, y1 + 72, fill=C["edge"])
        if title:
            self.text(x1 + 35, y1 + 26, title, 22, C["gold"], serif=True)
        self.button(x2 - 138, y1 + 21, 96, 37, "BACK", self.go_back)

    def draw_overlay(self):
        if self.overlay == "room_transition":
            self.draw_room_transition()
            return
        if self.overlay == "wardrobe":
            self.draw_wardrobe()
        elif self.overlay == "cinematic":
            self.draw_cinematic()
        elif self.overlay == "journal":
            self.draw_journal()
        elif self.overlay == "board":
            self.draw_board()
        elif self.overlay == "deduce":
            self.draw_deduction_choice()
        elif self.overlay == "deduce_result":
            self.draw_deduction_result()
        elif self.overlay == "dialogue":
            self.draw_dialogue()
        elif self.overlay == "evidence":
            self.draw_evidence_discovery()
        elif self.overlay == "confront":
            self.draw_confrontation()
        elif self.overlay == "chapter_end":
            self.draw_chapter_end()
        elif self.overlay == "caught":
            self.draw_caught()
        elif self.overlay == "pause":
            self.draw_pause()
        elif self.overlay == "debug":
            self.draw_debug_panel()

    def draw_cinematic(self):
        ch = CHAPTERS[self.chapter]
        self.ui_modal(title=f"CASE {roman(self.chapter)}  —  {ch['title']}")
        self.frame_box(143, 182, 1294, 564, fill="#0f2336")
        # World/location still image serves as a cutscene establishing shot.
        crop = self.world_pil.crop((50, 36, 493, 275))
        if getattr(self, "cutscene_img_step", None) != self.chapter:
            self.cutscene_photo = ImageTk.PhotoImage(crop.resize((504, 272), Image.Resampling.NEAREST))
            self.cutscene_img_step = self.chapter
        self.canvas.create_image(164, 234, image=self.cutscene_photo, anchor="nw")
        self.rect(163, 233, 669, 508, "", C["edge"])
        beats = [
            ch["cinematic"][0],
            ch["intro"][0],
            ch["cinematic"][1],
            ch["intro"][1],
            ch["intro"][2],
        ]
        total = len(beats)
        step = min(self.cutscene_step, total - 1)
        self.text(709, 223, "THE NIGHT UNFOLDS", 12, C["cyan"])
        self.text(709, 274, wrapped(beats[step], 37), 18, C["ivory"], width=516)
        self.text(710, 480, f"SCENE  {step + 1} / {total}", 11, C["muted"])
        self.text(164, 599, "Every shadow is a possible witness.", 15, C["muted"], serif=True)
        self.button(1043, 691, 198, 45, "CONTINUE", self.advance_cinematic, primary=True)
        self.text(163, 702, "SPACE  to continue", 12, C["cyan"])

    def advance_cinematic(self):
        sfx("menu_select")
        self.cutscene_step += 1
        if self.cutscene_step >= 5:
            self.overlay = None
            self.show_caption(CHAPTERS[self.chapter]["cinematic"][3])
        self.redraw()

    def draw_journal(self):
        ch = CHAPTERS[self.chapter]
        self.ui_modal(title="FIELD JOURNAL")
        # Warm parchment book held against the midnight game UI.
        self.rect(144, 183, 702, 740, C["paper"], "#826b51", 2)
        self.rect(706, 183, 1291, 740, "#e6d4ae", "#826b51", 2)
        self.line(703, 187, 703, 736, fill="#947453", width=4)
        self.text(164, 207, f"Case {roman(self.chapter)}", 21, C["ink"], serif=True)
        self.text(164, 248, ch["title"], 18, C["ink"], serif=True)
        self.line(165, 283, 678, 283, fill="#a48d69")
        self.text(165, 303, f"Victim: {ch['victim']}", 12, C["ink"])
        self.text(165, 335, wrapped(ch["threat"], 50), 13, C["ink"], width=480)
        self.text(165, 443, "A PRIVATE OBSERVATION", 12, "#825e40", bold=True)
        note = ch["journal_lore"][4 + min(5, self.ui_scroll % 6)]
        self.text(165, 474, wrapped(note, 50), 13, C["ink"], width=478)
        if self.witness_spoken:
            self.text(165, 568, "WITNESS STATEMENT", 12, "#825e40", bold=True)
            self.text(165, 603, wrapped(ch["witness"], 49), 12, C["ink"], width=478)
        else:
            self.text(165, 568, "Witness interview not yet recorded.", 12, "#8b7656")
        self.text(729, 204, "EVIDENCE RECORD", 20, C["ink"], serif=True)
        for idx, (name, detail) in enumerate(ch["clues"]):
            y = 252 + idx * 132
            found = idx in self.seen
            kind = EVIDENCE_SHAPES[self.chapter][idx]
            self.icon_draw(734, y - 3, kind, zoom=2, dim=not found)
            self.text(798, y, name if found else "[Unexamined evidence]", 15, C["ink"] if found else "#887959",
                      bold=found)
            self.text(798, y + 32, wrapped(
                detail if found else "There is something here you have not yet studied closely enough to remember.",
                50), 12, C["ink"] if found else "#8b795f", width=461)
            self.line(732, y + 102, 1271, y + 102, fill="#b7a17e")
        field_note = ("PRIVATE FILE: " + SECRET_REVEALS[
            self.chapter]) if self.infiltration_uncovered else "A private office may contain evidence the others do not want remembered."
        self.text(738, 656, wrapped(field_note, 73), 11, "#775940", width=515)

    def draw_board(self):
        ch = CHAPTERS[self.chapter]
        self.ui_modal(title="EVIDENCE BOARD")
        self.rect(146, 185, 1290, 735, "#79503a", "#b17d52", 3)
        for yy in range(193, 730, 15):
            for xx in range(151 + ((yy // 15) % 2) * 6, 1285, 13):
                self.rect(xx, yy, xx + 2, yy + 1, "#8f6142")
        self.text(177, 206, "Connect what you found. Test the hypothesis. Defend your conclusion.", 12, "#f0dbc2")
        # A muted procedural red-thread network replaces generic number badges.
        self.line(340, 348, 693, 352, 1050, 352, fill="#a64f4f", width=3)
        self.line(347, 390, 520, 625, 684, 395, fill="#883944", width=2)
        for j, (question, clue, answer) in enumerate(ch["questions"]):
            x = 167 + j * 373
            idx = j
            found = idx in self.seen
            solved = idx in self.solved
            method = METHODS[self.chapter * 3 + idx][0]
            paper = "#dfc69d" if found else "#bfae91"
            self.rect(x, 272, x + 344, 556, paper, "#947352", 2)
            self.ellipse_pin(x + 170, 272, solved)
            self.icon_draw(x + 285, 287, EVIDENCE_SHAPES[self.chapter][j], zoom=2, dim=not found)
            self.text(x + 22, 294, method.upper(), 13, "#54382c", bold=True, width=268)
            self.text(x + 22, 333, wrapped(question, 38), 14, "#30221d", width=299)
            self.line(x + 20, 423, x + 320, 423, fill="#b39b78")
            self.text(x + 22, 437, f"Supporting: {clue}", 12, "#7d5d43", width=300)
            self.text(x + 22, 478, "SUPPORTED" if solved else ("READY TO TEST" if found else "UNSUPPORTED"), 11,
                      "#35744c" if solved else "#7d5d43", bold=True)
            self.button(x + 22, 510, 300, 32, "REVIEW" if solved else "FORM A DEDUCTION",
                        lambda n=j: self.start_deduction(n), enabled=found, size=11)
        self.text(179, 615, "Every answer leaves a shadow. Follow the one the witnesses avoid.", 13, "#f0dbc2")
        self.text(179, 652,
                  f"CONCLUSIONS: {len(self.solved)}/3    WITNESS: {'RECORDED' if self.witness_spoken else 'NOT YET INTERVIEWED'}",
                  13, "#f0dbc2")

    def ellipse_pin(self, x, y, solved):
        self.canvas.create_oval(x - 9, y - 10, x + 9, y + 9, fill="#5d2a34" if not solved else "#4f6948",
                                outline="#e1a67e")
        self.canvas.create_oval(x - 3, y - 4, x + 3, y + 2, fill="#bb7a6b" if not solved else "#bad09f", outline="")

    def start_deduction(self, idx):
        if idx not in self.seen:
            self.toast("A conclusion needs something real beneath it.")
            return
        self.deduction_chosen = idx
        self.overlay = "deduce"
        self.redraw()

    def draw_deduction_choice(self):
        ch = CHAPTERS[self.chapter]
        idx = self.deduction_chosen
        method = METHODS[self.chapter * 3 + idx]
        question, clue, truth = ch["questions"][idx]
        self.ui_modal(title=f"REASONING  /  {method[0].upper()}")
        self.text(166, 202, "EVIDENCE IN HAND", 11, C["cyan"])
        self.text(166, 238, clue, 19, C["gold"], serif=True)
        self.text(166, 288, wrapped(ch["clues"][idx][1], 79), 14, C["ivory"], width=1050)
        self.line(165, 371, 1261, 371, fill=C["edge"])
        self.text(166, 398, question, 17, C["ivory"], bold=True)
        choices = self.deduction_options(idx)
        for j, option in enumerate(choices):
            yy = 449 + j * 88
            self.button(166, yy, 1075, 72, wrapped(option, 100), lambda k=j: self.answer_deduction(k), size=12)
        self.text(166, 728, "Only a conclusion consistent with the physical evidence belongs in the case file.", 11,
                  C["muted"])

    def deduction_options(self, idx):
        ch = CHAPTERS[self.chapter]
        correct = ch["questions"][idx][2]
        a, b = ch["deduction_decoys"][idx]
        options = [a, b, correct]
        order = (self.chapter * 5 + idx * 7 + 1) % 3
        return options[order:] + options[:order]

    def answer_deduction(self, selection):
        idx = self.deduction_chosen
        options = self.deduction_options(idx)
        correct = CHAPTERS[self.chapter]["questions"][idx][2]
        self.answer_correct = options[selection] == correct
        sfx("deduction_correct" if self.answer_correct else "deduction_wrong")
        if self.answer_correct:
            self.solved.add(idx)
            self.toast("The pieces fit. Another false story falls away.")
        else:
            self.wrong_attempts += 1
            self.deduction_mistakes.add(idx)
            # A mistaken theory is a reasoning error, not a noise event.
            self.toast("The evidence resists that explanation. Reconsider the details.")
        self.overlay = "deduce_result"
        self.save()
        self.redraw()

    def draw_deduction_result(self):
        idx = self.deduction_chosen
        ch = CHAPTERS[self.chapter]
        method = METHODS[self.chapter * 3 + idx][0]
        self.ui_modal(title="CONCLUSION  /  " + method.upper())
        self.moth(1159, 259, 3, C["gold"] if self.answer_correct else C["red"])
        self.text(169, 239, "THEORY ACCEPTED" if self.answer_correct else "THEORY REJECTED", 26,
                  C["green"] if self.answer_correct else C["red"], serif=True)
        if self.answer_correct:
            body = ch["questions"][idx][2]
        else:
            body = "A detail in your evidence contradicts that interpretation. No progress has been recorded."
        self.text(167, 328, wrapped(body, 70), 19, C["ivory"], width=960)
        self.line(166, 501, 1249, 501, fill=C["edge"])
        self.text(166, 532, "A theory can survive scrutiny, or collapse beneath a single detail.", 13, C["muted"],
                  width=1000)
        self.button(995, 688, 215, 44, "RETURN TO BOARD", lambda: self.open_overlay("board"), primary=True)

    def draw_dialogue(self):
        ch = CHAPTERS[self.chapter]
        self.ui_modal(title="AN INTERVIEW IN THE DARK")
        d = ch["dialogue"][min(self.dialogue_step, len(ch["dialogue"]) - 1)]
        self.frame_box(168, 207, 443, 575, fill="#172a40")
        speaker = d["speaker"]
        portrait = self.sprite_factory.photo(self.world.witness.coat,
                                             self.world.witness.hair,
                                             self.world.witness.skin,
                                             "down", (self.tick_count // 5) % 6,
                                             self.world.witness.hat, zoom=8)
        self.canvas.create_image(308, 266, image=portrait, anchor="n")
        self.frame_box(464, 207, 1223, 575, fill="#0c2036")
        self.text(493, 236, speaker, 21, C["gold"], serif=True)
        self.text(493, 311, wrapped(d["text"], 53), 18, C["ivory"], width=687)
        self.text(492, 520, "Not every answer is reliable. The journal records what is said, not what is proved.", 11,
                  C["cyan"], width=665)
        self.text(169, 680, "SPACE / ENTER  to continue", 12, C["cyan"])
        self.button(989, 674, 191, 44, "CONTINUE", self.advance_dialogue, primary=True)

    def advance_dialogue(self):
        self.dialogue_step += 1
        if self.dialogue_step >= len(CHAPTERS[self.chapter]["dialogue"]):
            self.overlay = None
            self.witness_spoken = True
            self.show_caption(CHAPTERS[self.chapter]["cinematic"][7])
            self.save()
        self.redraw()

    def draw_evidence_discovery(self):
        ch = CHAPTERS[self.chapter]
        idx = self.discovery_index
        obj = next((item for item in self.world.objects if item.id == f"clue_{idx}"), None)
        if obj is None:
            obj = next((item for item in make_level(self.chapter).objects if item.id == f"clue_{idx}"), None)
        if obj is None:
            self.overlay = None
            return
        self.ui_modal(title="AN OBJECT THAT DOES NOT BELONG")
        self.frame_box(153, 183, 458, 646, fill="#173048")
        scene_crop = self.world_pil.crop((max(0, int(obj.x) - 30), max(0, int(obj.y) - 30),
                                          min(WORLD_W, int(obj.x) + 30), min(WORLD_H, int(obj.y) + 30)))
        scaled = scene_crop.resize((250, 250), Image.Resampling.NEAREST)
        self.discovery_photo = ImageTk.PhotoImage(scaled)
        self.canvas.create_image(183, 230, image=self.discovery_photo, anchor="nw")
        self.icon_draw(264, 518, obj.kind, zoom=4)
        self.text(488, 227, obj.name, 24, C["gold"], serif=True)
        self.text(489, 307, wrapped(obj.details, 63), 17, C["ivory"], width=730)
        self.line(489, 461, 1218, 461, fill=C["edge"])
        self.text(489, 493, wrapped(ch["discovery_moments"][idx], 76), 14, C["cyan"], width=720)
        self.text(489, 600, "The detail stays with you. It will matter when the stories stop agreeing.", 12, C["muted"])
        self.button(978, 680, 210, 44, "RETURN TO SCENE", self.close_overlay, primary=True)

    def draw_confrontation(self):
        ch = CHAPTERS[self.chapter]
        self.ui_modal(title="THE PERSON IN THE SHADOW")
        self.frame_box(154, 199, 788, 624, fill="#111f34")
        self.frame_box(813, 199, 1286, 624, fill="#271a27")
        protagonist = self.sprite_factory.photo(self.player.coat, self.player.hair, self.player.skin,
                                                "right", (self.tick_count // 7) % 6, self.player.hat,
                                                self.player.accessory, zoom=7)
        antagonist = self.sprite_factory.photo(self.world.killer.coat, self.world.killer.hair,
                                               self.world.killer.skin, "left", 0, self.world.killer.hat,
                                               zoom=7)
        self.canvas.create_image(315, 311, image=protagonist, anchor="n")
        self.canvas.create_image(622, 307, image=antagonist, anchor="n")
        self.text(857, 231, ch["culprit"], 24, C["gold"], serif=True)
        self.text(857, 281, ch["role"], 12, C["muted"])
        premise, peril, proof = INVESTIGATION_STAKES[self.chapter]
        lines = [
            f"You name {ch['culprit']} and reconstruct the crime. {premise}",
            f"THE PROOF: {proof}",
            ch["reveal"],
            f"THE DANGER: {peril}",
            "The constables cannot be trusted with the only surviving testimony. Evelyn insists the killer must die tonight. "
            "You feel the weight of her demand—and begin to wonder why she keeps choosing you.",
        ]
        n = min(self.confront_step, len(lines) - 1)
        self.text(855, 339, wrapped(lines[n], 39), 15, C["ivory"], width=372)
        self.text(190, 576, "A sharp decision in a room too quiet for forgiveness.", 13, C["cyan"])
        if self.confront_step < len(lines) - 1:
            self.button(984, 679, 205, 45, "CONTINUE", self.advance_confrontation, primary=True)
        else:
            self.button(190, 671, 350, 49, "END THE MURDERER", self.execute_finale, primary=True)
            self.button(570, 671, 255, 49, "WITHDRAW", self.close_overlay)
        self.text(857, 575, "A complete case proves guilt. Evelyn's order to kill is a separate moral burden.", 11,
                  C["muted"], width=340)

    def advance_confrontation(self):
        self.confront_step += 1
        self.redraw()

    def execute_finale(self):
        # Stylized, non-graphic conclusion; no violent gameplay instructions.
        self.unlocked = max(self.unlocked, min(9, self.chapter + 1))
        self.thumbnails.clear()
        self.finished = self.chapter == 9
        # The report uses information the game already tracks, plus the
        # number of times the detective was caught during this chapter.
        if self.debug_score_override:
            self.report_score = int(clamp(self.debug_score, 0, 100))
        else:
            self.report_score = self.calculate_case_score()
        self.end_grade = self.ranks(self.report_score)
        self.overlay = "chapter_end"
        self.save()
        self.redraw()

    def calculate_case_score(self):
        """Return a simple 0-100 score for the completed investigation."""
        evidence_points = (len(self.seen) / 3) * 40
        optional_found = sum(1 for note in self.notes if 0 <= note <= 2)
        optional_points = (optional_found / 3) * 20
        stealth_points = 20 if self.spotted_count == 0 else max(0, 20 - self.spotted_count * 5)
        first_try = len(self.solved - self.deduction_mistakes)
        deduction_points = (first_try / 3) * 20
        return round(evidence_points + optional_points + stealth_points + deduction_points)

    def draw_chapter_end(self):
        """Render a completed case as a clean, legible investigation dossier."""
        ch = CHAPTERS[self.chapter]
        self.ui_modal(title=f"CASE FILE  /  {roman(self.chapter)}")

        paper = "#eee4ce"
        pale = "#f7f0df"
        ink = "#302b25"
        muted = "#695f51"
        red = "#973f39"
        blue = "#3d5260"
        rule = "#cabb9f"

        # Paper and binding, with all rules kept outside the text areas.
        self.rect(150, 180, 1290, 761, "#080e17", "#060910", 2)
        self.rect(144, 174, 1284, 755, "#d4c19e", "#887858", 2)
        self.rect(153, 183, 1275, 746, paper, "#b4a17e", 1)
        self.rect(170, 199, 175, 730, "#b79462")

        score = getattr(self, "report_score", self.calculate_case_score())
        grade = getattr(self, "end_grade", self.ranks(score))
        optional_found = sum(1 for note in self.notes if 0 <= note <= 2)
        first_try = len(self.solved - self.deduction_mistakes)
        evidence_points = round((len(self.seen) / 3) * 40)
        optional_points = round((optional_found / 3) * 20)
        stealth_points = 20 if self.spotted_count == 0 else max(0, 20 - self.spotted_count * 5)
        deduction_points = round((first_try / 3) * 20)

        # Editorial header.
        self.text(195, 201, "BLACKWELL  /  DETECTIVE AGENCY", 11, muted, bold=True)
        self.text(195, 224, "Final Investigation Report", 28, ink, serif=True, bold=True)
        self.text(197, 268, f"FILE {self.chapter + 1:02d}     •     {ch['title'].upper()}", 11, red, bold=True)
        self.rect(1042, 219, 1241, 280, pale, red, 2)
        self.text(1141, 232, "CASE CLOSED", 15, red, bold=True, anchor="n")
        self.text(1141, 257, "OFFICIAL RECORD", 9, muted, bold=True, anchor="n")
        self.line(195, 300, 1239, 300, fill=rule, width=2)

        # Three clearly separated details; suspect revealed only on case completion.
        identity = [(198, "VICTIM", ch["victim"], 280),
                    (521, "SCENE", ch["place"], 302),
                    (875, "DETECTIVE", self.avatar["name"], 335)]
        for x, label, value, width in identity:
            self.text(x, 313, label, 9, muted, bold=True)
            self.text(x, 336, value, 14, ink, serif=True, width=width)

        # The culprit gets its own prominent, easy-to-find report entry.
        self.rect(194, 377, 1238, 428, pale, rule, 1)
        self.rect(194, 377, 200, 428, red)
        self.text(218, 386, "CULPRIT IDENTIFIED", 10, red, bold=True)
        self.text(218, 404, ch["culprit"], 16, ink, serif=True, bold=True)
        self.text(1230, 398, "CONFIRMED", 10, red, bold=True, anchor="e")

        # Ledger on the left. Narrow row dividers appear below—not behind—text.
        self.text(198, 447, "INVESTIGATION BREAKDOWN", 12, ink, bold=True)
        self.text(585, 449, "FOUND", 9, muted, bold=True, anchor="ne")
        self.text(782, 449, "SCORE", 9, muted, bold=True, anchor="ne")
        rows = [
            ("Evidence recovered", f"{len(self.seen)} / 3", f"{evidence_points} / 40"),
            ("Optional discoveries", f"{optional_found} / 3", f"{optional_points} / 20"),
            ("Times detected", str(self.spotted_count), f"{stealth_points} / 20"),
            ("First-try deductions", f"{first_try} / 3", f"{deduction_points} / 20"),
        ]
        for i, (label, result, points) in enumerate(rows):
            y = 477 + i * 37
            if i % 2 == 0:
                self.rect(194, y - 3, 791, y + 30, pale)
            self.text(204, y + 2, label, 11, ink)
            self.text(585, y + 2, result, 11, blue, bold=True, anchor="ne")
            self.text(782, y + 2, points, 11, ink, bold=True, anchor="ne")
        self.text(200, 629, f"Incorrect theories: {self.wrong_attempts}", 10, muted)

        # Summary card and centered grade medallion.
        self.line(814, 448, 814, 649, fill=rule, width=2)
        self.text(841, 448, "FINAL ASSESSMENT", 12, ink, bold=True)
        self.text(842, 475, "TOTAL POINTS", 9, muted, bold=True)
        self.text(841, 492, str(score), 36, ink, serif=True, bold=True)
        self.text(934, 525, "/ 100", 11, muted)
        cx, cy, radius = 1122, 550, 63
        self.canvas.create_oval(cx-radius, cy-radius, cx+radius, cy+radius,
                                outline=red, width=3, fill=pale)
        self.canvas.create_oval(cx-radius+7, cy-radius+7, cx+radius-7, cy+radius-7,
                                outline="#c28b7d", width=1)
        self.text(cx, cy-8, grade, 53, red, serif=True, bold=True, anchor="center")
        self.text(cx, cy+38, "RANK", 9, red, bold=True, anchor="center")
        comments = {
            "S": "Outstanding investigation.",
            "A": "Excellent detective work.",
            "B": "A solid case, with some gaps.",
            "C": "The truth found; details missed.",
            "D": "Case closed; questions remain.",
        }
        self.text(842, 604, comments.get(grade, "Report filed."), 10, muted, width=235)

        # Dedicated, roomy notes block. Long text wraps within the paper.
        self.rect(194, 662, 1238, 731, pale, rule, 1)
        self.text(209, 673, "CASE NOTES", 10, red, bold=True)
        self.text(336, 672, ch["aftermath"], 10, ink, width=874)

        label = "RETURN TO TITLE" if self.chapter == 9 else "NEXT CHAPTER"
        self.button(173, 786, 280, 42, label, self.next_chapter, primary=True, size=11)
        self.button(472, 786, 245, 42, "CHAPTER SELECT", self.chapter_select, size=11)

    def draw_caught(self):
        self.ui_modal(title="A LAMP TURNS TOWARD YOU")
        self.text(165, 241, "They have seen you.", 29, C["red"], serif=True)
        self.text(165, 320,
                  "The watchman has a long memory and a shorter temper. He forces you back toward the entrance.", 17,
                  C["ivory"], width=850)
        self.text(165, 421, "Your notes, clues and deductions remain intact. Your position—and your cover—do not.", 14,
                  C["cyan"], width=880)
        self.button(925, 686, 270, 44, "RE-ENTER THE ROOM", self.reset_after_capture, primary=True)

    def open_debug(self):
        """Open developer tools using the backslash keyboard shortcut."""
        if self.screen in {"menu", "profile", "select", "help"}:
            self.cache_progress()
        self.debug_return_screen = self.screen
        self.debug_return_overlay = self.overlay
        self.debug_target_chapter = self.chapter
        if self.screen == "game" and self.overlay == "chapter_end":
            current = getattr(self, "report_score", None)
        else:
            current = self.calculate_case_score()
        if current is None:
            current = self.calculate_case_score()
        self.debug_score = int(clamp(current, 0, 100))
        if self.screen == "game":
            self.overlay = "debug"
        else:
            self.screen = "debug"
            self.overlay = None
        self.redraw()

    def close_debug(self):
        """Return to the exact menu or game overlay from which debug was opened."""
        if self.debug_return_screen == "game":
            self.screen = "game"
            self.overlay = self.debug_return_overlay
        else:
            self.screen = self.debug_return_screen
            self.overlay = None
        self.redraw()

    def change_debug_chapter(self, amount):
        self.debug_target_chapter = int(clamp(self.debug_target_chapter + amount, 0, 9))
        self.redraw()

    def change_debug_score(self, amount):
        self.debug_score = int(clamp(self.debug_score + amount, 0, 100))
        self.redraw()

    def debug_set_score(self, score):
        self.debug_score = int(clamp(score, 0, 100))
        self.redraw()

    def debug_jump_to_chapter(self):
        # Debug jumps intentionally unlock the selected chapter for testing.
        target = int(clamp(self.debug_target_chapter, 0, 9))
        self.unlocked = max(self.unlocked, target)
        self.start_game(target)

    def debug_skip_to_report(self):
        if self.screen != "game":
            return
        self.debug_score_override = True
        self.report_score = int(clamp(self.debug_score, 0, 100))
        self.end_grade = self.ranks(self.report_score)
        self.execute_finale()

    def draw_debug_panel(self):
        self.ui_modal(title="DEVELOPER TEST PANEL")
        self.text(180, 220, "CHAPTER JUMP", 14, C["gold"])
        self.text(180, 260, f"CHAPTER {roman(self.debug_target_chapter)} — {CHAPTERS[self.debug_target_chapter]['title']}",
                  20, C["ivory"], serif=True)
        self.button(180, 310, 70, 42, "−", lambda: self.change_debug_chapter(-1), size=20)
        self.button(264, 310, 70, 42, "+", lambda: self.change_debug_chapter(1), size=20)
        self.button(354, 310, 300, 42, "JUMP TO SELECTED CHAPTER", self.debug_jump_to_chapter, primary=True,
                    size=11)

        self.text(180, 400, "TEST SCORE", 14, C["gold"])
        self.text(180, 438, f"{self.debug_score:03d} / 100", 28, C["ivory"], serif=True)
        self.text(180, 468, f"RANK PREVIEW: {self.ranks(self.debug_score)}", 12, C["cyan"], bold=True)
        self.button(180, 505, 62, 42, "−10", lambda: self.change_debug_score(-10))
        self.button(252, 505, 62, 42, "−1", lambda: self.change_debug_score(-1))
        self.button(324, 505, 62, 42, "+1", lambda: self.change_debug_score(1))
        self.button(396, 505, 62, 42, "+10", lambda: self.change_debug_score(10))
        self.button(468, 505, 82, 42, "0", lambda: self.debug_set_score(0))
        self.button(560, 505, 94, 42, "100", lambda: self.debug_set_score(100))
        self.text(180, 568, "The selected score is used when you skip a chapter to its case report.",
                  11, C["muted"], width=650)

        if self.debug_return_screen == "game":
            self.button(180, 635, 330, 48, "SKIP CURRENT CHAPTER TO REPORT", self.debug_skip_to_report,
                        primary=True, size=11)
        self.button(1040, 635, 170, 48, "CLOSE", self.close_debug)

    def draw_pause(self):
        self.ui_modal(title="THE INVESTIGATION PAUSES")
        self.text(181, 235, "The night is not going anywhere.", 23, C["ivory"], serif=True)
        self.button(188, 350, 333, 53, "RESUME INVESTIGATION", self.close_overlay, primary=True)
        self.button(188, 422, 333, 53, "RETURN TO TITLE", self.return_menu)
        self.button(188, 495, 333, 53, "CONTROLS", lambda: self.open_screen("help"))

    def chapter_select(self):
        self.overlay = None
        self.save()
        self.open_screen("select")

    def next_chapter(self):
        self.overlay = None
        self.save()
        if self.chapter >= 9:
            self.return_menu()
        else:
            self.start_game(self.chapter + 1)

    def go_back(self):
        """One obvious, consistent route to the previous context."""
        if self.screen == "debug":
            self.close_debug()
            return
        if self.overlay == "debug":
            self.close_debug()
            return
        if self.overlay == "room_transition":
            return
        if self.screen == "game":
            if self.overlay is None:
                self.overlay = "pause"
            elif self.overlay == "deduce" or self.overlay == "deduce_result":
                self.overlay = "board"
                self.deduction_chosen = None
            elif self.overlay == "cinematic":
                if self.cutscene_step > 0:
                    self.cutscene_step -= 1
                else:
                    self.return_menu()
                    return
            elif self.overlay == "dialogue":
                if self.dialogue_step > 0:
                    self.dialogue_step -= 1
                else:
                    self.overlay = None
            elif self.overlay == "confront":
                if self.confront_step > 0:
                    self.confront_step -= 1
                else:
                    self.overlay = None
            elif self.overlay == "chapter_end":
                self.chapter_select()
                return
            elif self.overlay == "caught":
                self.reset_after_capture()
                return
            elif self.overlay == "pause":
                self.overlay = None
            else:
                self.overlay = None
        elif self.screen == "profile":
            self.profile_return()
            return
        elif self.screen in {"help", "select"}:
            previous = self.screen_return
            if previous and previous[0] == "game":
                self.screen, self.overlay = previous
                self.screen_return = None
            else:
                self.return_menu()
                return
        self.redraw()

    def open_overlay(self, name):
        sfx("overlay_open")
        self.overlay = name
        self.redraw()

    def close_overlay(self):
        sfx("overlay_close")
        self.overlay = None
        self.deduction_chosen = None
        self.redraw()

    # -------- interaction / movement / stealth --------
    def nearest_object(self):
        if self.screen != "game" or self.overlay:
            return None
        here = (self.player.x, self.player.y)
        possibilities = []
        for item in self.world.objects:
            if item.secret and int(item.id.split("_")[-1]) in self.notes:
                continue
            dd = distance(here, (item.x, item.y))
            if dd <= 42:
                if item.id == "uniform":
                    display = "Browse the clothes on the coatstand"
                elif item.id.startswith("clue") and int(item.id[-1]) in self.seen:
                    display = "Study " + item.name.lower() + " again"
                else:
                    display = "Examine " + item.name.lower()
                possibilities.append((dd, item.id, (item.x, item.y), display))
        dd = distance(here, self.world.witness.feet)
        if self.room_index == 0 and dd <= 33:
            possibilities.append((dd, "witness", self.world.witness.feet, "Speak quietly with the witness"))
        dd = distance(here, self.world.killer.feet)
        if self.room_index == 1 and dd <= 37:
            if len(self.solved) == 3 and len(self.seen) == 3:
                display = "Confront the person by the wall"
            else:
                display = "A familiar face. Something about the story still feels wrong"
            possibilities.append((dd, "killer", self.world.killer.feet, display))
        for j, spot in enumerate(self.world.hide_positions):
            dd = distance(here, spot)
            if dd <= 23:
                possibilities.append((dd, f"hide_{j}", spot, "Leave cover" if self.hidden else "Slip into cover"))
        for j, (x, y, radius) in enumerate(self.world.blend_zones):
            dd = distance(here, (x, y))
            if dd <= radius:
                possibilities.append((dd + 13, f"blend_{j}", (x, y),
                                      "Leave the conversation" if self.blending else "Blend into the conversation"))
        if not possibilities:
            return None
        possibilities.sort(key=lambda item: item[0])
        _, key, xy, display = possibilities[0]
        return key, xy, display

    def interact(self):
        portal = self.portal_nearby()
        near = self.nearest_object()
        # A nearby exit must not steal the E key from a clue or witness that
        # the player is standing directly beside. Prefer the closest actual
        # object, with a small bias toward physical evidence.
        if portal is not None and near is not None:
            item_distance = distance(self.player.feet, near[1])
            door_distance = distance(self.player.feet, portal[1])
            if item_distance + 8 < door_distance:
                portal = None
        if portal is not None:
            self.use_portal(portal[0])
            return
        if near is None:
            self.toast("Nothing catches your eye from here. A closer look might reveal more.")
            return
        key, xy, display = near
        if key in {"archive_secret", "private_file"}:
            # Kept apart from the margin notes' ids (0-2), which are hidden
            # once their number appears in self.notes.
            note_id = 4 if key == "archive_secret" else 3
            self.notes.add(note_id)
            self.infiltration_uncovered = self.infiltration_uncovered or key == "private_file"
            self.show_caption(SECRET_REVEALS[self.chapter] if key == "private_file" else
                              "Beneath the bricks, a record survives that the Lantern meant to erase.")
            self.save()
            self.redraw()
            return
        if key == "uniform":
            self.overlay = "wardrobe"
            self.redraw()
            return
        if key.startswith("clue_"):
            idx = int(key[-1])
            was_new = idx not in self.seen
            self.seen.add(idx)
            if was_new:
                sfx("clue_found")
                self.discovery_index = idx
                self.overlay = "evidence"
                self.show_caption(CHAPTERS[self.chapter]["cinematic"][5 + idx])
            else:
                self.toast("You already studied this object. Your field journal has the details.")
            self.save()
        elif key.startswith("optional_"):
            idx = int(key[-1])
            self.notes.add(idx)
            self.show_caption(CHAPTERS[self.chapter]["cinematic"][idx + 8])
            self.toast("A small detail slips into the margins of your case notes.")
            self.save()
        elif key == "witness":
            self.dialogue_step = 0
            self.overlay = "dialogue"
        elif key == "killer":
            if len(self.solved) < 3 or len(self.seen) < 3 or not self.witness_spoken:
                self.toast("The accusation needs the three proofs and a recorded witness statement.")
            elif self.exposure > 38 or any(g.mode == "pursue" for g in self.watchmen):
                self.toast("You are being watched. Lose the watchman before you approach.")
            else:
                self.confront_step = 0
                self.overlay = "confront"
        elif key.startswith("hide_"):
            self.toggle_hide()
        elif key.startswith("blend_"):
            self.toggle_blend()
        self.redraw()

    def draw_wardrobe(self):
        self.ui_modal(title="A SECOND IDENTITY")
        self.frame_box(159, 188, 484, 642, fill="#172c40")
        self.text(187, 213, "AN UNATTENDED COATSTAND", 16, C["gold"], serif=True)
        self.text(188, 266, wrapped(COVER_LINES[self.chapter], 31), 14, C["ivory"], width=278)
        self.text(188, 441, "A good disguise opens doors. A bad performance draws attention.", 12, C["cyan"], width=269)
        self.frame_box(518, 190, 1248, 642, fill="#0b2034")
        staff, guest = COVER_IDENTITIES[self.chapter]
        self.text(552, 220, "CHOOSE A COVER", 22, C["ivory"], serif=True)
        self.text(552, 278, staff, 17, C["gold"], serif=True)
        self.text(552, 310,
                  "Allows entry to staff rooms, but senior guards recognize unfamiliar faces. Avoid close inspection.",
                  13, C["muted"], width=616)
        self.button(555, 368, 275, 42, "WEAR STAFF UNIFORM", lambda: self.equip_disguise("staff"), primary=True)
        self.text(552, 451, guest, 17, C["gold"], serif=True)
        self.text(552, 485, "Believable among guests and witnesses. It does not grant staff access.", 13, C["muted"],
                  width=616)
        self.button(555, 544, 275, 42, "CHANGE INTO GUEST", lambda: self.equip_disguise("guest"))
        self.button(856, 544, 264, 42, "RETURN TO YOUR CLOTHES", lambda: self.equip_disguise(None))
        self.text(166, 679, "The uniform helps only while your cover remains believable.", 12, C["cyan"])
        self.button(1040, 688, 167, 42, "LEAVE", self.close_overlay)

    def equip_disguise(self, kind):
        self.disguise = kind
        self.scrutiny = 0.0
        self.cover_blown = False
        self.hidden = False
        self.blending = False
        self.overlay = None
        if kind is None:
            self.show_caption("You fold the borrowed clothing away. The room feels less forgiving.")
        else:
            name = COVER_IDENTITIES[self.chapter][0 if kind == "staff" else 1]
            self.show_caption(f"You become the {name.lower()}. Keep a steady pace: a uniform is not a personality.")
        self.save()
        self.redraw()

    def restricted(self, x, y):
        # Security is confined to the private wing, not a hidden invisible
        # rectangle arbitrarily painted over the public investigation.
        return self.security_zone((x, y))

    def authorized_in_office(self):
        return self.disguise == "staff" and not self.cover_blown

    def try_drop_coin(self):
        if self.coins <= 0:
            self.toast("Your pockets are empty. Distraction is no longer an option.")
            return
        direction = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}[self.player.facing]
        target = (clamp(self.player.x + direction[0] * 56, 28, WORLD_W - 28),
                  clamp(self.player.y + direction[1] * 56, 43, WORLD_H - 25))
        self.coins -= 1
        sfx("coin")
        sfx("coin_bounce")
        self.decoy = target
        self.decoy_expire = self.time_alive + 1.35
        for g in self.watchmen:
            if distance(g.actor.feet, target) < 130:
                g.last_known = target
                g.mode = "investigate"
                g.linger = 4.0
                g.notice = min(100, g.notice + 8)
        self.show_caption(DECOY_LINES[self.chapter])
        self.save()
        self.redraw()

    def update_cover(self, dt):
        if self.disguise is None or self.cover_blown:
            self.scrutiny = max(0, self.scrutiny - dt * 20)
            return
        enforcers = [g for g in self.watchmen if g.rank == "enforcer" and
                     self.security_zone(self.player.feet) and
                     distance(g.actor.feet, self.player.feet) < 35 and
                     self.guard_can_see(g)]
        self.scrutiny = min(100, self.scrutiny + dt * 35) if enforcers else max(0, self.scrutiny - dt * 17)
        if self.scrutiny >= 100:
            self.cover_blown = True
            for g in enforcers:
                g.notice = max(g.notice, 65)
                g.mode = "investigate"
                g.last_known = self.player.feet
                g.linger = 4
            self.show_caption("A senior watchman has recognized that the uniform belongs to someone else.")
            self.toast("COVER COMPROMISED")
            self.save()

    def toggle_hide(self):
        near = min((distance(self.player.feet, pos) for pos in self.world.hide_positions), default=999)
        if self.hidden:
            sfx("leave_hide")
            self.hidden = False
            self.toast("You leave cover. The room feels far less forgiving.")
        elif near <= 26:
            sfx("enter_hide")
            self.hidden = True
            self.blending = False
            self.click_destination = None
            self.player.vx = self.player.vy = 0
            self.toast("You disappear into the dark edge of the room.")
        else:
            self.toast("Find deep shadow, a cabinet, or the shelter of furniture first.")

    def toggle_blend(self):
        in_crowd = any(distance(self.player.feet, (x, y)) < radius for x, y, radius in self.world.blend_zones)
        if self.blending:
            sfx("leave_blend")
            self.blending = False
            self.toast("You drift away from the conversation.")
        elif in_crowd:
            sfx("enter_blend")
            self.blending = True
            self.hidden = False
            self.running = False
            self.toast("You lower your head and become another indistinct guest.")
        else:
            self.toast("You need people nearby to blend in. Find a small group.")

    def obstructed(self, x, y, radius=4):
        for x1, y1, x2, y2 in self.world.collisions:
            if x + radius > x1 and x - radius < x2 and y + radius > y1 and y - radius < y2:
                return True
        return False

    def move_agent(self, agent, vx, vy, dt):
        # Swept substeps prevent sprinting through narrow objects during a
        # temporary frame drop. X/Y resolution gives smooth wall sliding.
        pieces = max(1, math.ceil(max(abs(vx * dt), abs(vy * dt)) / 3.0))
        for _ in range(pieces):
            nx = agent.x + vx * dt / pieces
            if not self.obstructed(nx, agent.y):
                agent.x = nx
            else:
                agent.vx = 0
            ny = agent.y + vy * dt / pieces
            if not self.obstructed(agent.x, ny):
                agent.y = ny
            else:
                agent.vy = 0
        agent.x = clamp(agent.x, 25, WORLD_W - 25)
        agent.y = clamp(agent.y, 46, WORLD_H - 25)

    def update_player(self, dt):
        x = float("right" in self.held or "d" in self.held) - float("left" in self.held or "a" in self.held)
        y = float("down" in self.held or "s" in self.held) - float("up" in self.held or "w" in self.held)
        if abs(x) > 0 or abs(y) > 0:
            self.click_destination = None
            self.click_path = []
        elif self.click_destination is not None:
            while self.click_path and distance(self.player.feet, self.click_path[0]) < 7:
                self.click_path.pop(0)
            if self.click_path:
                dx = self.click_path[0][0] - self.player.x
                dy = self.click_path[0][1] - self.player.y
                x, y = unit(dx, dy)
            else:
                self.click_destination = None
        x, y = unit(x, y)
        self.running = False  # No sprint: consistent walking gives guards readable patrol timing.
        self.crouched = "control_l" in self.held or "control_r" in self.held or "control" in self.held
        if self.blending:
            self.running = False
        if self.hidden and (abs(x) + abs(y)) > 0.05:
            self.hidden = False
        speed = 55.0
        if self.crouched:
            speed = 28.0
        if self.blending:
            speed = 30.0
        # Frames-per-second independent acceleration / deceleration.
        response = 1 - math.exp(-14.0 * dt) if (x or y) else 1 - math.exp(-19.5 * dt)
        self.player.vx = lerp(self.player.vx, x * speed, response)
        self.player.vy = lerp(self.player.vy, y * speed, response)
        if abs(self.player.vx) < .25:
            self.player.vx = 0
        if abs(self.player.vy) < .25:
            self.player.vy = 0
        if self.hidden:
            self.player.vx = self.player.vy = 0
        self.move_agent(self.player, self.player.vx, self.player.vy, dt)
        # Trespassing is a SECURITY RULE, not an invisible wall. Anyone can
        # enter; only a suitable disguise makes it legitimate. Crouching still
        # needs cover and timing. Private records are optional lore.
        if self.restricted(self.player.x, self.player.y) and not self.authorized_in_office():
            if self.time_alive - self.restricted_warning_at > 7.0:
                self.restricted_warning_at = self.time_alive
                self.show_caption(
                    "The staff office is restricted. You can enter, but security will challenge an unknown face.")
        if self.restricted(self.player.x, self.player.y) and not self.infiltration_uncovered:
            if (self.disguise == "staff" and not self.cover_blown) or self.hidden or self.exposure < 30:
                self.infiltration_uncovered = True
                self.show_caption(SECRET_REVEALS[self.chapter], duration=7.0)
                self.save()
        moving = math.hypot(self.player.vx, self.player.vy) > 6
        self.player.moving = moving
        if moving:
            self.player.frame += dt * (6 if not self.crouched else 3.8)
            if abs(self.player.vx) > abs(self.player.vy):
                self.player.facing = "right" if self.player.vx > 0 else "left"
            else:
                self.player.facing = "down" if self.player.vy > 0 else "up"
        else:
            self.player.frame = 0
        if self.blending:
            if not any(distance(self.player.feet, (cx, cy)) < cr + 10 for cx, cy, cr in self.world.blend_zones):
                self.blending = False
                self.show_caption("You have wandered out of the crowd and into the open.")
        # Camera dead zone: let the detective walk within the middle of the
        # room before shifting the expensive full-room bitmap. This is also
        # more readable when examining nearby furniture and evidence.
        target_x, target_y = self.cam_x, self.cam_y
        left, right = self.cam_x + VISIBLE_W * .37, self.cam_x + VISIBLE_W * .63
        top, bottom = self.cam_y + VISIBLE_H * .35, self.cam_y + VISIBLE_H * .65
        if self.player.x < left:
            target_x = self.player.x - VISIBLE_W * .37
        elif self.player.x > right:
            target_x = self.player.x - VISIBLE_W * .63
        if self.player.y < top:
            target_y = self.player.y - VISIBLE_H * .35
        elif self.player.y > bottom:
            target_y = self.player.y - VISIBLE_H * .65
        target_x = clamp(target_x, 0, WORLD_W - VISIBLE_W)
        target_y = clamp(target_y, 0, WORLD_H - VISIBLE_H)
        ca = 1 - math.exp(-8.4 * dt)
        self.cam_x = lerp(self.cam_x, target_x, ca)
        self.cam_y = lerp(self.cam_y, target_y, ca)

    def sight_blocked(self, p1, p2):
        # Samples the segment against the map's solid furniture/walls; makes
        # cover useful rather than a cosmetic 'H' button.
        steps = max(2, int(distance(p1, p2) / 5))
        for i in range(1, steps):
            alpha = i / steps
            x = lerp(p1[0], p2[0], alpha)
            y = lerp(p1[1], p2[1], alpha)
            if self.obstructed(x, y, 1):
                return True
        return False

    def security_zone(self, xy):
        # Past the vestibule partition (x 112-122) in the private wing.
        return self.room_index == 1 and xy[0] > 120

    def suspicious_to(self, watchman):
        if not self.security_zone(self.player.feet):
            return False
        if self.disguise == "staff" and not self.cover_blown:
            # Only the more perceptive senior guard detects stolen uniforms.
            return watchman.rank == "enforcer" or self.crouched
        return True

    def guard_can_see(self, watchman=None):
        g = watchman or self.watchmen[0]
        a = g.actor
        dist = distance(a.feet, self.player.feet)
        if dist > (112 if g.rank == "enforcer" else 96):
            return False
        # Hiding is not a universal invisibility cheat: contact still reveals.
        if self.hidden and dist > 13:
            return False
        if self.blending and dist > 18 and not self.restricted(*self.player.feet):
            return False
        facing = {"up": (0, -1), "down": (0, 1),
                  "left": (-1, 0), "right": (1, 0)}[a.facing]
        look = unit(self.player.x - a.x, self.player.y - a.y)
        threshold = .61 if g.rank == "security" else .54
        if facing[0] * look[0] + facing[1] * look[1] < threshold and dist > 15:
            return False
        return not self.sight_blocked(a.feet, self.player.feet)

    def guard_hears(self, watchman=None):
        g = watchman or self.watchmen[0]
        if self.hidden or not self.player.moving or not self.security_zone(self.player.feet):
            return False
        d = distance(g.actor.feet, self.player.feet)
        # Slow steps are quieter, NOT unseen. Guards investigate footsteps,
        # then look where they think the player went.
        return d < (13 if self.crouched else 47)

    def guard_move(self, g, goal, speed, dt):
        g.repath -= dt
        if (g.path_goal is None or distance(goal, g.path_goal) > 12 or
                g.repath <= 0 or not g.path):
            g.path = self.nav.path(g.actor.feet, goal)
            g.path_goal = goal
            g.repath = .55 if g.mode == "pursue" else 1.1
        while g.path and distance(g.actor.feet, g.path[0]) < 6.5:
            g.path.pop(0)
        node = g.path[0] if g.path else goal
        dx, dy = node[0] - g.actor.x, node[1] - g.actor.y
        vx, vy = unit(dx, dy)
        if abs(dx) > abs(dy):
            g.actor.facing = "right" if dx > 0 else "left"
        elif abs(dy) > 1:
            g.actor.facing = "down" if dy > 0 else "up"
        self.move_agent(g.actor, vx * speed, vy * speed, dt)
        g.actor.frame += dt * 5

    def update_guard(self, dt):
        """Independent patrol / curious / investigate / search / pursuit AI.

        Enforcers challenge even uniformed strangers. A guard in public space
        is just a person: seeing a detective beside the public evidence does
        not start a chase. Every alert needs vision or believable sound.
        """
        self.update_cover(dt)
        any_alert = 0.0
        caught_by_contact = False
        for g in self.watchmen:
            visual = self.guard_can_see(g)
            illegal = self.suspicious_to(g)
            audible = self.guard_hears(g)
            if visual and illegal:
                # Crouching is more suspicious if visible, never protective.
                rate = (64 if self.crouched else 44) * (1.25 if g.rank == "enforcer" else 1)
                g.notice = min(100, g.notice + dt * rate)
                g.last_known = self.player.feet
                g.linger = 4.8
                if g.notice > 67:
                    g.mode = "pursue"
                elif g.notice > 17:
                    g.mode = "curious"
            else:
                g.notice = max(0, g.notice - dt * (13 if g.mode == "search" else 22))
                if audible and g.mode not in {"pursue", "investigate"}:
                    g.last_known = self.player.feet
                    g.mode = "investigate"
                    g.linger = 3.7
            # Players can read the state in animation: patrols move steadily,
            # guards pause to inspect, search turns are slower, pursuit fast.
            if g.mode == "pursue":
                if visual and illegal:
                    g.last_known = self.player.feet
                    g.linger = 4.0
                g.linger -= dt
                if g.last_known:
                    self.guard_move(g, g.last_known, 69, dt)
                if g.linger <= 0:
                    g.mode, g.linger = "search", 4.0
            elif g.mode in {"curious", "investigate", "search"}:
                g.linger -= dt
                if g.last_known and distance(g.actor.feet, g.last_known) > 9:
                    self.guard_move(g, g.last_known, 31, dt)
                else:
                    g.scan_clock += dt
                    if g.scan_clock > .65:
                        g.scan_clock = 0
                        faces = ["right", "down", "left", "up"]
                        g.search_turns += 1
                        g.actor.facing = faces[(g.search_turns + g.waypoint) % 4]
                if g.linger <= 0 and g.notice < 10:
                    g.mode, g.last_known = "patrol", None
            else:
                if not g.route:
                    continue
                goal = g.route[g.waypoint]
                if distance(g.actor.feet, goal) < 7:
                    # A short observable pause at each waypoint gives timing.
                    g.linger += dt
                    if g.linger >= .65:
                        g.waypoint = (g.waypoint + 1) % len(g.route)
                        g.linger = 0
                    else:
                        g.actor.facing = ("right", "down", "left", "up")[g.waypoint % 4]
                else:
                    self.guard_move(g, goal, 22 if g.rank == "enforcer" else 25, dt)
            any_alert = max(any_alert, g.notice)
            if g.mode == "pursue" and distance(g.actor.feet, self.player.feet) < 12:
                caught_by_contact = True
        self.exposure = max(0.0, min(100.0, max(any_alert, self.exposure - dt * 28)))
        if caught_by_contact:
            self.exposure = 100.0
        self.peak_exposure = max(self.peak_exposure, self.exposure)
        if self.exposure >= 100:
            if self.overlay != "caught":
                sfx("caught")
                self.spotted_count += 1
                self.save()
            self.overlay = "caught"
            self.click_destination = None
            self.clear_held()
            # update() only redraws while no overlay is open, so draw the
            # capture screen now rather than freezing on the last frame.
            self.redraw()

    def reset_after_capture(self):
        self.player.x, self.player.y = find_nearest_open(self.world, self.world.start)
        self.player.vx = self.player.vy = 0
        for g in self.watchmen:
            if not g.route:
                continue
            g.actor.x, g.actor.y = g.route[0]
            g.mode = "patrol"
            g.notice = 0
            g.last_known = None
            g.linger = g.repath = 0
            g.path.clear()
        self.exposure = 0
        self.hidden = self.blending = False
        self.cover_blown = bool(self.disguise)
        self.scrutiny = 0
        self.overlay = None
        self.save()
        self.redraw()

    # -------- keyboard and pointer --------
    def clear_held(self):
        self.held.clear()
        for job in list(self.release_jobs.values()):
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
        self.release_jobs.clear()

    def key_down(self, event):
        k = event.keysym.lower()
        if k in self.release_jobs:
            try:
                self.root.after_cancel(self.release_jobs.pop(k))
            except Exception:
                pass
        # Keep the Entry entirely in control of its own typed text.
        if self.screen == "profile" and self.name_entry is not None and self.root.focus_get() == self.name_entry:
            if k == "return":
                self.confirm_profile()
            return
        # Backslash opens/closes developer tools from any non-text-entry screen.
        if k in {"backslash", "bar"} or event.char == "\\":
            if self.screen == "debug" or (self.screen == "game" and self.overlay == "debug"):
                self.close_debug()
            else:
                self.open_debug()
            return
        if self.screen == "game" and self.overlay is None:
            if k in {"w", "a", "s", "d", "up", "down", "left", "right", "control_l", "control_r"}:
                self.held.add(k)
                return
            if k == "e":
                self.interact()
            elif k == "j":
                self.open_overlay("journal")
            elif k in {"tab", "i"}:
                self.open_overlay("board")
            elif k == "h":
                self.toggle_hide()
            elif k == "b":
                self.toggle_blend()
            elif k == "v":  # Woody's ppr
                self.focus = True
            elif k == "q":
                self.try_drop_coin()
            elif k == "n":
                if self.chapter == 0:
                    self.show_caption(get_hint(self.seen))
            elif k == "escape":
                self.go_back()
            elif k == "space":
                self.interact()  # Woodys ppr end
        elif self.screen == "game" and self.overlay is not None:
            if k == "escape":
                self.go_back()
            elif k in {"space", "return"}:
                if self.overlay == "cinematic":
                    self.advance_cinematic()
                elif self.overlay == "dialogue":
                    self.advance_dialogue()
                elif self.overlay == "confront" and self.confront_step < 4:
                    self.advance_confrontation()
                elif self.overlay == "evidence":
                    self.close_overlay()
                elif self.overlay == "deduce_result":
                    self.open_overlay("board")
            elif self.overlay == "deduce" and k in {"1", "2", "3"}:
                self.answer_deduction(int(k) - 1)
        elif k == "escape" and self.screen in {"select", "help", "profile"}:
            self.go_back()

    def key_up(self, event):
        k = event.keysym.lower()
        if k == "v":
            self.focus = False
        # Windows/Linux OS key repeat fires Release/Press pairs between actual
        # releases; a small grace period avoids stuttering while keys are held.
        if k in self.held:
            def remove(key=k):
                self.held.discard(key)
                self.release_jobs.pop(key, None)

            self.release_jobs[k] = self.root.after(35, remove)

    def motion(self, event):
        self.mouse = (event.x, event.y)

    def click(self, event):
        xy = (event.x, event.y)
        for (x1, y1, x2, y2), callback in reversed(self.buttons):
            if x1 <= xy[0] <= x2 and y1 <= xy[1] <= y2:
                callback()
                return
        # Optional direct walking by pointing to a position on the map.
        if self.screen == "game" and self.overlay is None:
            if VIEW_X <= xy[0] <= VIEW_X + VIEW_W and VIEW_Y <= xy[1] <= VIEW_Y + VIEW_H:
                self.click_destination = self.screen_to_world(*xy)
                self.click_path = self.nav.path(self.player.feet, self.click_destination)
                if not self.click_path:
                    self.click_destination = None

    def wheel(self, event):
        if self.overlay == "journal":
            self.ui_scroll = max(0, self.ui_scroll + (-1 if event.delta > 0 else 1))
            self.redraw()

    # -------- scheduled animation and rendering --------
    def update(self):
        now = time.perf_counter()
        try:
            self.step(now)
        finally:
            # Always schedule the next frame: an error in one tick must not
            # silently stop the game loop. Tk still reports the exception.
            try:
                self.root.after(self.next_frame_delay(now), self.update)
            except tk.TclError:
                pass  # The window has been closed.

    def step(self, now):
        dt = clamp(now - self.last_tick, 0.001, 0.085)
        self.last_tick = now
        self.time_alive += dt
        self.tick_count += 1
        if self.toast_timer > 0:
            self.toast_timer = max(0, self.toast_timer - dt)
        if self.alert_caption_timer > 0:
            self.alert_caption_timer = max(0, self.alert_caption_timer - dt)
        if self.screen == "game" and self.overlay == "room_transition":
            # Use elapsed wall time: a slower computer must not stretch a
            # 1.7-second passage transition into several seconds.
            self.transition_time = time.perf_counter() - self.transition_started_at
            if self.transition_time >= self.transition_duration * 0.57 and not self.transition_switched:
                self.transition_switched = True
                # switch_room() redraws the scene, transition overlay included.
                self.switch_room(self.transition_to)
            if self.transition_time >= self.transition_duration:
                self.canvas.delete("room_transition_fx")
                self.overlay = None
                self.transition_to = None
                self.redraw()
            elif self.tick_count % 2 == 0:
                self.draw_room_transition()
        if self.screen == "game" and self.overlay is None:
            self.update_player(dt)
            self.update_guard(dt)
            if self.tick_count % 80 == 0:
                self.cache_progress()
        # Menu rain and game movement animate continuously, while dialogs stop
        # the world so the player can actually read at their own pace.
        if self.screen == "game" and self.overlay is None:
            try:
                self.redraw()
            except (tk.TclError, ValueError, IndexError, StopIteration):
                traceback.print_exc()
                self.toast("A scene error was recovered. Your case progress is intact.")
                self._scene_ready = False
        elif self.screen in {"menu", "profile"}:
            # Title rain and the profile's walking preview, at menu cadence.
            self.redraw()

    def next_frame_delay(self, now):
        # Measure how long this frame actually took and subtract that work
        # from the 30-fps budget. The old loop waited a whole frame AFTER
        # drawing, causing avoidable visible slowdowns on slower machines.
        elapsed_ms = (time.perf_counter() - now) * 1000.0
        budget_ms = STEP_INTERVAL * 1000.0
        target = max(1, round(budget_ms - elapsed_ms))
        if self.screen != "game":
            target = 90  # Menus animate gently; don't burn CPU offscreen.
        elif self.overlay not in (None, "room_transition"):
            target = 55  # Paused dialogue / evidence doesn't need 30 updates.
        return target

    def redraw(self):
        if not self.canvas.winfo_exists():
            return
        if self.screen == "game":
            self.draw_game_scene()
        else:
            self.canvas.delete("all")
            self.buttons.clear()
            if self.screen == "menu":
                self.draw_title()
            elif self.screen == "select":
                self.draw_chapter_select()
            elif self.screen == "profile":
                self.draw_profile()
            elif self.screen == "help":
                self.draw_help()
            elif self.screen == "debug":
                self.draw_debug_panel()

# Jack's ppr
    def ranks(self, score):
        if score >= 95:
            return "S"
        if score >= 85:
            return "A"
        if score >= 70:
            return "B"
        if score >= 55:
            return "C"
        return "D"


def main():
    root = tk.Tk()
    BlackwellGame(root)
    root.mainloop()


if __name__ == "__main__":
    main()

