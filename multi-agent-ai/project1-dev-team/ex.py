import os
import json
import asyncio
from pathlib import Path
from typing import Dict, Any

from dotenv import load_dotenv
from google import genai
from google.genai import types


# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise ValueError(
        "GEMINI_API_KEY not found in .env file"
    )

client = genai.Client(api_key=API_KEY)

MODEL = "gemini-3.5-flash-lite"

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)


# ============================================================
# GEMINI HELPER
# ============================================================

def ask_agent(
    role: str,
    task: str,
    context: str = "",
    retries: int = 3
) -> str:

    prompt = f"""
You are an AI agent in a multi-agent software
development system.

YOUR ROLE:
{role}

YOUR TASK:
{task}

CONTEXT FROM OTHER AGENTS:
{context}

Rules:
1. Stay within your responsibility.
2. Do not invent information unnecessarily.
3. Be technically precise.
4. Produce useful output for the next agent.
"""

    for attempt in range(retries):

        try:

            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=5000
                )
            )

            if response.text:
                return response.text.strip()

        except Exception as error:

            print(
                f"[Retry {attempt + 1}/{retries}] "
                f"{role} failed: {error}"
            )

    return f"{role} failed after {retries} attempts."


# ============================================================
# SHARED STATE
# ============================================================

state: Dict[str, Any] = {
    "requirement": "",
    "research": "",
    "architecture": "",
    "analysis": "",
    "code": "",
    "tests": "",
    "review": "",
    "final_report": ""
}


# ============================================================
# AGENTS
# ============================================================

async def researcher():

    state["research"] = await asyncio.to_thread(
        ask_agent,
        "Software Researcher",
        """
Analyze the software requirement.

Identify:
- Functional requirements
- Non-functional requirements
- Important technologies
- APIs
- Database requirements
- Security concerns
- Edge cases
""",
        state["requirement"]
    )

    print("✓ Researcher completed")


async def analyst():

    state["analysis"] = await asyncio.to_thread(
        ask_agent,
        "Requirements Analyst",
        """
Convert the requirement into a clear technical specification.

Include:
- User stories
- Main features
- Inputs
- Outputs
- Validation rules
- Error cases
- Acceptance criteria
""",
        state["requirement"]
    )

    print("✓ Analyst completed")


async def architect():

    context = f"""
RESEARCH:

{state["research"]}

REQUIREMENTS:

{state["analysis"]}
"""

    state["architecture"] = await asyncio.to_thread(
        ask_agent,
        "Software Architect",
        """
Design the system architecture.

Include:
- Components
- API endpoints
- Database design
- Data flow
- Authentication
- Error handling
- Folder structure
- Important design decisions
""",
        context
    )

    print("✓ Architect completed")


async def developer():

    context = f"""
REQUIREMENTS:

{state["analysis"]}

ARCHITECTURE:

{state["architecture"]}
"""

    state["code"] = await asyncio.to_thread(
        ask_agent,
        "Senior Python Developer",
        """
Implement the proposed system.

Provide production-style Python code.

Include:
- Project structure
- Important source files
- Classes/functions
- Validation
- Error handling
- Database integration where appropriate

The code should be realistic and runnable.
""",
        context
    )

    print("✓ Developer completed")


async def tester():

    context = f"""
REQUIREMENTS:

{state["analysis"]}

CODE:

{state["code"]}
"""

    state["tests"] = await asyncio.to_thread(
        ask_agent,
        "Senior QA Automation Engineer",
        """
Design a comprehensive testing strategy.

Include:
- Unit tests
- Integration tests
- API tests
- Negative tests
- Boundary tests
- Security tests
- Example pytest tests
""",
        context
    )

    print("✓ Tester completed")


async def reviewer():

    context = f"""
REQUIREMENTS:

{state["analysis"]}

ARCHITECTURE:

{state["architecture"]}

CODE:

{state["code"]}

TESTS:

{state["tests"]}
"""

    state["review"] = await asyncio.to_thread(
        ask_agent,
        "Senior Code Reviewer",
        """
Review the complete implementation.

Find:
- Bugs
- Architecture problems
- Security problems
- Missing validation
- Missing tests
- Poor coding practices
- Scalability problems

Give a severity:

CRITICAL
HIGH
MEDIUM
LOW

Do not blindly approve the implementation.
""",
        context
    )

    print("✓ Reviewer completed")


async def final_reviewer():

    context = f"""
REQUIREMENT:
{state["requirement"]}

RESEARCH:
{state["research"]}

ARCHITECTURE:
{state["architecture"]}

CODE:
{state["code"]}

TESTS:
{state["tests"]}

CODE REVIEW:
{state["review"]}
"""

    state["final_report"] = await asyncio.to_thread(
        ask_agent,
        "Engineering Manager",
        """
Create the final engineering report.

Include:

1. Project summary
2. Requirements
3. Architecture
4. Implementation summary
5. Testing strategy
6. Review findings
7. Critical problems
8. Recommended improvements
9. Final development status

Be honest about problems.
""",
        context
    )

    print("✓ Final reviewer completed")


# ============================================================
# SAVE RESULTS
# ============================================================

def save_results():

    files = {
        "research.md": state["research"],
        "requirements.md": state["analysis"],
        "architecture.md": state["architecture"],
        "code.md": state["code"],
        "tests.md": state["tests"],
        "review.md": state["review"],
        "final_report.md": state["final_report"]
    }

    for filename, content in files.items():

        path = OUTPUT_DIR / filename

        path.write_text(
            content,
            encoding="utf-8"
        )

    print("\nAll artifacts saved in ./output/")


# ============================================================
# MAIN WORKFLOW
# ============================================================

async def main():

    print("=" * 60)
    print("MULTI-AGENT SOFTWARE DEVELOPMENT TEAM")
    print("=" * 60)

    state["requirement"] = input(
        "\nEnter your software requirement:\n> "
    )

    print("\nStarting multi-agent workflow...\n")

    # --------------------------------------------------------
    # STEP 1
    # Independent agents execute in parallel
    # --------------------------------------------------------

    await asyncio.gather(
        researcher(),
        analyst()
    )

    # --------------------------------------------------------
    # STEP 2
    # Architect depends on research + analysis
    # --------------------------------------------------------

    await architect()

    # --------------------------------------------------------
    # STEP 3
    # Developer depends on architecture
    # --------------------------------------------------------

    await developer()

    # --------------------------------------------------------
    # STEP 4
    # Tester depends on developer output
    # --------------------------------------------------------

    await tester()

    # --------------------------------------------------------
    # STEP 5
    # Reviewer
    # --------------------------------------------------------

    await reviewer()

    # --------------------------------------------------------
    # STEP 6
    # Final synthesis
    # --------------------------------------------------------

    await final_reviewer()

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    save_results()

    print("\n" + "=" * 60)
    print("FINAL REPORT")
    print("=" * 60)

    print(state["final_report"])


if __name__ == "__main__":
    asyncio.run(main())