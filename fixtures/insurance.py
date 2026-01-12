"""Insurance coverage fixtures."""

PROCEDURE_CODES = {
    "cleaning": "D1110",
    "checkup": "D0120",
    "consultation": "D9310",
    "xray": "D0220",
    "filling": "D2140",
    "extraction": "D7140",
    "crown": "D2740",
    "root_canal": "D3310",
}

INSURANCE_PLANS = {
    ("delta dental", "ppo"): {
        "D1110": {"covered": True, "copay": 25, "notes": "Cleaning covered twice per year"},
        "D0120": {"covered": True, "copay": 0, "notes": "Periodic exam fully covered"},
        "D9310": {"covered": True, "copay": 50},
        "D0220": {"covered": True, "copay": 15},
        "D2140": {"covered": True, "copay": 75},
        "D7140": {"covered": True, "copay": 100},
        "D2740": {"covered": True, "copay": 300, "notes": "50% coverage after deductible"},
        "D3310": {"covered": True, "copay": 250, "notes": "80% coverage after deductible"},
    },
    ("delta dental", "hmo"): {
        "D1110": {"covered": True, "copay": 0, "notes": "Cleaning covered twice per year"},
        "D0120": {"covered": True, "copay": 0},
        "D9310": {"covered": True, "copay": 35},
        "D0220": {"covered": True, "copay": 0},
        "D2140": {"covered": True, "copay": 50},
        "D7140": {"covered": True, "copay": 75},
        "D2740": {"covered": True, "copay": 450},
        "D3310": {"covered": True, "copay": 350},
    },
    ("cigna", "dppo"): {
        "D1110": {"covered": True, "copay": 20},
        "D0120": {"covered": True, "copay": 0},
        "D9310": {"covered": True, "copay": 45},
        "D0220": {"covered": True, "copay": 10},
        "D2140": {"covered": True, "copay": 60},
        "D7140": {"covered": True, "copay": 90},
        "D2740": {"covered": True, "copay": 350},
        "D3310": {"covered": True, "copay": 200},
    },
    ("aetna", "dmo"): {
        "D1110": {"covered": True, "copay": 15},
        "D0120": {"covered": True, "copay": 0},
        "D9310": {"covered": False, "copay": 0, "notes": "Consultation not covered under DMO"},
        "D0220": {"covered": True, "copay": 5},
        "D2140": {"covered": True, "copay": 55},
        "D7140": {"covered": True, "copay": 85},
        "D2740": {"covered": False, "copay": 0, "notes": "Crowns not covered under DMO"},
        "D3310": {"covered": True, "copay": 275},
    },
}

CASH_PAY_ESTIMATES = {
    "D1110": 150,
    "D0120": 75,
    "D9310": 100,
    "D0220": 50,
    "D2140": 200,
    "D7140": 250,
    "D2740": 1200,
    "D3310": 900,
}


def get_procedure_code(appointment_type: str) -> str:
    """Map appointment type to procedure code."""
    normalized = appointment_type.lower().replace(" ", "_").replace("-", "_")
    return PROCEDURE_CODES.get(normalized, "D9310")


def check_coverage(
    payer: str, plan: str, procedure_code: str
) -> dict:
    """Check insurance coverage for a procedure."""
    key = (payer.lower().strip(), plan.lower().strip())

    plan_coverages = INSURANCE_PLANS.get(key)
    if not plan_coverages:
        cash_estimate = CASH_PAY_ESTIMATES.get(procedure_code, 100)
        return {
            "covered": False,
            "copay_estimate": 0,
            "notes": f"No coverage found for {payer} {plan}. Cash-pay estimate: ${cash_estimate}",
        }

    coverage = plan_coverages.get(procedure_code)
    if not coverage:
        return {
            "covered": False,
            "copay_estimate": 0,
            "notes": f"Procedure {procedure_code} not covered",
        }

    return {
        "covered": coverage["covered"],
        "copay_estimate": coverage["copay"],
        "notes": coverage.get("notes"),
    }
