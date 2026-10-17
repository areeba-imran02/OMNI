from app import classify_task, verify_result

def test_classify_diagram():
    assert classify_task("Explain DNS with a flowchart") == "Diagram"

def test_verifier_detects_empty():
    checks = verify_result("", "Learning")
    assert checks[0][1] is False

def test_verifier_mermaid():
    text = "Here is a diagram:\n```mermaid\nflowchart TD\n A-->B\n```"
    checks = verify_result(text, "Diagram")
    assert checks[-1][1] is True
