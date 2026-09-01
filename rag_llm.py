import os
import json
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(override=True)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError(
        "OPENAI_API_KEY was not found in the AIPortfolio .env file."
    )

client = OpenAI(api_key=OPENAI_API_KEY)

BASE_DIR = Path(__file__).resolve().parent

EVIDENCE_FILE = BASE_DIR / "portfolio_evidence.json"
OUTPUT_FILE = BASE_DIR / "portfolio_narrative.json"

# ============================================================
# LOAD EVIDENCE
# ============================================================

def load_evidence():
    if not EVIDENCE_FILE.exists():
        raise FileNotFoundError(
            f"Could not find {EVIDENCE_FILE}"
        )

    with open(EVIDENCE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# BUILD RETRIEVED CONTEXT
# ============================================================

def build_retrieved_context(data):
    """
    Creates a compact evidence context for the LLM.

    This is our first simple RAG implementation.
    We retrieve the most important portfolio-level and
    holding-level evidence rather than sending arbitrary data.
    """

    portfolio = data.get("portfolio", {})

    context = {
        "portfolio": portfolio,
        "forces_pushing_up": data.get("forces_pushing_up", []),
        "forces_pushing_down": data.get("forces_pushing_down", []),
        "forces_mixed_or_unclear": data.get(
            "forces_mixed_or_unclear", []
        ),
        "sector_evidence": data.get("sector_evidence", {}),
        "holding_evidence": data.get("holding_evidence", []),
    }

    return context


# ============================================================
# GENERATE LLM NARRATIVE
# ============================================================

def generate_narrative(context):
    system_prompt = """
You are an AI portfolio analysis assistant.

Your job is to explain portfolio performance using ONLY the
portfolio data and retrieved financial-news evidence provided
to you.

IMPORTANT RULES:

1. Never invent facts, news, causes, numbers, or explanations.

2. Clearly distinguish:
   - observed market movement
   - news sentiment
   - possible explanation
   - proven causation

3. News sentiment does NOT automatically mean the news caused
   the stock price movement.

4. If a stock declined but there is no relevant retrieved
   evidence explaining the decline, explicitly say that the
   available evidence is insufficient.

5. If news sentiment is positive but the stock declined, do
   NOT describe the news as a positive contributor to the
   portfolio. Explain that the news was positive in tone while
   the observed market move was negative.

6. Do not claim that a factor "caused" a price movement unless
   the supplied evidence explicitly establishes causation.
   Prefer phrases such as:
   - "aligned with"
   - "may have contributed"
   - "provides a possible explanation"
   - "the available evidence does not establish causation"

7. Prioritize the largest portfolio contributors.

8. Use exact portfolio numbers supplied in the evidence.

9. Do not provide personalized investment advice or tell the
   user to buy or sell securities.

10. Be concise, analytical, and transparent about uncertainty.

Return valid JSON only.
"""

    user_prompt = f"""
Analyze the following portfolio evidence.

Generate a grounded portfolio report with these sections:

- portfolio_overview
- biggest_positive_contributors
- biggest_negative_contributors
- key_evidence
- sector_observations
- evidence_gaps
- overall_assessment

For each important claim involving news, identify the relevant
ticker and briefly explain what the evidence says.

Remember that correlation/alignment is not proof of causation.

PORTFOLIO EVIDENCE:

{json.dumps(context, indent=2)}
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
    )

    content = response.choices[0].message.content

    if not content:
        raise RuntimeError("OpenAI returned an empty response.")

    return json.loads(content)


# ============================================================
# SAVE OUTPUT
# ============================================================

def save_narrative(narrative):
    output = {
        "generated_by": "OpenAI",
        "source": "portfolio_evidence.json",
        "narrative": narrative,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(
            output,
            f,
            indent=4,
            ensure_ascii=False,
        )


# ============================================================
# DISPLAY REPORT
# ============================================================

def print_report(narrative):
    print()
    print("=" * 70)
    print("AI PORTFOLIO NARRATIVE")
    print("=" * 70)

    overview = narrative.get("portfolio_overview")

    if overview:
        print()
        print("PORTFOLIO OVERVIEW")
        print("-" * 70)
        print(overview)

    print()
    print("BIGGEST POSITIVE CONTRIBUTORS")
    print("-" * 70)
    print(
        narrative.get(
            "biggest_positive_contributors",
            "None identified."
        )
    )

    print()
    print("BIGGEST NEGATIVE CONTRIBUTORS")
    print("-" * 70)
    print(
        narrative.get(
            "biggest_negative_contributors",
            "None identified."
        )
    )

    print()
    print("KEY EVIDENCE")
    print("-" * 70)
    print(
        narrative.get(
            "key_evidence",
            "None identified."
        )
    )

    print()
    print("SECTOR OBSERVATIONS")
    print("-" * 70)
    print(
        narrative.get(
            "sector_observations",
            "None identified."
        )
    )

    print()
    print("EVIDENCE GAPS")
    print("-" * 70)
    print(
        narrative.get(
            "evidence_gaps",
            "None identified."
        )
    )

    print()
    print("OVERALL ASSESSMENT")
    print("-" * 70)
    print(
        narrative.get(
            "overall_assessment",
            "None available."
        )
    )

    print()
    print("=" * 70)


# ============================================================
# MAIN
# ============================================================

def main():
    print()
    print("=" * 70)
    print("STARTING RAG + OPENAI PORTFOLIO ANALYSIS")
    print("=" * 70)

    print()
    print("Loading portfolio evidence...")

    data = load_evidence()

    print("Evidence loaded successfully.")

    print("Building retrieved context...")

    context = build_retrieved_context(data)

    print("Retrieved context ready.")

    print("Sending grounded evidence to OpenAI...")

    narrative = generate_narrative(context)

    print("Narrative generated successfully.")

    save_narrative(narrative)

    print()
    print(f"Saved: {OUTPUT_FILE}")

    print_report(narrative)


if __name__ == "__main__":
    main()