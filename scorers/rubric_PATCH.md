--- a/scorers/rubric.py
+++ b/scorers/rubric.py

=== FIX: rubric scorer prefix strip ===

BUG: The exemplar adapter emits multi-line output:
    "Think in plans, critique weak points...\nCapability: reflection\n[actual answer]"
The old strip only removed from "Capability:" forward, leaving the system_prompt
line as part of the answer text. This caused:
  - is_boilerplate checks to fire falsely (system prompt matched boilerplate phrases)
  - does_not_repeat_error to fire (system prompt contained "repair, calibrate")
  - topically_relevant to fail (system prompt tokens polluted the overlap count)

BEFORE (in score_record function, around line 128):
    text = (output_text or "").strip()
    # Strip the adapter's "Capability: X\n" prefix and "Supporting patterns:" suffix
    if text.lower().startswith("capability:"):
        text = text.split("\n", 1)[-1].strip()

AFTER:
    text = (output_text or "").strip()
    # Strip the adapter's system-prompt + "Capability: X\n" prefix universally.
    # The exemplar adapter prepends: system_prompt\nCapability: X\n[answer]
    # We strip all lines up to and including the "Capability:" line.
    lines = text.splitlines()
    cap_idx = next(
        (i for i, l in enumerate(lines) if l.strip().lower().startswith("capability:")),
        None,
    )
    if cap_idx is not None:
        text = "\n".join(lines[cap_idx + 1:]).strip()
    if not text:
        # Fallback: use full text if stripping removed everything
        text = (output_text or "").strip()

This correctly handles both single-line and multi-line prefixes.
