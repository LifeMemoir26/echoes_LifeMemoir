from src.domain.session_status import is_terminal_session_status


def test_terminal_session_status_rule():
    assert is_terminal_session_status("session_closed") is True
    assert is_terminal_session_status("idle_timeout") is True
    assert is_terminal_session_status("created") is False
