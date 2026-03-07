"""
CLI Entry Point — Multi-Agent AI System
Usage:
    python main.py                     # interactive mode
    python main.py "your question"     # single-shot mode
    python main.py --agents claude,gpt "your question"
"""
import sys
import os
import argparse
import textwrap

# ── Load .env before importing anything that needs API keys ────────────────────
from dotenv import load_dotenv
load_dotenv()

# ── Make sure imports work from any working directory ─────────────────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from orchestrator.orchestrator import Orchestrator, OrchestratorResult


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

AGENT_COLORS = {
    "Claude":  "\033[94m",   # blue
    "GPT-4":   "\033[92m",   # green
    "Gemini":  "\033[93m",   # yellow
    "Llama":   "\033[91m",   # orange/red
}
RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[92m"
CYAN   = "\033[96m"
YELLOW = "\033[93m"
RED    = "\033[91m"
DIM    = "\033[2m"


def print_banner():
    banner = f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════════╗
║         🤖  Multi-Agent AI System  🤖                    ║
║  Claude · GPT-4 · Gemini · Llama  →  Orchestrated Answer ║
╚══════════════════════════════════════════════════════════╝{RESET}
"""
    print(banner)


def print_agent_response(r):
    color = AGENT_COLORS.get(r.agent_name, CYAN)
    status = f"{GREEN}✅ Success{RESET}" if r.success else f"{RED}❌ Failed{RESET}"
    print(f"\n{color}{BOLD}┌─── {r.agent_name} ({r.role}) {RESET}")
    print(f"{color}│{RESET} Model: {DIM}{r.model}{RESET}  "
          f"Latency: {DIM}{r.latency_seconds}s{RESET}  "
          f"Tokens: {DIM}{r.tokens_used:,}{RESET}  "
          f"Cost: {DIM}${r.cost_usd:.6f}{RESET}  {status}")
    print(f"{color}└{'─'*60}{RESET}")
    if r.success:
        # Wrap long lines for readability
        for line in r.content.splitlines():
            wrapped = textwrap.fill(line, width=90, subsequent_indent="  ") if line.strip() else ""
            print(wrapped or "")
    else:
        print(f"{RED}  Error: {r.error}{RESET}")


def print_final_answer(result: OrchestratorResult):
    print(f"\n{BOLD}{GREEN}{'═'*65}")
    print("  ✨  FINAL SYNTHESISED ANSWER")
    print(f"{'═'*65}{RESET}\n")
    for line in result.final_answer.splitlines():
        # Bold markdown headers
        if line.startswith("#"):
            print(f"{BOLD}{CYAN}{line}{RESET}")
        elif line.startswith("**") and line.endswith("**"):
            print(f"{BOLD}{line[2:-2]}{RESET}")
        else:
            wrapped = textwrap.fill(line, width=90, subsequent_indent="  ") if line.strip() else ""
            print(wrapped or "")
    print(f"\n{BOLD}{GREEN}{'═'*65}{RESET}")


def print_summary(result: OrchestratorResult):
    print(f"\n{BOLD}{YELLOW}📊 Run Summary{RESET}")
    print(f"  Agents used   : {', '.join(result.agents_used)}")
    print(f"  Total tokens  : {result.total_tokens:,}")
    print(f"  Total cost    : ${result.total_cost_usd:.6f} USD")
    print(f"  Total latency : {result.total_latency_seconds}s")
    if result.errors:
        print(f"\n{RED}  ⚠️  Errors:{RESET}")
        for err in result.errors:
            print(f"  - {err}")


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def run_query(orchestrator: Orchestrator, query: str, show_agents: bool = True):
    print(f"\n{BOLD}🔎 Query:{RESET} {query}")
    print(f"{DIM}Running {len(orchestrator.agents)} agent(s) in parallel...{RESET}")

    result = orchestrator.run(query)

    if show_agents:
        print(f"\n{BOLD}{'━'*65}")
        print("  📋  INDIVIDUAL AGENT OUTPUTS")
        print(f"{'━'*65}{RESET}")
        for r in result.agent_responses:
            print_agent_response(r)

    print_final_answer(result)
    print_summary(result)
    return result


def interactive_mode(orchestrator: Orchestrator):
    print(f"\n{CYAN}Interactive mode — type your question (or 'quit' to exit, 'clear' to reset){RESET}")
    while True:
        try:
            query = input(f"\n{BOLD}You>{RESET} ").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{DIM}Goodbye!{RESET}")
            break

        if not query:
            continue
        if query.lower() in {"quit", "exit", "q"}:
            print(f"{DIM}Goodbye!{RESET}")
            break
        if query.lower() == "clear":
            os.system("cls" if os.name == "nt" else "clear")
            print_banner()
            continue
        if query.lower() == "cost":
            orchestrator.cost_tracker.print_summary()
            continue
        if query.lower() == "agents":
            for k, a in orchestrator.agents.items():
                print(f"  {k:10s} → {a}")
            continue

        run_query(orchestrator, query)


def main():
    parser = argparse.ArgumentParser(
        description="Multi-Agent AI System — combines Claude, GPT-4, Gemini, and Llama",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Examples:
          python main.py
          python main.py "How does quantum computing work?"
          python main.py --agents claude,gemini "Fact-check climate change statistics"
          python main.py --agents llama "Write a binary search in Python"
          python main.py --no-agents "What is machine learning?" 
        """),
    )
    parser.add_argument("query", nargs="?", help="Question to ask (omit for interactive mode)")
    parser.add_argument(
        "--agents", "-a",
        help="Comma-separated list of agents: claude,gpt,gemini,llama (default: all available)",
        default=None,
    )
    parser.add_argument(
        "--no-agent-output", action="store_true",
        help="Skip printing individual agent outputs (only show final answer)",
    )
    args = parser.parse_args()

    print_banner()

    # Parse agent list
    agent_list = None
    if args.agents:
        agent_list = [a.strip().lower() for a in args.agents.split(",")]

    # Check which API keys are set
    key_map = {
        "claude": "ANTHROPIC_API_KEY",
        "gpt":    "OPENAI_API_KEY",
        "gemini": "GOOGLE_API_KEY",
        "llama":  "GROQ_API_KEY",
    }
    print(f"{BOLD}API Key Status:{RESET}")
    for key, env_var in key_map.items():
        val = os.getenv(env_var)
        status = f"{GREEN}✅ Set{RESET}" if val else f"{RED}❌ Missing — set {env_var} in .env{RESET}"
        print(f"  {key:8s} → {status}")

    print(f"\n{DIM}Loading agents...{RESET}")
    orchestrator = Orchestrator(available_agents=agent_list)

    if not orchestrator.agents:
        print(f"\n{RED}❌ No agents loaded! Please set at least one API key in your .env file.{RESET}")
        print("\nRequired environment variables:")
        for k, v in key_map.items():
            print(f"  {v}=your_key_here")
        sys.exit(1)

    show_agents = not args.no_agent_output

    if args.query:
        # Single-shot mode
        run_query(orchestrator, args.query, show_agents=show_agents)
    else:
        # Interactive REPL
        interactive_mode(orchestrator)

    orchestrator.cost_tracker.print_summary()


if __name__ == "__main__":
    main()
