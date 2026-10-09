from careerbot.recommender import CareerRecommender, UserProfile, parse_education, parse_list


def test_parse_list_normalises_synonyms():
    assert parse_list("Coding, maths and AI") == ["programming", "mathematics", "artificial intelligence"]


def test_parse_education():
    assert parse_education("I'm in 12th") == "high school"
    assert parse_education("B.Tech 2nd year") == "bachelor"
    assert parse_education("MBA") == "master"
    assert parse_education("polytechnic diploma") == "diploma"
    assert parse_education("banana") is None


def test_tech_profile_gets_tech_careers():
    rec = CareerRecommender()
    profile = UserProfile(
        education="bachelor",
        skills=parse_list("coding, problem solving, maths"),
        interests=parse_list("technology, AI, data"),
        subjects=parse_list("computer science, maths"),
        work_style=parse_list("analytical"),
    )
    titles = [r.career["title"] for r in rec.recommend(profile)]
    assert len(titles) == 3
    assert all(r.career["category"] == "Technology" for r in rec.recommend(profile))


def test_healthcare_profile():
    rec = CareerRecommender()
    profile = UserProfile(
        education="high school",
        skills=parse_list("empathy, communication, biology"),
        interests=parse_list("helping people, health, medicine"),
        subjects=parse_list("biology, chemistry"),
        work_style=parse_list("people"),
    )
    top = rec.recommend(profile)[0]
    assert top.career["category"] == "Healthcare"


def test_education_gap_adds_note():
    rec = CareerRecommender()
    career = rec.find("psychologist")
    r = rec.score(UserProfile(education="high school", interests=["psychology"]), career)
    assert "master" in r.education_note


def test_empty_profile_returns_nothing():
    assert CareerRecommender().recommend(UserProfile()) == []


def test_find():
    rec = CareerRecommender()
    assert rec.find("data scientist")["id"] == "data-scientist"
    assert rec.find("lawyer")["id"] == "lawyer"
    assert rec.find("astronaut") is None


def test_parse_education_abbreviation_boundaries():
    assert parse_education("M.Sc physics") == "master"
    assert parse_education("BCA final year") == "bachelor"
    assert parse_education("10th standard") == "high school"
