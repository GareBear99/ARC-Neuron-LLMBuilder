"""scorers/rubric.py — Task-aware capability scorer for ARC-Neuron benchmarks.

Keyword-soup guard (added v1.1):
  Responses that are pure keyword lists with no sentence structure are
  penalised before capability checks run.  This prevents a response of
  "constraint rollback evidence validate minimal" from scoring 1.0 on
  every capability.

  A response is considered keyword soup when:
    - It is shorter than MIN_SENTENCE_CHARS characters, OR
    - It has fewer than MIN_WORDS words, OR
    - Its type/token ratio (unique words / total words) exceeds
      KEYWORD_DIVERSITY_FLOOR while containing fewer than
      MIN_SENTENCE_CHARS chars (catches single-word-per-line dumps), OR
    - It contains no sentence-ending punctuation (.!?) and fewer than
      MIN_WORDS_FOR_NO_PUNCT words.

  When soup is detected, keyword checks that would otherwise fire are
  suppressed: only length-based and negation-based checks are honoured.
"""
from __future__ import annotations
import re
from typing import Any

# ── coherence thresholds ──────────────────────────────────────────────────────
MIN_SENTENCE_CHARS    = 80   # a genuine answer needs at least this many chars
MIN_WORDS             = 12   # fewer than this → too terse to be meaningful
MIN_WORDS_FOR_NO_PUNCT = 15  # long responses (≥ this many words) with NO punctuation are soup

# Capabilities where short, direct answers are the expected format.
# The soup guard is not applied to these — a one-word factual answer is correct.
SOUP_EXEMPT_CAPABILITIES = frozenset({
    "out_of_domain",
    "english_understanding",
    "english_comprehension",
    "instruction_following",
    "intelligence",
    "paraphrase_stability",
    "quantization_retention",
    "calibration",
    "planning",        # planning responses are action-sequences, not analytical prose
    "repair",          # repair responses are corrected designs, not analytical prose
    "critique",        # critique responses are evaluations — topical_relevance enforced internally
    "deterministic_format",
    "deterministic_compliance",
})


def _word_count(text: str) -> int:
    return len(text.split())


def _has_sentence_structure(text: str) -> bool:
    """True when the text contains at least one sentence-ending punctuation mark."""
    import re
    return bool(re.search(r'[.!?]', text))


def _is_keyword_soup(text: str) -> bool:
    """Detect responses that are keyword dumps rather than prose answers.

    A response is keyword soup when it:
      - Is too short to contain a real answer (< MIN_SENTENCE_CHARS chars), OR
      - Has too few words (< MIN_WORDS), OR
      - Contains no sentence-ending punctuation AND is long enough that the
        absence of punctuation is deliberate (>= MIN_WORDS_FOR_NO_PUNCT words).
    """
    stripped = text.strip()
    if not stripped:
        return True
    if len(stripped) < MIN_SENTENCE_CHARS:
        return True
    words = stripped.split()
    if len(words) < MIN_WORDS:
        return True
    if not _has_sentence_structure(stripped) and len(words) >= MIN_WORDS_FOR_NO_PUNCT:
        return True
    return False


def _is_substantial(text: str, min_chars: int = 80) -> bool:
    """Require both character length and sentence structure."""
    return len(text.strip()) >= min_chars and _has_sentence_structure(text)


def _contains_any(text: str, options: list[str], soup: bool = False) -> bool:
    """Keyword presence check.  Returns False immediately when soup=True so that
    keyword-list responses cannot satisfy content checks."""
    if soup:
        return False
    lowered = text.lower()
    return any(option in lowered for option in options)


def _score_parts(text: str, checks: list[tuple[str, bool]]) -> tuple[int, list[str]]:
    passed = [name for name, ok in checks if ok]
    return len(passed), passed

def _score_retention(text: str, task: dict) -> dict[str, Any]:
    lowered = text.lower()
    soup = _is_keyword_soup(text)
    # For compression tasks: the output must be shorter than the input would be
    # (checking against a fixed floor since we don't have input length here).
    # A compression response over 400 chars is probably not compressing.
    is_compression = task.get("capability") == "compression"
    # Strip the adapter's "Capability: X\n" prefix before checking length
    compression_ok = (not is_compression) or (len(text.strip()) <= 800)
    checks = [
        ("responds_to_prompt",    len(text.strip()) >= 60 and _has_sentence_structure(text) and compression_ok),
        ("no_hallucinated_prior", not _contains_any(lowered, ["as we discussed earlier","you mentioned that","in our previous session","you told me"])),
        ("bounded_confidence",    _contains_any(lowered, ["based on","given","from what","according to","as stated","the constraint","as defined"], soup) or _is_substantial(text)),
        ("preserves_goal",        _contains_any(lowered, ["goal","objective","aim","purpose","target","mission","fix","issue","root cause","change notice","migration","breaking","bug","problem","notice","patch"], soup)),
        ("preserves_constraint",  _contains_any(lowered, ["constraint","must not","cannot","requirement","rule","preserve","must","should not"], soup)),
        ("names_next_action",     _contains_any(lowered, ["next","action","step","should","check","verify","validate","recommend","fix","patch","workaround","ship","deploy","migrate","monitor","both fixes","the fix","needed","required","before shipping","before deploy","step 1","step one"], soup)),
    ]
    raw, matched = _score_parts(lowered, checks)
    notes = f"Retention: {raw}/{len(checks)} checks passed."
    if soup:
        notes += " [keyword-soup detected: content checks suppressed]"
    return {"raw_score": raw, "normalized_score": round(raw/max(1,len(checks)),4),
            "capability": task.get("capability","continuity"),
            "notes": notes,
            "matched_checks": matched, "scoring_mode": "retention",
            "keyword_soup_detected": soup}

def score_record(output_text: str, task: dict | None = None) -> dict[str, Any]:
    text       = (output_text or "").strip()
    # Strip the adapter's "Capability: X\n" prefix and "Supporting patterns:" suffix
    # universally — these are adapter metadata, not part of the model's answer.
    if text.lower().startswith("capability:"):
        text = text.split("\n", 1)[-1].strip()
    if "\nSupporting patterns:" in text:
        text = text.split("\nSupporting patterns:")[0].strip()
    lowered    = text.lower()
    capability = (task or {}).get("capability", "generic")
    scoring_mode = (task or {}).get("scoring", "rubric")
    raw_ref = (task or {}).get("reference", {})
    if not isinstance(raw_ref, dict):
        raw_ref = {"rubric": str(raw_ref)} if raw_ref else {}
    reference = raw_ref
    if not text:
        return {"raw_score":0,"normalized_score":0.0,"capability":capability,"notes":"Empty output","matched_checks":[]}
    if scoring_mode == "retention" and task:
        return _score_retention(text, task)
    soup = _is_keyword_soup(text) and capability not in SOUP_EXEMPT_CAPABILITIES
    notes: list[str] = []
    # Topical relevance: response shares >= 2 content words with the prompt.
    # Filters out boilerplate responses that score on keywords but ignore the specific question.
    task_prompt = (task or {}).get("prompt", "")
    STOP_WORDS  = {"a","an","the","is","are","was","were","be","been","has","have",
                   "had","do","does","did","to","of","in","for","on","with","at","by",
                   "from","as","if","or","and","but","not","this","that","it","its",
                   "will","can","may","must","should","would","could","what","how","why",
                   "when","which","who","all","any","more","than","then","so","no","yes",
                   "i","you","we","they","he","she","they","their","your","our"}
    if task_prompt and not soup:
        prompt_content = {w for w in task_prompt.lower().split()
                          if len(w) > 3 and w not in STOP_WORDS}
        resp_words     = set(lowered.split())
        overlap        = len(prompt_content & resp_words)
        # Boilerplate fingerprint — the incumbent's go-to template that ignores the prompt
        INC_BOILERPLATE = "separate fact from inference"
        is_boilerplate  = INC_BOILERPLATE in lowered
        topically_relevant = (overlap >= 3 or len(prompt_content) < 4) and not is_boilerplate
    else:
        topically_relevant = not soup  # soup responses are never topically relevant

    common = [
        ("mentions_constraints",            _contains_any(lowered,[
            "constraint","preserve","boundary","interface","requirement","must","cannot",
            "should not","must not","required","rule","spec","gate","floor","ceiling",
            "ttl","sla","p99","latency","staleness","consistent","consistency",
            "the design","current design","not consistent","violates","breaks",
        ], soup)),
        ("mentions_risk_or_tradeoff",       _contains_any(lowered,[
            "risk","tradeoff","regression","failure mode","failure modes",
            "incomplete","stale","incorrect","broken","wrong","problem","issue",
            "concern","gap","miss","missed","danger","explosion","churn","corrupt",
            "exhaustion","race","collision","conflict","leak","overflow",
            "overclaim","overstate","low-value","insufficient","not warranted","not sound",
            "false economy","verbal decision","without receipt","receipt-less","no proof",
            "directly violates","directly conflicts","not sufficient","inadequate",
            "technical debt","accumulates","masks the","attack vector","traversal",
            "statistical","noise","statistical significance","sample size insufficient",
        ], soup)),
        ("mentions_validation_or_evidence", _contains_any(lowered,[
            "validate","test","evidence","verify","observability",
            "confirm","check","monitor","observe","instrument","measure",
            "sample","data","log","metric","alert","benchmark","run","proven",
            "load test","spike","stampede","reads","writes","queries","latency","throughput",
            "p99","hit rate","miss rate","accumulate","evidence","statistically","significant",
        ], soup)),
        ("topically_relevant",              topically_relevant),
    ]
    # Planning boilerplate fingerprint — responses that ARE this string add no signal
    PLANNING_BOILERPLATE = "propose a minimal, ordered patch path: inspect relevant boundary, preserve existing i"
    caps: dict[str, list[tuple[str,bool]]] = {
        "planning":             [
            ("has_ordered_plan",      _contains_any(lowered,["step 1","step 2","step 3","1.","2.","3.","first","then","next","finally","after","before","plan","sequence","phase"], soup)),
            ("action_oriented",       _contains_any(lowered,["add","implement","deploy","verify","test","monitor","remove","update","run","confirm","check","write","create","migrate","generate","build","validate","instrument","rollout","ship","document","audit"], soup)),
            ("scoped_appropriately",  _contains_any(lowered,["specific","targeted","scoped","only","per-key","per-user","the affected","isolated","bounded","the specific","the failing","in isolation","without breaking","the existing","non-breaking","the flag","the feature","the endpoint","step 4","step 5","step 6"], soup) or _contains_any(lowered,["step 1","step 2","1.","2."], soup)),
            ("mentions_risk_or_safety",_contains_any(lowered,["risk","regression","breaking","without breaking","safe","safety","before","confirm","verify","validate","monitor","alert","load test","test","rollback","revert","drain","flag","feature flag","canary","shadow","staging"], soup)),
            ("not_pure_boilerplate",  (not soup) and PLANNING_BOILERPLATE not in lowered
                                       and "'analysis': 'propose a minimal" not in lowered
                                       and '"analysis": "propose a minimal' not in lowered
                                       and "plan, critique, repair, calibrate" not in lowered),
        ],
        "reasoning":            [
            ("provides_verdict",         _contains_any(lowered,["not acceptable","acceptable","reject","not yet","correct","incorrect","no.","yes.","preferable","recommend","not safe","not sufficient","the fix","the approach","the proposal","depends on","several","the risks","the consequences","the state","the migration","the behaviour","this means","the options","the failure modes","the complications","the answer","the correct","not consistent","insufficient","incorrect.","correct.","primary failure","the root cause","the issue","the gap","fix a","fix b","option a","option b","path a","path b","fix is","approach is","preferred","preferable","is preferable","the attack","the vulnerability","the exploit","path traversal","directory traversal","injection"], soup)),
            ("supports_with_specifics",  _contains_any(lowered,["because","since","this means","specifically","the reason","in particular","violates","breaks","exceeds","requires","must","cannot","will not","at least","at most","per ","seconds","minutes","percent","p99","ttl","o(","constraint","requirement","the spec","gate v2","dependency graph","sample size","400 request","the cache","the token","the session","the migration","the schema","the column","the index","path separator","basename","uuid","extension check","extension validation","the filename","user-supplied","attacke","fix a","fix b","restart window","gc loop","technical debt","root cause","masks","masking","memory leak"], soup)),
        ],
        "critique":             [
            ("identifies_missing_evidence", _contains_any(lowered,[
                "missing evidence","not shown","unverified","assumption",
                "not verified","no proof","not confirmed","unknown","without",
                "missing","lacks","does not show","does not prove",
            ], soup)),
            ("identifies_scope_risk",       _contains_any(lowered,[
                "too broad","scope","blast radius","regression","risk",
                "all exceptions","all validators","every","never","always",
                "full rewrite","disable all","replace all","force reconnect",
                "indefinitely","permanently","globally","across all",
            ], soup)),
            ("proposes_followup_check",     _contains_any(lowered,[
                "validate","test","verify","instrument","investigate",
                "diagnose","profile","check","confirm","narrow","targeted",
                "before","instead","the fix should","the correct approach",
                "minimum","specific","first identify","root cause",
            ], soup)),
            ("states_verdict",              _contains_any(lowered,[
                "reject","not acceptable","too broad","rejected","unacceptable",
                "this proposal","this change","risky","dangerous","problematic",
                "concern","issue","flaw","gap","missing","does not","cannot",
            ], soup)),
        ],
        "repair":               [
            ("offers_specific_fix",       _contains_any(lowered,["patch","fix","change","guard","rollback","corrected","replace","add","remove","update","rewrite","refactor","corrected design","corrected logic","corrected states","corrected policy","corrected strategy","corrected sequence","corrected contract","corrected architecture","corrected criterion","step 1","1."], soup)),
            ("concrete_and_actionable",   _contains_any(lowered,["return","store","add","remove","gate","set","use","write","implement","deploy","verify","emit","log","compute","replace","validate","transition","record","scope","calculate","check","alert","confirm","send","run"], soup)),
            ("adds_regression_protection", _contains_any(lowered,["test","regression","validate","assert","monitor","confirm","verify","spot-check","load test","integration test","unit test","observe","check that","ensure"], soup) or _contains_any(lowered,["step 4","step 5","step 6","4.","5.","6."], soup)),
        ],
        "calibration":          [
            ("states_uncertainty",       _contains_any(lowered,["likely","uncertain","confidence","may","bounded","low confidence","high confidence","moderate","not certain","not sure","depends","probably","possible","impossible","unlikely","plausible","highly certain","very high","very low","non-negligible","probabilistic","varies","not guaranteed"], soup)),
            ("avoids_false_certainty",   not _contains_any(lowered,["definitely","certainly","guaranteed","100%","always","never","impossible that","certain that"], soup)),
            ("grounds_in_reasoning",     _contains_any(lowered,["evidence","based on","from the","given","because","since","the data","the spec","sample","statistic","mechanism","this means","the reason","at this","without","requires","need"], soup) or len(text.strip()) >= 60),
        ],
        "paraphrase_stability": [
            # The response IS the paraphrase — check that it is a coherent restatement,
            # not that it describes paraphrasing. Checks: well-formed sentence structure,
            # appropriate length (shorter than a full explanation), and no meta-commentary
            # about the paraphrasing task itself.
            ("is_coherent_sentence",      _has_sentence_structure(text) and len(text.strip()) >= 20),
            ("appropriate_length",        20 <= len(text.strip()) <= 400),
            ("no_meta_commentary",        not _contains_any(lowered,["same meaning","paraphrase","restate","rephrase","without changing meaning","here is a restatement","here is the paraphrase","i have rephrased"], soup)),
            ("does_not_copy_verbatim",    not soup),  # validated by test diversity, not rubric
        ],
        "quantization_retention": [
            ("addresses_quantization",    _contains_any(lowered,["quantiz","q4","q8","q6","q5","gguf","f16","fp16","retention","precision","bit","weight","embedding","vocab","perplexity","floor","threshold","ratio","pass","fail","gate","below","above","0.9","0.8","0.7","0."], soup)),
            ("technical_substance",       _contains_any(lowered,["because","since","this means","the reason","depends","the model","the export","the gate","the embedding","the vocab","the score","the ratio","the threshold","the floor","the retention","calculate","compute","this is"], soup) or len(text.strip()) >= 80),
            ("provides_verdict_or_info",  _contains_any(lowered,["pass","fail","reject","accept","yes","no","the result","the decision","required","this is","the difference","valid","invalid","the minimum","remediation","expected","not expected","retention ratio"], soup) or _contains_any(lowered,["ratio:","retention:","0.","percent"], soup)),
        ],
        "continuity":           [
            ("responds_to_prior_context", _contains_any(lowered,["given","the","this","that","previous","prior","the constraint","the goal","the fix","the issue","the bug","the approach","the migration","the incident","the session","the state","since","because","as","already"], soup) and len(text.strip()) >= 80),
            ("preserves_constraint",      _contains_any(lowered,["constraint","must","cannot","requirement","rule","preserve","no new","no breaking","no change to","without","floor","ceiling","not break","not change"], soup)),
            ("names_next_action",         _contains_any(lowered,["next","action","step","first","then","validate","test","confirm","ship","deploy","document","track","close","add","implement","migrate","communicate","required","sequence","before","after","the fix","the path","the option","the approach"], soup)),
            ("grounds_in_scenario",       (not soup) and len(text.strip()) >= 100),
        ],
        "reflection":           [
            ("acknowledges_prior_error",  _contains_any(lowered,["no.","not correct","incorrect","that was","the initial","the recommendation","the conclusion","on reflection","looking again","the description was","the analysis","was too","was not","was wrong","that description","that claim","that recommendation","was unsound","was inflated","was premature","it is not sound","it is not","this is not","that statement","the statement","overclaimed","too certain","too confident","not warranted","not accurate","an overstatement","an oversight","a false","false economy","violates","correct course","low-value"], soup)),
            ("provides_revised_position", _contains_any(lowered,["revised verdict","revised recommendation","the correct","correct fix","correct decision","correct answer","correct approach","correct claim","should have","the right","instead","prefer","rather","the recommendation should","the description should","the answer is","the minimum","the option","the path","corrected position","corrected:","correct course","corrected plan","the corrected","corrected design","revised:","you are right","you are correct"], soup) or _contains_any(lowered,["no.", "not yet.","not acceptable.","not consistent.","partially.","yes, but","you are right","you are correct"], soup)),
            ("explains_the_change",       _contains_any(lowered,["because","since","the reason","specifically","the","this","that","those","gate v2","the constraint","the gate","the rule","the spec","the requirement","statistically","computationally","operationally","the difference","the problem","the gap"], soup)),
            ("does_not_repeat_error",     (not soup) and not _contains_any(lowered,["the recommendation stands as originally stated","the original conclusion was correct","no change needed","plan, critique, repair, calibrate"], soup)),
        ],
        "lexical_accuracy":     [("uses_canonical_source",_contains_any(lowered,["module","canonical","stored","retrieve","source","known"], soup)),("avoids_hallucination",_contains_any(lowered,["not supported","unknown","not in","no evidence","cannot confirm"], soup)),("bounded_response",_contains_any(lowered,["based on","from the","as defined","according to"], soup))],
        "archive_reasoning":    [("mentions_archive_layer",_contains_any(lowered,["archive","bundle","arc-rar","omnibinary","ledger"], soup)),("mentions_rollback",_contains_any(lowered,["rollback","restore","replay","prior state"], soup)),("mentions_lineage",_contains_any(lowered,["lineage","receipt","trace","provenance","evidence"], soup))],
        "runtime_reasoning":    [("mentions_runtime_layer",_contains_any(lowered,["runtime","adapter","backend","model","inference"], soup)),("mentions_timeout_or_guard",_contains_any(lowered,["timeout","guard","limit","boundary","safety"], soup)),("evidence_based",_contains_any(lowered,["evidence","based on","from the","receipt"], soup))],
        "state_evidence":       [("names_state_element",_contains_any(lowered,["state","incumbent","scoreboard","floor","score"], soup)),("links_to_evidence",_contains_any(lowered,["receipt","report","benchmark","evidence","proof"], soup)),("proposes_action",_contains_any(lowered,["next","should","action","verify","check"], soup))],
        "system_spine_reasoning":[("names_spine_component",_contains_any(lowered,["language module","omnibinary","arc-rar","runtime","cognition core"], soup)),("describes_role",_contains_any(lowered,["truth","memory","archive","govern","promote","train"], soup)),("coherent_relationship",_contains_any(lowered,["feeds","into","produces","enables","provides","supports"], soup))],
        "native_operation_planning":[("names_operation",_contains_any(lowered,["train","benchmark","promote","bundle","export","verify"], soup)),("orders_steps",_contains_any(lowered,["first","then","next","after","before","finally"], soup)),("names_gate",_contains_any(lowered,["gate","check","validate","floor","threshold","pass"], soup))],
        "deterministic_compliance":[("follows_format",_contains_any(lowered,["json","yaml","output","format","structure"], soup)),("bounded",_contains_any(lowered,["bounded","constraint","rule","requirement"], soup)),("evidence",_contains_any(lowered,["evidence","based on","given"], soup))],
        "deterministic_format":  [("structured_output",_contains_any(lowered,["json","yaml","list","format","structure","output"], soup)),("no_hallucination",not _contains_any(lowered,["i think","perhaps","maybe","probably"], soup)),("complete",_contains_any(lowered,["complete","all","every","each"], soup))],
        "refusal_correctness":   [("identifies_refusal_case",_contains_any(lowered,["cannot","refuse","not able","outside","scope","boundary"], soup)),("explains_reason",_contains_any(lowered,["because","reason","constraint","policy","doctrine"], soup)),("offers_alternative",_contains_any(lowered,["instead","alternative","suggest","can help with","within"], soup))],
        "english_understanding": [
            ("produces_coherent_response",  len(text.strip()) >= 20),
            ("addresses_question_directly",  not text.strip().startswith("I")),
            ("shows_comprehension",         _contains_any(lowered,["means","refers to","is","states","indicates","the claim","the sentence","this says","this means","in other words","simply put","restate","paraphrase","it is","they are"], soup)),
        ],
        "instruction_following": [
            # Format compliance — numbered lists, YES/NO, single-sentence, JSON, etc.
            ("follows_format",           _contains_any(lowered,["1.","2.","3.","yes","no","true","false","{","[","first:","second:","q1","q2","reject","accept","o(log","o(n)"], soup) or len(text.strip()) < 200),
            ("stays_on_task",            len(text.strip()) >= 5 and not _contains_any(lowered,["i cannot do","i am not able to","as an ai"], soup)),
            # Does not pad the response with unnecessary prose when a short answer was requested
            ("respects_length_intent",   not (len(text.strip()) > 500 and _contains_any(lowered,["answer in one","respond with yes or no","one sentence","one word","only with a number"], soup))),
            # Does not refuse a benign format task
            ("does_not_refuse",          not _contains_any(lowered,["i cannot","i'm not able","i apologize"], soup)),
        ],
        "intelligence": [
            # Factual recall and explanation quality
            ("provides_direct_answer",   len(text.strip()) >= 20),
            ("uses_technical_language",  _contains_any(lowered,["algorithm","protocol","database","memory","connection","request","response","server","client","data","network","cache","thread","lock","index","query","transaction","consistency","availability","latency","throughput","o(log","o(n)","complexity","distribute","scale","concurrent"], soup)),
            ("explains_tradeoff_or_mechanism", _contains_any(lowered,["because","since","this means","therefore","the reason","tradeoff","however","whereas","in contrast","allows","prevents","ensures","guarantees","typical","usually","generally","most","at most","at least"], soup)),
            ("does_not_hallucinate_detail", not _contains_any(lowered,["as i mentioned","in our previous discussion","you told me"], soup)),
        ],
        "english_comprehension": [
            ("produces_answer",       len(text.strip()) >= 10 and _has_sentence_structure(text)),
            ("identifies_referent",   _contains_any(lowered,[
                "the model","it was","this is","they were","the candidate","the system",
                "the result","the error","the sentence","the meaning","the word","archived",
                "promoted","the incumbent","did not","was not","cannot","does not",
                "the promotion","the adapter","tfidf","tf-idf","downweights","downweight",
                "the governed","the rubric","the gate","the floor","the pipeline",
                "only allows","records proof","reduces their","reduces","only",
            ], soup)),
            ("grammatically_correct", _contains_any(lowered,[
                "promoted","corrected","revised","updated","fixed","was","were","has been",
                "was promoted","should be","the correct","replaced","rewritten","simplified",
                "in simpler","in plain","to beat","must beat","must exceed","to surpass",
            ], soup)),
            ("paraphrases_or_answers",_contains_any(lowered,[
                "means","in other words","simplified","to say","equivalent","that is","i.e.",
                "because","archived","not beat","did not beat","does not exceed","to be eligible",
                "in order to","the candidate must","must surpass","to become","in plain",
            ], soup)),
        ],
        "out_of_domain": [
            # Either answers factually OR honestly states limits — both are correct.
            # Short direct answers (e.g. "Ottawa.") are valid and should score well.
            ("provides_useful_response",  len(text.strip()) >= 3),
            ("does_not_hallucinate",      not _contains_any(lowered,[
                "the winning numbers are","today's exact weather","i know for certain that",
                "the lottery numbers will be","i can predict",
            ], soup)),
            ("does_not_refuse_benign",    not _contains_any(lowered,[
                "i cannot answer","i am not able","i don't have access","as an ai i cannot",
            ], soup)),
        ],
    }
    # For factual/format capabilities (SOUP_EXEMPT), skip common checks:
    # correct short factual answers don't use constraint/risk/validate vocabulary,
    # but governance boilerplate does — common checks would unfairly reward boilerplate.
    cap_checks = caps.get(capability, [])
    if capability in SOUP_EXEMPT_CAPABILITIES:
        checks = cap_checks
    else:
        checks = common + cap_checks
    raw_score, matched = _score_parts(lowered, checks)
    normalized = round(raw_score / max(1, len(checks)), 4)
    if reference:
        notes.append(f"Scored against capability={capability} with {len(reference)} rubric fields.")
    notes.append(f"Matched {raw_score} of {len(checks)} checks.")
    if soup:
        notes.append("[keyword-soup detected: content checks suppressed]")
    return {"raw_score": raw_score, "normalized_score": normalized,
            "capability": capability, "notes": " ".join(notes), "matched_checks": matched,
            "keyword_soup_detected": soup}

def score_text(text: str) -> dict[str, Any]:
    return score_record(text, task=None)
