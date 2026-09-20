import laya

agent = laya.load("convaiinnovations/laya")


while True:
    body_text: str = input("> ")
    state = {
        "from": "user@acme.com",
        "subject": "Duplicate charge on invoice #4411",
        "body": body_text
    }

    questions = {
        # choice: categorical selection with probabilities & confidence
        "department": {
            "type": "choice",
            "instructions": "Which department should handle this email?",
            "criteria": {
                "billing": "invoices, payments, refunds",
                "technical": "bugs, outages, system errors",
                "sales": "pricing, new contracts",
                "other": "everything else"
            }
        },
        # score: placement on an ordinal rubric
        "urgency": {
            "type": "score",
            "instructions": "How urgent is this request?",
            "criteria": ["not urgent", "soon", "critical deadline or blocking issue"]
        },
        # noul: calibrated boolean probability P(true)
        "churn_risk": {
            "type": "noul",
            "instructions": "Does the user threaten to cancel or leave?"
        },
        "is_phishing": {
            "type": "noul",
            "instructions": "Is this email a phishing or scam attempt?"
        }
    }

    # 4. Run all questions in ONE single forward pass (~35 ms on GPU)
    result = agent.predict(state, questions)
    answers = result["answers"]

    print("Department :", answers["department"]["choice"])
    # -> billing (confidence: 0.94)

    print("Urgency    :", answers["urgency"]["score"])
    # -> 1.84 / 2.0

    print("Churn Risk :", answers["churn_risk"]["noul"])
    # -> 0.892 (89.2% probability)

    print("Phishing   :", answers["is_phishing"]["noul"])
    # -> 0.008 (0.8% probability)
def main() -> None:
    print("Hello from classifier!")
