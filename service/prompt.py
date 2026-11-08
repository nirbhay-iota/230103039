"""Prompt format shared by training, evaluation and the service (no third-party imports)."""


def build_prompt(text):
    """The text the student sees. The training target continues right after "JSON:"."""
    return f"Command: {text.strip()}\nJSON:"


def build_target(teacher_json):
    """Training target: the teacher's JSON reply, with a leading space so it continues the prompt."""
    return " " + teacher_json.strip()
