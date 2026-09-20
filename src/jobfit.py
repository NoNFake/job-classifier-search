import concurrent.futures as cf
import html
import re

from pathlib import Path

import yaml
from laya import Router
from rich.console import Console
from rich.table  import Table
from rich.text import Text

from sources.jobindex import get_jobs as jobindex_jobs
from sources.jobnet import get_jobs as jobnet_jobs

PROFILE = yaml.safe_load(Path("profile.yaml").read_text())
TOP = 50

def clean(text):
    return html.unescape(re.sub(r"<[^>]+>", " ", text or "")).strip()


def normalize(job, source):
    if source == "jobnet":
        return {
            "source": source,
            "id": job.get("tid"),
            "title": job.get("headline") or "",
            "company": job.get("companytext") or (job.get("company") or {}).get("name") or "",
            "location": job.get("area") or "",
            "url": job.get("share_url") or "",
            "description": clean(job.get("description")),
            "posted": job.get("firstdate") or "",
        }
    return {
        "source": source,
        "id": job.get("jobAdId"),
        "title": job.get("title") or "",
        "company": job.get("hiringOrgName") or "",
        "location": f"{job.get('postalCode') or ''} {job.get('postalDistrictName') or ''}".strip(),
        "url": job.get("jobAdUrl") or f"https://jobnet.dk/jobannonce/{job.get('jobAdId')}",
        "description": clean(job.get("description")),
        "posted": job.get("publicationDate") or "",
    }

def dedupe(jobs):
    seen, out = set(), []
    for job in jobs:
        key = (job["title"].lower().strip(), job["company"].lower().strip())
        if key not in seen:
            seen.add(key)
            out.append(job)
    return out


PROFILE_SUMMARY = (
    f"{PROFILE['seniority']} engineer targeting {', '.join(PROFILE['roles'])}. "
    f"Strong: {', '.join(PROFILE['skills']['strong'])}. "
    f"Good: {', '.join(PROFILE['skills']['good'])}. "
    f"Languages: {', '.join(f'{k} {v}' for k, v in PROFILE['languages'].items())}. "
    f"Location: {PROFILE['location_preference']}. Remote/hybrid allowed. No sponsorship needed."
)

# print(PROFILE_SUMMARY)

def build_state(job):
    return {
        "title": job["title"],
        "company": job["company"],
        "location": job["location"],
        "posted": job["posted"],
        "description_excerpt": job["description"][:900],
        "candidate_profile": PROFILE_SUMMARY,
    }


QUESTIONS = {
    "job_family": {
        "type": "choice",
        "instructions": "What kind of job is this?",
        "criteria": {
            "backend": "server-side, APIs, databases, services",
            "data_engineering": "pipelines, ETL, warehouses, Airflow, dbt",
            "ml_ai": "machine learning, LLM, GenAI, RAG, model deployment",
            "frontend": "React, UI, browser applications",
            "devops_platform": "Kubernetes, cloud infrastructure, CI/CD",
            "product_management": "roadmap, discovery, stakeholder management",
            "qa_testing": "manual or automated testing",
            "support_operations": "customer support, IT operations",
            "sales_marketing": "sales, marketing, lead generation",
            "other": "anything else",
        },
    },

    "seniority": {
        "type": "score",
        "instructions": "What seniority level does this job require?",
        "criteria": ["intern or junior", "mid-level", "senior", "lead or principal"],
    },

    "english_enough": {
        "type": "noul",
        "instructions": "Can an English-speaking candidate reasonably work in this role without fluent Danish?",
    },
    "danish_required": {
        "type": "noul",
        "instructions": "Does this job strongly require fluent Danish?",
    },
    "copenhagen_possible": {
        "type": "noul",
        "instructions": "Is this job realistically possible for someone based in or moving to Copenhagen?",
    },
    "skill_overlap": {
        "type": "score",
        "instructions": "How well does the candidate profile match the required skills?",
        "criteria": ["no meaningful overlap", "weak overlap", "partial overlap", "strong overlap", "near-perfect overlap"],
    },
    "role_fit": {
        "type": "score",
        "instructions": "How well does this role fit the candidate's target roles?",
        "criteria": ["wrong career direction", "adjacent role", "acceptable role", "good role", "ideal role"],
    },
    "spam_or_mass_recruiting": {
        "type": "noul",
        "instructions": "Is this a scam, low-quality mass recruiting message, or irrelevant automated job ad?",
    },
    "sponsorship_needed": {
        "type": "noul",
        "instructions": "Does this job appear to require employer sponsorship for non-EU candidates?",
    },
}

def clamp(value, minimum=0.0, maximum=1.0):
    return max(minimum, min(maximum, value))

def normalize_score(value, max_value):
    return clamp(value / max_value)

def seniority_compatibility(job_seniority, candidate_seniority):
    levels = {"junior": 0.0, "mid": 0.33, "senior": 0.66, "lead": 1.0}
    candidate = levels[candidate_seniority]
    if job_seniority <= candidate + 0.15:
        return 1.0
    if job_seniority <= candidate + 0.35:
        return 0.7
    return 0.35


def compute_final_percent(answers, profile):
    family = answers["job_family"]["choice"]
    probs = answers["job_family"]["probabilities"]
    seniority = normalize_score(answers["seniority"]["score"], 3.0)
    skill = normalize_score(answers["skill_overlap"]["score"], 4.0)
    role = normalize_score(answers["role_fit"]["score"], 4.0)

    english = answers["english_enough"]["noul"]
    danish = answers["danish_required"]["noul"]
    copenhagen = answers["copenhagen_possible"]["noul"]
    spam = answers["spam_or_mass_recruiting"]["noul"]
    sponsorship = answers["sponsorship_needed"]["noul"]

    family_score = sum(probs.get(f, 0.0) for f in ("backend", "data_engineering", "ml_ai", "devops_platform"))
    language_score = english * (1.0 - danish)
    location_score = copenhagen
    legal_score = 1.0 - 0.2 * sponsorship if not profile["work_authorization"]["needs_sponsorship"] else 1.0 - sponsorship

    base = (
        0.30 * skill
        + 0.20 * role
        + 0.15 * family_score
        + 0.10 * language_score
        + 0.10 * location_score
        + 0.05 * legal_score
        + 0.10 * seniority_compatibility(seniority, profile["seniority"])
    )
    final = clamp(base - 0.65 * spam)

    return {
        "final_percent": round(final * 100, 1),
        "reasons": {
            "job_family": family,
            "family_probability": round(family_score, 3),
            "skill_overlap": round(skill, 3),
            "role_fit": round(role, 3),
            "language_score": round(language_score, 3),
            "location_score": round(location_score, 3),
            "spam_probability": round(spam, 3),
            "seniority_score": round(seniority, 3),
        },
    }


def percent_text(value):
    style = "green" if value >= 80 else "yellow" if value >= 60 else "dim"
    return Text(f"{value}%", style=style)


def main():
    with cf.ThreadPoolExecutor(2) as pool:
        net, idx = pool.map(lambda fn: fn(), [jobnet_jobs, jobindex_jobs])

    jobs = dedupe(
        [normalize(j, "jobnet") for j in net] + 
        [normalize(j, "jobindex") for j in idx] 
    )
    print(f"jobs after dedupe: {len(jobs)}")

    router = Router(
        preload=["english", "multilingual"], device="cuda"
    )

    scored = []
    for i, job in enumerate(jobs, 1):
        result =  router.predict(build_state(job), QUESTIONS)
        scored.append(job | compute_final_percent(result["answers"], PROFILE))

        if i % 50 == 0:
            print(f"{i}/{len(jobs)}")
    scored.sort(key=lambda j: j["final_percent"], reverse=True)

    table = Table(title=f"TOP {TOP} jobs for {PROFILE['location_preference']}")
    table.add_column("match", justify="right")
    table.add_column("title", overflow="fold")
    table.add_column("company")
    table.add_column("location")
    table.add_column("source")

    for job in scored[:TOP]:
        title = Text(job["title"][:60], style=f"link {job['url']}")
        table.add_row(
            percent_text(job["final_percent"]),
            title,
            job["company"][:30],
            job["location"][:25],
            job["source"],
        )

    Console().print(table)

main()