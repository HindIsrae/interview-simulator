#!/usr/bin/env python
"""
Enhanced report generator
──────────────────────────
Consumes:
  • transcript.json  (list of {question, answer, feedback})
  • gestures.json    (list of {metric:value, ...})
  • questions.json   (for category tagging)

Produces:
  • report.md
  • scorecard.json
"""

import json, subprocess, sys, textwrap, statistics, re
from pathlib import Path

OLLAMA_MODEL = "mistral"

# ───────── utility ───────── #
def read(name):
    return json.loads(Path(name).read_text(encoding="utf-8"))

def rating_to_stars(r: float) -> str:
    full = int(round(r))
    return "★" * full + "☆" * (5 - full)

# ───────── LLM helper ───────── #
def ask_llm(prompt: str) -> str:
    proc = subprocess.run(
        ["ollama", "run", OLLAMA_MODEL],
        input=prompt,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.stdout.strip()

# ───────── main ───────── #
def main():
    tr  = read("transcript.json")
    ges = read("gestures.json")
    qs  = read("questions.json")

    # 1. compute simple gesture scores (e.g. mouth_open→talking clarity)
    speak_clarity = [0 if g.get("mouth_open") else 1 for g in ges]
    eye_contact   = [1 - g.get("eye_distance", 0) for g in ges]  # crude proxy

    gesture_score = statistics.mean(speak_clarity + eye_contact) * 5  # 0-5

    # 2. aggregate LLM feedback sentiment (simple heuristic)
    sent_prom = "Score 0-5: how positive is each feedback? Reply JSON list."
    combined_feedback = [x["feedback"] for x in tr]
    pos_scores = json.loads(ask_llm(f"{sent_prom}\n{combined_feedback}"))
    tech_avg = statistics.mean(pos_scores)

    # 3. overall hire recommendation (LLM)
    hire_prompt = textwrap.dedent(f"""
      You are a senior hiring manager.
      Here is a list of feedback sentences and a gesture score on 0-5 scale.

      FEEDBACK: {combined_feedback}
      GESTURE_SCORE: {gesture_score:.1f}

      Provide:
       1. Overall rating on 0-5
       2. 3 key strengths
       3. 3 main concerns
      Return JSON {{ "rating":#, "strengths":[...], "concerns":[...] }}.
    """)
    hire_json = json.loads(ask_llm(hire_prompt))

    # 4. build Markdown
    md = ["# Candidate Interview Report\n"]
    md += ["## 1. Executive summary"]
    md += [f"**Recommendation:** {rating_to_stars(hire_json['rating'])} / 5"]
    md += [""]

    md += ["### Key strengths"]
    md += [f"- {s}" for s in hire_json["strengths"]]
    md += ["### Concerns / Risks"]
    md += [f"- {c}" for c in hire_json["concerns"]]
    md += [""]

    md += ["## 2. Detailed Q&A with feedback\n"]
    md += ["| # | Question | Key answer points | Coach feedback | Gesture flag |"]
    md += ["|---|----------|------------------|----------------|--------------|"]

    for i, (qa, g) in enumerate(zip(tr, ges), 1):
        flag = "⚠" if g.get("mouth_open") else "–"
        md += [f"| {i} | {qa['question']} | {qa['answer'][:80]} | {qa['feedback']} | {flag} |"]

    md += ["\n## 3. Gesture summary"]
    md += [f"- **Average clarity score:** {statistics.mean(speak_clarity):.2f}"]
    md += [f"- **Average eye-contact proxy:** {statistics.mean(eye_contact):.2f}"]

    md += ["\n## 4. Next steps"]
    md += ["- Panel review with technical lead.",
           "- Verify projects listed in résumé.",
           "- Schedule cultural-fit call if proceeding to next round."]

    Path("report.md").write_text("\n".join(md), encoding="utf-8")
    print("✔ report.md generated")

    # 5. write scorecard
    scorecard = {
        "overall_rating": hire_json["rating"],
        "gesture_score": gesture_score,
        "technical_sentiment": tech_avg
    }
    Path("scorecard.json").write_text(json.dumps(scorecard, indent=2))
    print("✔ scorecard.json generated")

if __name__ == "__main__":
    main()
