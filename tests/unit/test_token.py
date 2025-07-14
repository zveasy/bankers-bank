from unittest.mock import Mock, patch

from bankersbank.finastra import fetch_token


def test_fetch_token_success():
    mock_resp = Mock()
    mock_resp.json.return_value = {"access_token": "xyz"}
    mock_resp.raise_for_status.return_value = None
    with patch("requests.post", return_value=mock_resp) as p:
        token = fetch_token("id", "secret")
    p.assert_called_once()
    assert token == "xyz"
