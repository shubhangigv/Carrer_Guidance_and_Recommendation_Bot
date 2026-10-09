"""Flask web app exposing the career bot as a chat UI and a JSON API.

Run:  python app.py   then open http://127.0.0.1:5000
"""

import os

from flask import Flask, jsonify, render_template, request, session

from careerbot import CareerBot, CareerRecommender, UserProfile
from careerbot.recommender import parse_education, parse_list

app = Flask(__name__, template_folder="careerbot/templates", static_folder="careerbot/static")
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

recommender = CareerRecommender()


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/chat")
def chat():
    data = request.get_json(silent=True) or {}
    message = str(data.get("message", ""))[:500]
    if data.get("start"):
        bot = CareerBot(recommender)
        reply = bot.greeting()
    else:
        bot = CareerBot.from_state(session.get("bot"), recommender)
        reply = bot.reply(message)
    session["bot"] = bot.to_state()
    return jsonify({"reply": reply, "done": bot.finished_questions})


@app.post("/api/recommend")
def recommend():
    """Stateless endpoint: send a full profile, get recommendations back."""
    data = request.get_json(silent=True) or {}
    profile = UserProfile(
        name=str(data.get("name", "")),
        education=parse_education(str(data.get("education", ""))),
        skills=parse_list(data.get("skills")),
        interests=parse_list(data.get("interests")),
        subjects=parse_list(data.get("subjects")),
        work_style=parse_list(data.get("work_style")),
    )
    top_n = max(1, min(int(data.get("top_n", 3)), 10))
    return jsonify([r.to_dict() for r in recommender.recommend(profile, top_n)])


@app.get("/api/careers")
def careers():
    return jsonify(recommender.careers)


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
