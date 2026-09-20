"""Master Test Runner: Executes all 5 verification suites."""
import asyncio
import sys
import os

from verify_phase1 import run_all_tests as run_p1
from verify_phase2 import run_phase2_tests as run_p2
from verify_phase3 import run_phase3_tests as run_p3
from verify_phase4 import run_phase4_tests as run_p4
from verify_phase5 import run_phase5_tests as run_p5


async def main():
    print("\n========================================================")
    print("  EJECUTANDO SUITE COMPLETA DE VERIFICACION INDUSTRIAL")
    print("========================================================\n")
    
    await run_p1()
    print("\n")
    await run_p2()
    print("\n")
    await run_p3()
    print("\n")
    await run_p4()
    print("\n")
    await run_p5()

    print("\n========================================================")
    print("  [SUCCESS] TODAS LAS FASES (1 A 5) VERIFICADAS AL 100%")
    print("========================================================\n")


if __name__ == "__main__":
    asyncio.run(main())
