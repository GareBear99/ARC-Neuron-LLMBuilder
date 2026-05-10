--- a/scripts/execution/promote_candidate.py
+++ b/scripts/execution/promote_candidate.py

=== FIX 1: incumbent selection (use flag, not max score) ===

BEFORE:
    incumbent = max(
        promotable_models,
        key=lambda m: m.get("overall_weighted_score", 0.0),
        default=None,
    )

AFTER:
    # Find the current flagged incumbent first; fall back to highest score.
    # Bug: using max(score) caused the newly-added candidate to be selected
    # as the "incumbent" on a second run, making the gate compare the candidate
    # to itself (score == score -> "did not beat incumbent").
    _flagged = [m for m in promotable_models if m.get("incumbent", False)]
    incumbent = (
        _flagged[0] if _flagged
        else max(promotable_models, key=lambda m: m.get("overall_weighted_score", 0.0), default=None)
    )

=== FIX 2: always write calibration_error into scoreboard entries ===

Find the block that builds the scoreboard entry dict and ensure this line exists:
    "calibration_error": round(1.0 - summary.get("calibration", 1.0), 4),

Bug: calibration_error was never written. The regression check then read
    incumbent.get("calibration_error", 0.0) = 0.0
instead of the actual value (e.g. 0.10), making every candidate with
calibration_error > 0.03 look like a regression when it was actually improving.

=== FIX 3: retroactively patch existing scoreboard entries ===

After loading scoreboard.json, add this migration block:
    for m in sb["models"]:
        if "calibration" in m and "calibration_error" not in m:
            m["calibration_error"] = round(1.0 - m["calibration"], 4)
