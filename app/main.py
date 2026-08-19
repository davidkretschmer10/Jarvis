import multiprocessing
import sys

from core.startup import ensure_ai_engine_started, ensure_pc_agent_started


def main():
    print("Starting Jarvis system")
    ensure_ai_engine_started()
    ensure_pc_agent_started()

    print("Starting Jarvis GUI...")
    import app.gui

    print("Jarvis started")


if __name__ == "__main__":
    multiprocessing.freeze_support()

    if len(sys.argv) > 1 and sys.argv[1] == "agent":
        from core import agent

        agent.app.run(port=5000, use_reloader=False)
        sys.exit()

    main()
