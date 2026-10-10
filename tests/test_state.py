from src.ui.state import AppState


def test_select_all_accumulates_across_pages():
    """select_all should add to existing selection, not replace it."""
    state = AppState()
    state.toggle_selection("profile-a")
    state.toggle_selection("profile-b")

    # Simulate selecting a second page
    state.select_all(["profile-c", "profile-d"])

    selected = state.selected_names()
    assert "profile-a" in selected
    assert "profile-b" in selected
    assert "profile-c" in selected
    assert "profile-d" in selected


def test_select_all_deduplicates():
    """select_all with already-selected names should not duplicate."""
    state = AppState()
    state.toggle_selection("profile-a")

    state.select_all(["profile-a", "profile-b"])

    selected = state.selected_names()
    assert selected == {"profile-a", "profile-b"}
