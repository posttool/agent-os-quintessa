from quintessa.capabilities.loader import load_capabilities, load_prompt


def test_builtin_capabilities_load_from_markdown():
    caps = load_capabilities()
    assert set(caps) == {"memory", "generative_ui", "tool_discovery", "tool_use"}
    assert caps["memory"].executor == "memory"
    assert "knowledge graph" in caps["memory"].instructions


def test_capability_set_is_configurable(tmp_path):
    assert set(load_capabilities(names=["memory"])) == {"memory"}
    (tmp_path / "memory.md").write_text(
        "---\nname: memory\ndescription: only memory\nexecutor: memory\n---\nKeep it short."
    )
    caps = load_capabilities(tmp_path)
    assert caps["memory"].description == "only memory" and caps["memory"].instructions == "Keep it short."
    assert "reasoning controller" in load_prompt("controller", tmp_path)
