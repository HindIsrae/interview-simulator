#!/usr/bin/env python3
"""
Résumé Parser v2
────────────────
✓ Robust section detection (EN & FR headings, mixed cases)
✓ Bullet‑proof Contact Information extraction
✓ UTF‑8‑safe Ollama calls (no Windows console crashes)
✓ Auto‑fills Projects (if missing) and Certifications

Requires
--------
pip install pdfminer.six nameparser spacy
python -m spacy download en_core_web_sm
ollama pull mistral        # or any model you prefer
"""

import json
import re
import subprocess
import sys
from pathlib import Path

from nameparser import HumanName
from pdfminer.high_level import extract_text
import spacy

# ───────────────────────── CONFIG ───────────────────────── #
if len(sys.argv) != 2:
    sys.exit("Usage:  python resume_parser.py  /path/to/resume.pdf")

PDF_PATH = Path(sys.argv[1]).expanduser()
if not PDF_PATH.is_file():
    sys.exit(f"❌  File not found: {PDF_PATH}")

EMAIL_RE = re.compile(r"[A-Za-z0-9+._%-]+@[A-Za-z0-9._%-]+\.[A-Za-z]{2,6}")
PHONE_RE = re.compile(r"\+?\d[\d ()\-]{7,}\d")

SECTION_ORDER = [
    "Contact Information",
    "Target Title",
    "Professional Summary",
    "Work Experience",
    "Education",
    "Skills & Interests",
    "Certifications",
    "Awards & Scholarships",
    "Projects",
    "Volunteering & Leadership",
    "Publications",
]

HEADING_PATTERNS = {
    "Contact Information": r"contact information",
    "Target Title": r"target title",
    "Professional Summary": r"(professional summary|summary|profile)",
    "Work Experience": r"(work experience|experience|professional experience)",
    "Education": r"education",
    "Skills & Interests": r"(skills\s*(?:&|and)\s*interests|skills|interests|compétences)",
    "Certifications": r"(certifications?|certificats?)",
    "Awards & Scholarships": r"(awards|scholarships|récompenses)",
    "Projects": r"(projects?|projets?)",
    "Volunteering & Leadership": r"(volunteering|leadership|bénévolat)",
    "Publications": r"publications?",
}

LLM_MODEL = "mistral"
nlp = spacy.load("en_core_web_sm")

# tokens that must **not** be considered part of the name
LOCATION_STOP = {
    "morocco", "maroc", "rabat", "casablanca",
    "tanger", "agadir", "meknes", "fes", "marrakesh",
}


# ──────────────────────── HELPERS ───────────────────────── #
def find_sections(text: str) -> dict:
    """Split résumé into {section: raw_text}."""
    lines = [ln.strip() for ln in text.splitlines()]
    markers = []
    for i, ln in enumerate(lines):
        for name, pat in HEADING_PATTERNS.items():
            if re.match(rf"^{pat}\s*:?\s*$", ln, flags=re.I):
                markers.append((i, name))
    markers.sort()

    sections = {k: "" for k in SECTION_ORDER}
    for (start, name), (end, _) in zip(markers, markers[1:] + [(len(lines), None)]):
        sections[name] = "\n".join(lines[start + 1 : end]).strip()
    return sections


def extract_contact(text: str) -> dict:
    """
    Robust header parser
      • prefers explicit “name line”,
      • falls back to PERSON entity,
      • last‑ditch: derive from e‑mail,
      • never mistakes a country / city for the name.
    """
    lines = [ln.strip() for ln in text.splitlines()[:30] if ln.strip()]

    # e‑mail / phone
    email = next((m.group() for ln in lines if (m := EMAIL_RE.search(ln))), "")
    phone = next((m.group() for ln in lines if (m := PHONE_RE.search(ln))), "")

    # 1  explicit name line (2–5 words, not an email/phone)
    name_line = next(
        (
            ln
            for ln in lines[:10]
            if 2 <= len(ln.split()) <= 5
            and not EMAIL_RE.search(ln)
            and not PHONE_RE.search(ln)
        ),
        "",
    )

    if name_line:
        human = HumanName(name_line)
        first, last = human.first, human.last
    else:
        # 2  spaCy PERSON
        doc = nlp(" ".join(lines[:15]))
        ents = [
            ent.text
            for ent in doc.ents
            if ent.label_ == "PERSON"
            and len(ent.text.split()) >= 2
            and not any(tok.lower() in LOCATION_STOP for tok in ent.text.split())
        ]
        if ents:
            human = HumanName(max(ents, key=len))
            first, last = human.first, human.last
        else:
            # 3  derive from email
            local = email.split("@")[0]
            local = re.sub(r"[._\-]+", " ", local)
            local = re.sub(r"([a-z])([A-Z])", r"\1 \2", local)
            human = HumanName(local)
            first, last = human.first, human.last

    first, last = first.title(), last.title()

    # location entity
    doc = nlp(" ".join(lines[:12]))
    location = next((ent.text for ent in doc.ents if ent.label_ in ("GPE", "LOC")), "")

    return {
        "First Name": first,
        "Last Name": last,
        "Email": email,
        "Phone": phone,
        "Location": location,
    }


def call_llm(section: str, body: str):
    """Run Ollama and return parsed JSON fragment."""
    if not body.strip():
        return [] if section != "Professional Summary" else ""

    PROMPTS = {
        "Professional Summary": """Extract one ≤70‑word professional summary.
Return JSON: { "Professional Summary": "..." }""",
        "Skills & Interests": """Group skills into
["Programming Languages","Frameworks & Libraries","Tools & Platforms","Soft Skills","Languages"].
Return JSON exactly in that form.""",
        "Certifications": """List each certification with fields
"Certificate","Issuer","Date" (Date may be empty).
Return JSON: { "Certifications": [ {...}, ... ] }""",
        "Projects": """For each project provide "Title","Description","Technologies".
Return JSON: { "Projects": [...] }""",
    }
    prompt = PROMPTS.get(
        section,
        f'Extract structured data for "{section}". Return JSON: {{ "{section}": [...] }}',
    )
    full_prompt = f"{prompt}\n\n---\n{body}\n---"

    proc = subprocess.run(
        ["ollama", "run", LLM_MODEL],
        input=full_prompt,
        capture_output=True,
        text=True,
        encoding="utf-8",   # ← prevents Windows UnicodeDecodeError
        errors="replace",
    )

    m = re.search(r"\{.*\}", proc.stdout, flags=re.S)
    if not m:
        print(f"⚠️  {section}: no JSON found in LLM output.")
        return [] if section != "Professional Summary" else ""

    try:
        parsed = json.loads(m.group())
        return parsed.get(section, parsed)
    except json.JSONDecodeError:
        print(f"⚠️  {section}: invalid JSON.")
        return [] if section != "Professional Summary" else ""


def ensure_projects(sections: dict, output: dict):
    """If Projects list is empty, mine Work‑Experience bullets for project lines."""
    if output["Projects"]:
        return
    candidate = [
        ln
        for ln in sections["Work Experience"].splitlines()
        if re.search(r"\b(project|built|developed|created|designed)\b", ln, re.I)
    ]
    if not candidate:
        return
    parsed = call_llm("Projects", "\n".join(candidate))
    if parsed:
        output["Projects"] = parsed


def ensure_certifications(sections: dict, output: dict):
    """Fallback: treat bullet lines containing 'certificate' as certs."""
    if output["Certifications"]:
        return
    lines = [
        ln for ln in sections.get("Skills & Interests", "").splitlines()
        if "cert" in ln.lower()
    ] + [
        ln for ln in sections.get("Work Experience", "").splitlines()
        if "cert" in ln.lower()
    ]
    if not lines:
        return
    parsed = call_llm("Certifications", "\n".join(lines))
    if parsed:
        output["Certifications"] = parsed


# ────────────────────────── MAIN ────────────────────────── #
raw = extract_text(str(PDF_PATH)).replace("\r", "")
sections = find_sections(raw)

out: dict[str, object] = {}

# Contact Information
out["Contact Information"] = (
    extract_contact(sections["Contact Information"])
    if sections["Contact Information"]
    else extract_contact(raw)
)

# Target Title
tt_lines = [ln for ln in sections["Target Title"].splitlines() if ln.strip()]
out["Target Title"] = tt_lines[0] if tt_lines else ""

# Professional Summary
out["Professional Summary"] = call_llm("Professional Summary", sections["Professional Summary"])

# Work Experience & Education
for sec in ("Work Experience", "Education"):
    out[sec] = call_llm(sec, sections[sec])

# Skills, Certs, Projects
for sec in ("Skills & Interests", "Certifications", "Projects"):
    out[sec] = call_llm(sec, sections[sec])

# Post‑processing fallbacks
ensure_projects(sections, out)
ensure_certifications(sections, out)

# Empty placeholders
for sec in ("Awards & Scholarships", "Volunteering & Leadership", "Publications"):
    out[sec] = out.get(sec, [])

# Save
json_path = PDF_PATH.with_stem(PDF_PATH.stem + "_parsed").with_suffix(".json")
json_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"✅  Parsed résumé saved → {json_path}")
