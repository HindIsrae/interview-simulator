#!/usr/bin/env python
"""
Turns a raw job-post (TXT or pasted JD) into structured JSON so the
question-generator can reason over it.
"""
import json, subprocess, sys, textwrap, re
from pathlib import Path
LLM="mistral"

PROMPT=textwrap.dedent("""
 You are an HR analyst. From this job description extract:
 1. Title
 2. Key Responsibilities (bullets, ≤8)
 3. Required Skills & Tech (list)
 4. Soft Skills / Behavioural traits
Return JSON with keys
{ "Title": "...", "Responsibilities":[...], "Skills":[...], "SoftSkills":[...] }.
---JOB---
{jd}
---END---
""").strip()

def main():
    if len(sys.argv)!=2: sys.exit("usage: job_offer_parser.py job.txt")
    jd=Path(sys.argv[1]).read_text(encoding="utf-8")[:4000]
    proc=subprocess.run(["ollama","run",LLM],input=PROMPT.format(jd=jd),
           text=True,capture_output=True,encoding="utf-8")
    m=re.search(r"\{.*\}",proc.stdout,re.S)
    print(m.group() if m else proc.stdout)

if __name__=="__main__": main()
