import concurrent.futures as cf
import hashlib
import html
import json
import re

from pathlib import Path

import yaml
from laya import Router
from rich.console import Console
from rich.table  import Table
from rich.text import Text

from sources.jobindex import get_jobs as jobindex_jobs
from sources.jobnet import get_jobs as jobnet_jobs
from sources.enrich import enrich_jobindex

PROFILE = yaml.safe_load(Path("profile.yaml").read_text())
TOP = 100
SCORES = Path(".cache/scores.json")
CALIBRATION = Path("calibration.json")
CACHE_VERSION = "enriched-2"

def clean(text):
    return html.unescape(re.sub(r"<[^>]+>", " ", text or "")).strip()


# def normalize(job, source):
#     if source == "jobnet":
#         return {
#             "source": source,
#             "id": job.get("jobAdId"),
#             "title": job.get("title") or "",
#             "company": job.get("hiringOrgName") or "",
#             "location": f"{job.get('postalCode') or ''} {job.get('postalDistrictName') or ''}".strip(),
#             "url": job.get("jobAdUrl") or f"https://jobnet.dk/jobannonce/{job.get('jobAdId')}",
#             "description": clean(job.get("description")),
#             "posted": job.get("publicationDate") or "",
#         }
#     return {
#         "source": source,
#         "id": job.get("tid"),
#         "title": job.get("headline") or "",
#         "company": job.get("companytext") or (job.get("company") or {}).get("name") or "",
#         "location": job.get("area") or "",
#         "url": job.get("share_url") or "",
#         "description": clean(job.get("description")),
#         "posted": job.get("firstdate") or "",
#     }


def normalize(job, source):
    if source == "jobnet":
        return {
            "source": source,
            "id": job.get("jobAdId"),
            "title": job.get("title") or "",
            "company": job.get("hiringOrgName") or "",
            "location": f"{job.get('postalCode') or ''} {job.get('postalDistrictName') or ''}".strip(),
            "url": job.get("jobAdUrl") or f"https://jobnet.dk/jobannonce/{job.get('jobAdId')}",
            "description": clean(job.get("description")),
            "posted": job.get("publicationDate") or "",
            "deadline": job.get("applicationDeadline") or "",
            "address": (job.get("workPlaceAddress") or "").strip(),
            "latitude": None,
            "longitude": None,
            "distance_km": None,
            "employment": job.get("jobAnnouncementTypeName") or "",
            "home_workplace": None,
            "external": bool(job.get("isExternal")),
            "occupation": job.get("occupation") or "",
            "apply_url": job.get("jobAdUrl") or "",
        }
    addr = (job.get("addresses") or [{}])[0]
    coords = addr.get("coordinates") or {}
    company = job.get("company") or {}
    return {
        "source": source,
        "id": job.get("tid"),
        "title": job.get("headline") or "",
        "company": job.get("companytext") or company.get("name") or "",
        "location": job.get("area") or "",
        "url": job.get("share_url") or "",
        "description": clean(job.get("description")),
        "posted": job.get("firstdate") or "",
        "deadline": job.get("lastdate") or "",
        "address": addr.get("line") or "",
        "latitude": coords.get("latitude"),
        "longitude": coords.get("longitude"),
        "distance_km": job.get("distance"),
        "employment": "",
        "home_workplace": job.get("home_workplace"),
        "external": not job.get("is_local", True),
        "occupation": "",
        "apply_url": job.get("apply_url") or "",
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
    f"Candidate: {PROFILE['seniority']} developer, also open to student, intern and entry-level roles. "
    f"Target roles: {', '.join(PROFILE['roles'])}. "
    f"Target level: {', '.join(PROFILE['preferred_seniority'])}. "
    f"Strong: {', '.join(PROFILE['skills']['strong'])}. "
    f"Good: {', '.join(PROFILE['skills']['good'])}. "
    f"Languages: {', '.join(f'{k} {v}' for k, v in PROFILE['languages'].items())}. "
    f"Location: {PROFILE['location_preference']}. Remote/hybrid allowed. No sponsorship needed."
)

# print(PROFILE_SUMMARY)

TECH_WORDS = [
    "python", "fastapi", "postgres", "docker", "git", "typescript", "react", "aws", "kubernetes",
    "langchain", "rag", "transformer", "machine learning", "ml", "genai", "llm", "api", "backend",
    "frontend", "devops", "cloud", "sql", "database", "data", "software", "developer", "engineer",
    "udvikler", "programmør", "systemudvikling", "infrastructure", "linux", "azure", "gcp",
    "snowflake", "spark", "airflow", "etl", "network", "netværk", "it-arkitekt", "it-konsulent",
]
KEYWORD_LIST = sorted({
    *TECH_WORDS,
    *(s.lower() for s in PROFILE["skills"]["strong"]),
    *(s.lower() for s in PROFILE["skills"]["good"]),
})
KEYWORD_RE = re.compile(r"\b(" + "|".join(map(re.escape, KEYWORD_LIST)) + r")")


def tech_hits(job):
    return len(set(KEYWORD_RE.findall((job["title"] + " " + job["description"]).lower())))


WAREHOUSE_WORDS = [
    "lager", "pakkeri", "pluk", "varemodtagelse", "truck", "palle", "logistik",
    "forsendelse", "sortering", "warehouse", "wms", "scanning", "stabler",
]
WAREHOUSE_RE = re.compile(r"\b(" + "|".join(map(re.escape, WAREHOUSE_WORDS)) + r")")


def warehouse_job(job):
    return bool(WAREHOUSE_RE.search(job["title"].lower()))


def _matches(text, patterns):
    text = (text or "").lower()
    for pattern in patterns:
        p = pattern.lower().strip()
        if not p:
            continue
        if len(p) <= 3:
            if re.search(rf"\b{re.escape(p)}\b", text):
                return p
        elif p in text:
            return p
    return None


def blacklisted(job):
    return (
        _matches(job["company"], PROFILE.get("blacklist_companies", []))
        or _matches(job["title"], PROFILE.get("blacklist_title_keywords", []))
        or _matches(job["description"], PROFILE.get("blacklist_description_patterns", []))
    )


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
            "warehouse_logistics": "warehouse, picking, packing, sorting, unloading, forklift",
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
    # model "seniority" score is 0..3: junior, mid, senior, lead
    levels = {"junior": 0.0, "mid": 1.0, "senior": 2.0, "lead": 3.0}
    diff = job_seniority - levels[candidate_seniority]
    if diff <= 0.5:
        return 1.0
    if diff <= 1.5:
        return 0.6
    return 0.2


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

    family_score = sum(probs.get(f, 0.0) for f in ("backend", "data_engineering", "ml_ai", "devops_platform", "warehouse_logistics"))
    language_score = english * (1.0 - danish)
    location_score = copenhagen
    legal_score = 1.0 - 0.2 * sponsorship if not profile["work_authorization"]["needs_sponsorship"] else 1.0 - sponsorship

    base = (
        0.25 * skill
        + 0.15 * role
        + 0.15 * family_score
        + 0.10 * language_score
        + 0.10 * location_score
        + 0.05 * legal_score
        + 0.20 * seniority_compatibility(seniority, profile["seniority"])
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


def score_key(job):
    return f"{job['title'].lower().strip()}|{job['company'].lower().strip()}"


def power(probs, k):
    scaled = [p ** k for p in probs]
    total = sum(scaled)
    return [p / total for p in scaled]


def apply_calibration(answers, calibration):
    if not calibration:
        return answers
    out = {}
    for qid, ans in answers.items():
        k = calibration.get(qid, 1.0)
        if k == 1.0:
            out[qid] = ans
        elif ans["type"] == "choice":
            keys = list(ans["probabilities"])
            probs = power([ans["probabilities"][key] for key in keys], k)
            out[qid] = ans | {
                "choice": keys[probs.index(max(probs))],
                "probabilities": dict(zip(keys, (round(p, 4) for p in probs))),
            }
        elif ans["type"] == "score":
            keys = list(ans["probabilities"])
            probs = power([ans["probabilities"][key] for key in keys], k)
            out[qid] = ans | {
                "score": round(sum(i * p for i, p in enumerate(probs)), 4),
                "probabilities": dict(zip(keys, (round(p, 4) for p in probs))),
            }
        else:
            probs = power([1.0 - ans["noul"], ans["noul"]], k)
            out[qid] = ans | {"noul": round(probs[1], 4)}
    return out


def percent_text(value):
    style = "green" if value >= 80 else "yellow" if value >= 60 else "dim"
    return Text(f"{value}%", style=style)


def load_jobs():
    with cf.ThreadPoolExecutor(2) as pool:
        net, idx = pool.map(lambda fn: fn(), [jobnet_jobs, jobindex_jobs])
    jobs =  dedupe(
        [normalize(j, "jobnet") for j in net] +
        [normalize(j, "jobindex") for j in idx]
    )
    return enrich_jobindex(jobs)




def main():
    all_jobs = load_jobs()
    jobs, blocked = [], 0
    for job in all_jobs:
        if not tech_hits(job):
            continue
        if blacklisted(job):
            blocked += 1
            continue
        jobs.append(job)
    print(f"jobs after dedupe: {len(all_jobs)} | relevant: {len(jobs)} | blacklisted: {blocked}")

    calibration = json.loads(CALIBRATION.read_text()) if CALIBRATION.exists() else {}
    if calibration:
        print(f"calibration: {calibration}")

    profile_hash = hashlib.sha1(json.dumps(PROFILE, sort_keys=True).encode()).hexdigest()[:10]
    cache = json.loads(SCORES.read_text()) if SCORES.exists() else {}
    stale = cache.pop("_profile_hash", None) != profile_hash
    stale = cache.pop("_version", None) != CACHE_VERSION or stale
    if stale:
        print("profile or text changed: rescoring")
        cache = {}
    print(f"scores cached: {len(cache)}")
    cache["_profile_hash"] = profile_hash
    cache["_version"] = CACHE_VERSION

    router = None
    scored = []
    for i, job in enumerate(jobs, 1):
        key = score_key(job)
        entry = cache.get(key)
        if entry and "answers" in entry:
            answers = apply_calibration(entry["answers"], calibration)
            scored.append(job | compute_final_percent(answers, PROFILE))
            continue
        if entry:
            scored.append(job | entry)
            continue
        if router is None:
            router = Router(preload=["english", "multilingual"], device="cuda")
        result = router.predict(build_state(job), QUESTIONS)
        answers = apply_calibration(result["answers"], calibration)
        score = compute_final_percent(answers, PROFILE)
        cache[key] = score | {"answers": answers}
        scored.append(job | score)

        if i % 50 == 0:
            print(f"{i}/{len(jobs)}")
            SCORES.write_text(json.dumps(cache, ensure_ascii=False))
    SCORES.write_text(json.dumps(cache, ensure_ascii=False))
    scored.sort(key=lambda j: j["final_percent"], reverse=True)
    it_jobs = [j for j in scored if not warehouse_job(j)]
    warehouse_jobs = [j for j in scored if warehouse_job(j)]
    print(f"IT: {len(it_jobs)} | warehouse/logistics: {len(warehouse_jobs)}")

    render(f"TOP {TOP} IT jobs for {PROFILE['location_preference']}", it_jobs)
    render(f"TOP {TOP} warehouse / logistics for {PROFILE['location_preference']}", warehouse_jobs)


def render(title, jobs):
    table = Table(title=title)
    table.add_column("match", justify="right")
    table.add_column("title", overflow="fold")
    table.add_column("company")
    table.add_column("location")
    table.add_column("source")

    for job in jobs[:TOP]:
        table.add_row(
            percent_text(job["final_percent"]),
            Text(job["title"][:60], style=f"link {job['url']}"),
            job["company"][:30],
            job["location"][:25],
            job["source"],
        )

    Console().print(table)


if __name__ == "__main__":
    main()