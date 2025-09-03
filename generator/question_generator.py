#!/usr/bin/env python
"""
question_generator.py
─────────────────────
Usage:
    python question_generator.py  resume_parsed.json  job_offer.txt  > questions.json
Requires:
    • Ollama running locally (`ollama serve`)
    • A CPU-friendly model pulled (e.g. `ollama pull mistral`)
"""

import json, subprocess, sys, textwrap
from pathlib import Path

OLLAMA_MODEL = "mistral"    # <= change if you prefer phi3, llama3-instruct, etc.
N_TECH   = 6               # how many technical questions
N_BEHAV  = 4               # how many behavioral / soft-skill questions
N_CULT   = 2               # company / culture fit

PROMPT_TEMPLATE = textwrap.dedent("""
    You are an experienced technical interviewer.

    ROLE OVERVIEW (from job offer):
    ---
    {job_offer}
    ---

    CANDIDATE SNAPSHOT (from parsed CV):
    ---
    {resume_overview}
    ---

    TASK:
    1. Draft {n_tech} **technical / role-specific** questions focusing on the
       skills and technologies in the job offer and those visible in the CV.
    2. Draft {n_behav} **behavioral** questions (STAR method) to probe soft skills
       like leadership, conflict resolution, ownership.
    3. Draft {n_cult} **culture-fit** or motivation questions.

    Return **exactly** this JSON schema:

    {{
      "Technical": [ "...", ... ],
      "Behavioral": [ "...", ... ],
      "CultureFit": [ "...", ... ]
    }}

    Keep each question ≤ 120 characters, no numbering, no extra keys.
""").strip()


def load_inputs(resume_json_path: Path, job_offer_path: Path) -> tuple[str, str]:
    resume_data = json.loads(resume_json_path.read_text(encoding="utf-8"))
    # build a concise text block (name, headline, key skills, recent positions)
    name = f"{resume_data['Contact Information']['First Name']} {resume_data['Contact Information']['Last Name']}"
    summary = resume_data.get("Professional Summary", "")[:300]
    last_job = resume_data.get("Work Experience", [{}])[0]
    skills = ", ".join(resume_data.get("Skills & Interests", {}).get("Programming Languages", [])[:6])

    resume_overview = (
        f"Name: {name}\n"
        f"Summary: {summary}\n"
        f"Latest role: {last_job.get('Position','')} at {last_job.get('Company','')}\n"
        f"Key skills: {skills}"
    )

    job_offer_text = job_offer_path.read_text(encoding="utf-8")[:4000]  # keep prompt short
    return resume_overview, job_offer_text


def call_ollama(prompt: str) -> dict:
    proc = subprocess.run(
        ["ollama", "run", OLLAMA_MODEL],
        input=prompt,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    # extract first {...} block
    import re, json
    m = re.search(r"\{.*\}", proc.stdout, flags=re.S)
    if not m:
        sys.exit("❌  Ollama did not return JSON. Full output:\n" + proc.stdout)
    return json.loads(m.group())


def main():
    if len(sys.argv) != 3:
        sys.exit("Usage:\n  python question_generator.py  resume_parsed.json  job_offer.txt")

    resume_path = Path(sys.argv[1])
    job_path    = Path(sys.argv[2])
    if not (resume_path.is_file() and job_path.is_file()):
        sys.exit("❌  Input file(s) not found.")

    resume_oview, job_text = load_inputs(resume_path, job_path)

    prompt = PROMPT_TEMPLATE.format(
        job_offer=job_text,
        resume_overview=resume_oview,
        n_tech=N_TECH,
        n_behav=N_BEHAV,
        n_cult=N_CULT,
    )

    questions_json = call_ollama(prompt)
    # pretty-print to stdout so user can redirect to .json file
    print(json.dumps(questions_json, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
