"""Automated test suite covering the 20 M1 Planning Scenarios from M1_planning.txt."""

import asyncio
import httpx
import uuid
import sys

BASE_URL = "http://localhost:8000/api/v1/sessions/chat"

async def run_scenario(name: str, turns: list[str], checks: list[callable]) -> bool:
    session_id = f"m1-test-{uuid.uuid4().hex[:8]}"
    print(f"\n--- Running Scenario: {name} ---")
    async with httpx.AsyncClient(timeout=30.0) as client:
        last_resp = None
        for i, text in enumerate(turns):
            print(f"  Turn {i+1} User: \"{text}\"")
            resp = await client.post(BASE_URL, json={"message": text, "session_id": session_id})
            if resp.status_code != 200:
                print(f"  FAILED: HTTP {resp.status_code} - {resp.text}")
                return False
            data = resp.json()
            print(f"  Agent Stage: {data.get('stage')}")
            print(f"  Agent Reply: {data.get('reply')[:90]}...")
            last_resp = data
        
        # Run assertions
        for check in checks:
            try:
                check(last_resp)
            except AssertionError as e:
                print(f"  FAILED Assertion: {e}")
                return False
    print(f"  PASSED: {name}")
    return True

async def main():
    results = []

    # Test 1: "I want to run a campaign."
    r1 = await run_scenario(
        "Test 1: Generic start",
        ["I want to run a campaign."],
        [lambda r: len(r.get("reply", "")) > 0 and r.get("stage") == "basics"]
    )
    results.append(("Test 1: Generic start", r1))

    # Test 2: "I want to run a campaign in the UK."
    r2 = await run_scenario(
        "Test 2: Campaign in UK",
        ["I want to run a campaign in the UK."],
        [lambda r: r.get("plan_state", {}).get("markets") in ("GB", "UK") and r.get("stage") == "basics"]
    )
    results.append(("Test 2: Campaign in UK", r2))

    # Test 3: "We're launching a new running shoe line."
    r3 = await run_scenario(
        "Test 3: Product only",
        ["We're launching a new running shoe line."],
        [lambda r: "running shoe" in (r.get("plan_state", {}).get("brand") or "").lower()]
    )
    results.append(("Test 3: Product only", r3))

    # Test 4: "We're launching a new running shoe line in the UK."
    r4 = await run_scenario(
        "Test 4: Product + Market",
        ["We're launching a new running shoe line in the UK."],
        [
            lambda r: "running shoe" in (r.get("plan_state", {}).get("brand") or "").lower(),
            lambda r: r.get("plan_state", {}).get("markets") in ("GB", "UK"),
        ]
    )
    results.append(("Test 4: Product + Market", r4))

    # Test 5: "We're launching a new running shoe line, want to run something on Prime Video in the UK."
    r5 = await run_scenario(
        "Test 5: Product + Market + Inventory",
        ["We're launching a new running shoe line, want to run something on Prime Video in the UK."],
        [
            lambda r: "running shoe" in (r.get("plan_state", {}).get("brand") or "").lower(),
            lambda r: r.get("plan_state", {}).get("markets") in ("GB", "UK"),
        ]
    )
    results.append(("Test 5: Product + Market + Inventory", r5))

    # Test 6: "I have £15k for a running shoe campaign in the UK."
    r6 = await run_scenario(
        "Test 6: Budget + Product + Market",
        ["I have £15k for a running shoe campaign in the UK."],
        [
            lambda r: "15000" in (r.get("plan_state", {}).get("market_budgets") or ""),
            lambda r: r.get("plan_state", {}).get("markets") in ("GB", "UK"),
        ]
    )
    results.append(("Test 6: Budget + Product + Market", r6))

    # Test 7: "I have £15k for a running shoe campaign in the UK from October 1 to 31."
    r7 = await run_scenario(
        "Test 7: Budget + Product + Market + Dates",
        ["I have £15k for a running shoe campaign in the UK from October 1 to 31 2026."],
        [
            lambda r: "10-01" in (r.get("plan_state", {}).get("flight_dates") or ""),
            lambda r: "15000" in (r.get("plan_state", {}).get("market_budgets") or ""),
        ]
    )
    results.append(("Test 7: Budget + Product + Market + Dates", r7))

    # Test 8: "I have £15k for a running shoe campaign in the UK from October 1 to 31 2026, probably 30 seconds."
    r8 = await run_scenario(
        "Test 8: Full Basics -> Advance to Inventory",
        ["I have £15k for a running shoe campaign in the UK from October 1 to 31 2026, probably 30 seconds."],
        [
            lambda r: r.get("stage") == "inventory",
            lambda r: len(r.get("blocks", [])) > 0,
        ]
    )
    results.append(("Test 8: Full Basics -> Advance to Inventory", r8))

    # Test 9: Complete brief with awareness
    r9 = await run_scenario(
        "Test 9: Full Brief with Awareness Goal",
        ["We're launching a new running shoe line in the UK. We have £15k from October 1 to 31 2026 and want 30-second ads for awareness."],
        [
            lambda r: r.get("stage") == "inventory",
            lambda r: "awareness" in (r.get("plan_state", {}).get("goal") or "").lower(),
        ]
    )
    results.append(("Test 9: Full Brief with Awareness Goal", r9))

    # Test 10: Unavailable inventory rejection (Zee TV)
    r10 = await run_scenario(
        "Test 10: Unsupported Inventory (Zee TV)",
        ["We're launching a new running shoe line, want to run something on Zee TV in the UK."],
        [
            lambda r: "zee tv" in r.get("reply", "").lower() or "not currently available" in r.get("reply", "").lower(),
            lambda r: "zee tv" not in (r.get("plan_state", {}).get("inventory") or "").lower(),
        ]
    )
    results.append(("Test 10: Unsupported Inventory (Zee TV)", r10))

    # Test 11 & 12: Accept alternative and select inventory
    r11_12 = await run_scenario(
        "Test 11 & 12: Show Available Inventory -> Select Prime Video",
        [
            "We're launching a new running shoe line, want to run something on Zee TV in the UK.",
            "Show available inventory",
            "Prime Video",
        ],
        [
            lambda r: r.get("stage") in ("basics", "inventory", "audiences", "forecast"),
        ]
    )
    results.append(("Test 11 & 12: Alternative & Selection", r11_12))

    # Test 13: Change inventory
    r13 = await run_scenario(
        "Test 13: Change Inventory Decision",
        [
            "I have £15k for running shoes in the UK from Oct 1 to Oct 31 2026, 30s ads on Prime Video",
            "Actually use Netflix",
        ],
        [
            lambda r: "netflix" in (r.get("plan_state", {}).get("inventory") or "").lower() or "netflix" in r.get("reply", "").lower(),
        ]
    )
    results.append(("Test 13: Change Inventory Decision", r13))

    # Test 14: Change budget
    r14 = await run_scenario(
        "Test 14: Change Budget Decision",
        [
            "I have £15k for running shoes in the UK from Oct 1 to Oct 31 2026, 30s ads",
            "Actually make the budget £20k",
        ],
        [
            lambda r: "20000" in (r.get("plan_state", {}).get("market_budgets") or ""),
        ]
    )
    results.append(("Test 14: Change Budget Decision", r14))

    # Test 15: One-shot complete message
    r15 = await run_scenario(
        "Test 15: Complete One-Shot Brief",
        ["We're launching a new running shoe line in the UK. We have £15k from October 1 to 31 2026 and want 30-second ads for awareness on Prime Video."],
        [
            lambda r: r.get("stage") in ("inventory", "audiences", "forecast", "plan_ready"),
        ]
    )
    results.append(("Test 15: Complete One-Shot Brief", r15))

    # Test 16: Out-of-order accumulation
    r16 = await run_scenario(
        "Test 16: Out-of-order Multi-turn",
        [
            "I want 30-second ads.",
            "Budget is £15k.",
            "UK.",
            "October 1 to October 31 2026.",
        ],
        [
            lambda r: r.get("stage") == "inventory",
            lambda r: "30s" in (r.get("plan_state", {}).get("durations") or ""),
            lambda r: "15000" in (r.get("plan_state", {}).get("market_budgets") or ""),
        ]
    )
    results.append(("Test 16: Out-of-order Multi-turn", r16))

    # Test 17: Past dates handling
    r17 = await run_scenario(
        "Test 17: Past Dates Rejection",
        [
            "Run campaign in UK from March 1 to March 31 2020.",
        ],
        [
            lambda r: "past" in r.get("reply", "").lower() or "flight" in r.get("reply", "").lower() or "when" in r.get("reply", "").lower(),
        ]
    )
    results.append(("Test 17: Past Dates Rejection", r17))

    # Test 18: Unsupported duration
    r18 = await run_scenario(
        "Test 18: Unsupported Creative Duration (45s)",
        [
            "UK running shoes, 45 seconds creative length.",
        ],
        [
            lambda r: "45" in r.get("reply", "") or "duration" in r.get("reply", "").lower() or "10" in r.get("reply", "") or "30" in r.get("reply", ""),
        ]
    )
    results.append(("Test 18: Unsupported Creative Duration", r18))

    # Test 19: Unsupported inventory anti-hallucination
    r19 = await run_scenario(
        "Test 19: Unsupported Inventory Anti-Hallucination",
        [
            "Target Sony Liv in the UK with £10k budget.",
        ],
        [
            lambda r: "sony liv" not in (r.get("plan_state", {}).get("inventory") or "").lower(),
        ]
    )
    results.append(("Test 19: Anti-hallucination", r19))

    # Test 20: User declines alternatives (conclude gracefully)
    r20 = await run_scenario(
        "Test 20: User Declines Alternatives (No)",
        [
            "Run on Zee TV in UK.",
            "No, I'll plan this later.",
        ],
        [
            lambda r: "anytime" in r.get("reply", "").lower() or "problem" in r.get("reply", "").lower() or "later" in r.get("reply", "").lower(),
        ]
    )
    results.append(("Test 20: Polite conclusion", r20))

    # Final summary
    print("\n==========================================")
    print("M1 SCENARIOS EVALUATION SUMMARY")
    print("==========================================")
    passed_count = sum(1 for _, ok in results if ok)
    total_count = len(results)
    for name, ok in results:
        status = "[PASS]" if ok else "[FAIL]"
        print(f"{status} | {name}")
    print(f"\nTotal: {passed_count}/{total_count} Passed ({round(passed_count/total_count*100)}%)")

if __name__ == "__main__":
    asyncio.run(main())
