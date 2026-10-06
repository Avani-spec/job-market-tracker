from jobtracker.skills import classify_role, extract_skills


def s(text):
    return set(extract_skills(text))


def test_basic_and_aliases():
    assert s("We use Python 3, k8s, Postgres and AWS.") == {"Python", "Kubernetes", "PostgreSQL", "AWS"}


def test_symbols_preserved():
    assert {"C++", "C#", ".NET", "Node.js", "CI/CD"} <= s("Stack: C++, C#, .NET 8, Node.js; CI/CD via GitHub Actions")


def test_multiword_and_react_native():
    found = s("Mobile engineer, React Native and machine learning")
    assert "React Native" in found and "Machine Learning" in found and "React" not in found
    assert {"React", "React Native"} <= s("React for web, React Native for mobile, plus React hooks")


def test_ambiguous_languages():
    assert "Go" in s("Backend in Go and Python")
    assert "Go" in s("Our services are written in golang")
    assert "Go" not in s("You will go to customer sites")
    assert "Go" not in s("Go live in Q3")
    assert "R" in s("Experience with R, Python or SQL")
    assert "R" not in s("Section R of the handbook")
    assert "C" in s("Embedded C and C++")
    assert "Spark" in s("Spark and Kafka pipelines") and "Spark" not in s("a spark of curiosity")


def test_roles():
    assert classify_role("Senior Machine Learning Engineer") == "ML / AI"
    assert classify_role("Site Reliability Engineer") == "DevOps / SRE"
    assert classify_role("Software Engineer") == "Software (general)"


def test_slash_separated():
    assert {"Python", "Django", "CI/CD"} <= s("Python/Django services, CI/CD and R/Python analytics")
    assert "R" in s("R/Python analytics")
