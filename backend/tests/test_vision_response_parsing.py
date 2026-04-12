from app.agent.local_client import _parse_vision_response_text


def test_parse_vision_response_text_with_complete_json() -> None:
    payload = """
    {
      "emotion": "tired",
      "intensity": 3,
      "cues": "眼神涣散，身体后仰",
      "suggestion": "先活动一下肩颈"
    }
    """

    result = _parse_vision_response_text(payload)

    assert result == {
      "emotion": "tired",
      "intensity": 3,
      "cues": "眼神涣散，身体后仰",
      "suggestion": "先活动一下肩颈",
    }


def test_parse_vision_response_text_with_truncated_json() -> None:
    payload = """
    {
      "emotion": "tired",
      "intensity": 3,
      "cues": "眼神涣散，头部后仰",
      "suggestion": "看起来有些疲惫或正在
    """

    result = _parse_vision_response_text(payload)

    assert result is not None
    assert result["emotion"] == "tired"
    assert result["intensity"] == 3
    assert result["cues"] == "眼神涣散，头部后仰"