from careerbot import CareerBot

ANSWERS = [
    "My name is Priya",
    "12th",
    "art, design, technology",
    "drawing, creativity, communication",
    "arts, computer science",
    "creative, team",
]


def run_conversation():
    bot = CareerBot()
    replies = [bot.reply(a) for a in ANSWERS]
    return bot, replies


def test_full_conversation_produces_recommendations():
    bot, replies = run_conversation()
    assert bot.profile.name == "Priya"
    assert bot.profile.education == "high school"
    assert bot.finished_questions
    assert "top career matches" in replies[-1]
    assert bot.results[0].career["category"] == "Design"


def test_invalid_education_reasks():
    bot = CareerBot()
    bot.reply("Arjun")
    reply = bot.reply("banana")
    assert "didn't catch" in reply
    assert bot.step == 1


def test_follow_up_questions():
    bot, _ = run_conversation()
    assert "Roadmap" in bot.reply("roadmap for #1")
    assert "LPA" in bot.reply("salary of lawyer")
    assert "Resources" in bot.reply("resources for data scientist")
    assert "Software Engineer" in bot.reply("careers in technology")
    assert "Technology" in bot.reply("categories")


def test_restart():
    bot, _ = run_conversation()
    bot.reply("restart")
    assert bot.step == 0 and bot.profile.name == ""


def test_state_round_trip():
    bot, _ = run_conversation()
    clone = CareerBot.from_state(bot.to_state())
    assert clone.profile == bot.profile
    assert [r.career["id"] for r in clone.results] == [r.career["id"] for r in bot.results]
