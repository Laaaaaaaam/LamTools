from app.member import kit, manifest


def test_member_manifest_and_kit_match() -> None:
    assert kit.id == manifest.id
    assert kit.display_name == manifest.display_name
    assert kit.prompt_fragments()
    assert kit.tool_specs() == []
    assert kit.verification_policy().name == f"{manifest.id}-default"
