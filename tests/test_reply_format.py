"""Tests for reply closing and paragraph normalization."""

from app.utils.reply_format import normalize_reply_closing, prepare_reply_text


def test_removes_your_name_placeholder() -> None:
    raw = "Thanks for reaching out.\n\nBest regards,\n[Your Name]"
    out = prepare_reply_text(raw)
    assert "[Your Name]" not in out
    assert "Best regards," in out


def test_splits_inline_closing_after_sentence() -> None:
    raw = "We will investigate shortly. Best regards, Support Team"
    out = normalize_reply_closing(raw)
    assert "investigate shortly." in out
    assert out.index("investigate shortly.") < out.index("Best regards,")


def test_splits_salutation_from_body() -> None:
    raw = (
        "Dear People Ops, thank you for letting me know that my kit shipped. "
        "I will track RB772991US.\n\nBest regards,\nSupport Team"
    )
    out = prepare_reply_text(raw)
    assert out.startswith("Dear People Ops,\n\n")
    assert "Thank you" in out
    assert out.index("Thank you") < out.index("Best regards,")


def test_splits_best_regards_comma_signature() -> None:
    raw = "Done.\n\nBest regards, Support Team"
    out = normalize_reply_closing(raw)
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    assert lines[-2].lower().startswith("best regards")
    assert lines[-1] == "Support Team"
