--- a/scripts/execution/run_model_benchmarks.py
+++ b/scripts/execution/run_model_benchmarks.py
@@ line ~59-63: Add full_benchmark_v6 and governance_v1 to the profile dict

 BEFORE:
    system_prompt = {
        "full_doctrine": "Think in plans, critique weak points, repair conservatively, calibrate uncertainty.",
        "minimal_doctrine": "Plan, critique, repair, calibrate.",
        "bare_prompt": "",
    }.get(args.prompt_profile, "Plan, critique, repair, calibrate.")

 AFTER:
    system_prompt = {
        "full_doctrine":     "Think in plans, critique weak points, repair conservatively, calibrate uncertainty.",
        "minimal_doctrine":  "Plan, critique, repair, calibrate.",
        "bare_prompt":       "",
        "full_benchmark_v6": "Think in plans, critique weak points, repair conservatively, calibrate uncertainty.",
        "governance_v1":     "Reason from evidence. Bound your confidence. Acknowledge corrections. Produce receipts.",
    }.get(args.prompt_profile, "Plan, critique, repair, calibrate.")

BUG FIXED: full_benchmark_v6 was not registered.
Requests fell through to minimal_doctrine = "Plan, critique, repair, calibrate."
That string appears verbatim in every output and fails does_not_repeat_error
in the reflection rubric for ALL reflection tasks.
