"""Chat with the career bot in your terminal.

Run:  python cli.py
"""

import re

from careerbot import CareerBot


def plain(text: str) -> str:
    """Strip the **bold** markdown used by the web UI."""
    return re.sub(r"\*\*(.+?)\*\*", r"\1", text)


def main() -> None:
    bot = CareerBot()
    print("CareerBot (type 'help' for commands, 'quit' to exit)\n")
    print("Bot:", plain(bot.greeting()))
    while True:
        try:
            msg = input("\nYou: ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if msg.strip().lower() in {"quit", "exit"}:
            break
        print("\nBot:", plain(bot.reply(msg)))
    print("Goodbye!")


if __name__ == "__main__":
    main()
