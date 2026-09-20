import csv
import json
import math
from pathlib import Path

from laya import Router

from jobfit import QUESTIONS, build_state, load_jobs, power, score_key

LABELS = Path("labels.csv")
OUT = Path("calibration.json")
GRID = [round(0.05 * i, 2) for i in range(1, 101)]
MIN_LABELS = 20


def nll(samples, k):
    total = 0.0
    for probs, label in samples:
        total -= math.log(max(1e-12, power(probs, k)[label]))
    return total / len(samples)


def fit_k(samples):
    return min(GRID, key=lambda k: nll(samples, k))


def main():
    jobs = {score_key(j): j for j in load_jobs()}
    rows = []
    with LABELS.open() as fh:
        for row in csv.DictReader(fh):
            job = jobs.get(row["key"])
            if job:
                rows.append((row, job))
    print(f"labeled rows matched: {len(rows)}")

    router = Router(preload=["multilingual"], device="cuda")
    samples = {"skill_overlap": [], "role_fit": [], "spam_or_mass_recruiting": []}
    for row, job in rows:
        answers = router.predict(build_state(job), QUESTIONS, model="multilingual")["answers"]
        if row["human_skill_overlap"]:
            p = answers["skill_overlap"]["probabilities"]
            samples["skill_overlap"].append(([p[str(i)] for i in range(5)], int(float(row["human_skill_overlap"]))))
        if row["human_role_fit"]:
            p = answers["role_fit"]["probabilities"]
            samples["role_fit"].append(([p[str(i)] for i in range(5)], int(float(row["human_role_fit"]))))
        if row["human_spam"]:
            noul = answers["spam_or_mass_recruiting"]["noul"]
            samples["spam_or_mass_recruiting"].append(([1.0 - noul, noul], round(float(row["human_spam"]))))

    calibration = {}
    for qid, s in samples.items():
        if len(s) < MIN_LABELS:
            print(f"{qid}: {len(s)} labels, skipped (need {MIN_LABELS})")
            continue
        k = fit_k(s)
        calibration[qid] = k
        edge = "  (grid edge, want more flattening)" if k in (GRID[0], GRID[-1]) else ""
        print(f"{qid}: k={k}  nll {nll(s, 1.0):.3f} -> {nll(s, k):.3f}  ({len(s)} labels){edge}")

    OUT.write_text(json.dumps(calibration, ensure_ascii=False, indent=2))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
