from mcp.servers.arc_eval_server import eval_compare_candidates


def test_eval_compare_candidates_detects_worse():
    result = eval_compare_candidates(incumbent_score=0.9, candidate_score=0.8)
    assert result["promotion_recommended"] is False
    assert result["delta"] < 0
