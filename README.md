cat > README.md <<'EOF'
# Offline Interview Suite

> **TL;DR** Parse a résumé → parse a job offer → auto-generate tailored questions → run a webcam + mic interview (speech-to-text, facial-gesture capture, live LLM feedback) → produce a Markdown report.  
> **Fully local, CPU-only.** Powered by [Vosk](https://alphacephei.com/vosk/), [MediaPipe](https://mediapipe.dev/), and [Ollama](https://ollama.ai/).

---

## 1  Features

| Category | What you get |
| -------- | ------------ |
| **Parsing** | PDF résumé → structured JSON<br>Job-description text → role JSON |
| **Question gen** | Static YAML templates with CV placeholders<br>LLM-generated technical / behavioural / culture-fit questions |
| **Interview runtime** | Webcam overlay, space-to-answer flow<br>Offline speech recognition (Vosk)<br>Instant LLM feedback per answer<br>Basic face-mesh gesture metrics |
| **Reporting** | `report.md` (exec summary, strengths, concerns, Q-by-Q table, next steps)<br>`scorecard.json` for dashboards |
| **Offline** | Everything runs on CPU—no cloud calls, no PyAudio headaches |

---

## 2  Folder layout

\`\`\`
interview-suite/
├─ parsers/
│  ├─ resume_parser.py
│  └─ job_offer_parser.py
├─ generator/
│  └─ question_generator.py
├─ interview/
│  └─ interview_simulator.py
├─ reports/
│  └─ report_generator.py
├─ models/
│  └─ vosk-model-small-en-us-0.15/   # download once
└─ resources/
   └─ generic_questions.yaml
\`\`\`

---

## 3  Prerequisites

| Tool | Notes |
| ---- | ----- |
| **Python** | 3.9 – 3.12 |
| **Ollama** | `ollama serve` running locally — e.g. `ollama pull mistral` |
| **Vosk model** | `vosk-model-small-en-us-0.15` in `models/` |
| **ffmpeg** | Only needed on some Linux audio setups |

Install Python deps:

\`\`\`bash
python -m venv .venv && source .venv/bin/activate     # Windows: .\.venv\Scripts\activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
\`\`\`

---

## 4  Quickstart

\`\`\`bash
# 1  Parse résumé
python parsers/resume_parser.py  data/CV.pdf

# 2  Parse job description
python parsers/job_offer_parser.py  data/job_offer.txt  > offer.json

# 3  Generate question set
python generator/question_generator.py  CV.pdf_parsed.json  offer.json  > questions.json

# 4  Run interview (webcam + mic)
python interview/interview_simulator.py  questions.json
#  → transcript.json, gestures.json

# 5  Generate final report
python reports/report_generator.py
#  → report.md, scorecard.json
\`\`\`

---

## 5  Workflow graph

\`\`\`mermaid
flowchart LR
    A[CV.pdf] -->|resume_parser| B(resume.json)
    C[Job offer.txt] -->|job_offer_parser| D(offer.json)
    B --> E(question_generator)
    D --> E
    E --> F(questions.json)
    F --> G(interview_simulator)
    G --> H(transcript.json)
    G --> I(gestures.json)
    H --> J(report_generator)
    I --> J
    F --> J
    J --> K(report.md)
\`\`\`

---

## 6  Config tips

| Need… | Edit |
| ----- | ---- |
| Different LLM | Change `OLLAMA_MODEL` constant in each script |
| More / fewer questions | `N_TECH`, `N_BEHAV`, `N_CULT` in `question_generator.py` |
| Other language | Download another Vosk model and update `VOSK_PATH` in `interview_simulator.py` |
| Deeper gesture analytics | Extend `analyse_frame()` in `interview_simulator.py` |

---

## 7  Contributing

1. Fork, create a feature branch.  
2. Run `python -m compileall .` or your tests before opening a PR.  
3. Keep code **CPU-only** and offline-friendly.

---


echo "README.md and .gitignore created! 🎉"
