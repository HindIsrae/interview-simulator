#!/usr/bin/env python
# interview_simulator.py  –  CPU-only, PyAudio-free, gesture-aware
import json, sys, queue, subprocess, time, textwrap
from pathlib import Path

import cv2
import numpy as np
import sounddevice as sd
from vosk import Model, KaldiRecognizer
import mediapipe as mp
import yaml

# ───────── settings ───────── #
OLLAMA_MODEL = "mistral"        # any CPU-friendly model pulled with `ollama`
SAMPLE_RATE  = 16_000           # Vosk model sample-rate
CHUNK_SEC    = 0.25             # audio chunk size
MAX_ANS_SEC  = 60               # stop recording after N s

VOSK_PATH = "models/vosk-model-small-en-us-0.15"
FALLBACK_YAML = Path("resources/generic_questions.yaml")  # legacy template

# ───────── question loaders ───────── #
def load_questions_from_json(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):           # plain list
        return data
    # schema from question_generator.py  (has categories)
    merged = (
        data.get("Static", []) +
        data.get("Technical", []) +
        data.get("Behavioral", []) +
        data.get("CultureFit", [])
    )
    return merged

def load_questions_from_yaml(resume_json: dict) -> list[str]:
    tmpl = yaml.safe_load(FALLBACK_YAML.read_text(encoding="utf-8"))
    questions = []
    for section, qlist in tmpl.items():
        block = resume_json.get(section, {})
        for q in qlist:
            rendered = q
            if isinstance(block, dict):
                for k, v in block.items():
                    rendered = rendered.replace(f"{{{{ {k} }}}}", str(v)[:100])
            questions.append(rendered)
    return questions

# ───────── audio capture (sounddevice + Vosk) ───────── #
def record_answer(rec: KaldiRecognizer) -> str:
    q = queue.Queue()
    def callback(indata, frames, time_info, status): q.put(bytes(indata))

    with sd.RawInputStream(samplerate=SAMPLE_RATE,
                           blocksize=int(SAMPLE_RATE * CHUNK_SEC),
                           dtype="int16",
                           channels=1,
                           callback=callback):
        start = time.time()
        while True:
            data = q.get()
            if rec.AcceptWaveform(data): break
            if time.time() - start > MAX_ANS_SEC: break

    j = rec.Result() or rec.FinalResult()
    return json.loads(j)["text"]

# ───────── answer evaluation via Ollama ───────── #
def evaluate_answer(question: str, answer: str) -> str:
    prompt = textwrap.dedent(f"""
        You are an interview coach.
        Question: {question}
        Candidate answer: {answer}
        Give a short (≤ 40 words) evaluation focusing on clarity, relevance and depth.
    """).strip()
    proc = subprocess.run(
        ["ollama", "run", OLLAMA_MODEL],
        input=prompt,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.stdout.strip()

# ───────── gesture helper (MediaPipe FaceMesh) ───────── #
mp_face = mp.solutions.face_mesh.FaceMesh(
    static_image_mode=False,
    max_num_faces=1,
    refine_landmarks=True
)

def analyse_frame(frame):
    """Return very simple metrics (eye-contact, mouth_open)."""
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    res = mp_face.process(rgb)
    if not res.multi_face_landmarks: return {}
    lm = res.multi_face_landmarks[0].landmark
    eye_dist = abs(lm[33].x - lm[263].x)   # left–right iris centres
    mouth_open = (lm[13].y - lm[14].y) > 0.02
    return {"eye_distance": eye_dist, "mouth_open": mouth_open}

# ───────── main driver ───────── #
def run_interview(q_source: Path):
    # 1) decide where questions come from
    questions = (load_questions_from_json(q_source)
                 if q_source.suffix == ".json"
                 else load_questions_from_yaml(json.loads(q_source.read_text())))
    if not questions:
        sys.exit("❌  No questions found.")

    # 2) initialise Vosk + webcam
    rec = KaldiRecognizer(Model(VOSK_PATH), SAMPLE_RATE)
    cam = cv2.VideoCapture(0)

    transcript, gestures = [], []
    for idx, q in enumerate(questions, start=1):
        # overlay question until SPACE
        while True:
            ok, frm = cam.read()
            if not ok: raise RuntimeError("Webcam error.")
            ov = frm.copy()
            cv2.putText(ov, f"Q{idx}/{len(questions)}: {q}", (30,40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0,255,0), 2)
            cv2.imshow("Interview", ov)
            if cv2.waitKey(30) & 0xFF == ord(" "): break

        answer = record_answer(rec)
        feedback = evaluate_answer(q, answer)

        transcript.append({"question": q, "answer": answer, "feedback": feedback})
        gestures.append(analyse_frame(frm))

        # flash confirmation
        for _ in range(20):
            ok, fr = cam.read()
            cv2.putText(fr, "✔ recorded", (30,40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,0), 2)
            cv2.imshow("Interview", fr)
            cv2.waitKey(30)

    cam.release(); cv2.destroyAllWindows()

    # 3) persist artefacts
    Path("transcript.json").write_text(json.dumps(transcript,indent=2,ensure_ascii=False))
    Path("gestures.json").write_text(json.dumps(gestures, indent=2))
    print("✅  Saved transcript.json & gestures.json")

# ───────── CLI ───────── #
if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage:\n  python interview_simulator.py  questions.json\n"
                 "  -or-\n  python interview_simulator.py  resume_parsed.json")
    src = Path(sys.argv[1])
    if not src.is_file():
        sys.exit("❌  File not found.")
    run_interview(src)
