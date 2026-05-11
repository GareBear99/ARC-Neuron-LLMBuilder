from mcp.servers.arc_business_server import business_generate_ticket_response


def test_business_response_is_draft_only():
    result = business_generate_ticket_response("refund request", sources=[])
    assert result["requires_human_review"] is True
    assert result["external_send_allowed"] is False
