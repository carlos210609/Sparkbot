from sparkbot.goal_mode import run_goal


def test_goal_continues_until_verified_completion():
    turns = [
        {"reply": "I researched the options.\nGOAL_STATUS: CONTINUE",
         "events": [{"type": "plan", "message": "Plan ready"}]},
        {"reply": "The task is complete.\nVERIFICATION: Output exists and was checked.\nGOAL_STATUS: COMPLETE",
         "events": [{"type": "verification", "message": "Output checked"}]},
    ]
    events = []
    result = run_goal(
        "Produce a checked result",
        lambda kind, message, **data: events.append((kind, message, data)),
        "mission-test",
        lambda messages: turns.pop(0),
        lambda: False,
    )
    assert result["status"] == "COMPLETED"
    assert result["verified"] is True
    assert result["iterations"] == 2
    assert any(kind == "verification" for kind, _, _ in events)


def test_goal_never_marks_unverified_completion_as_done():
    turns = [
        {"reply": "Done!\nGOAL_STATUS: COMPLETE", "events": []},
        {"reply": "Still working.\nGOAL_STATUS: CONTINUE", "events": []},
    ]
    result = run_goal(
        "A goal that needs evidence",
        lambda *args, **kwargs: None,
        "mission-test-2",
        lambda messages: turns.pop(0),
        lambda: False,
    )
    assert result["status"] == "PARTIAL"
    assert result["verified"] is False


def test_goal_honors_stop_before_starting_an_iteration():
    result = run_goal(
        "Stop this goal",
        lambda *args, **kwargs: None,
        "mission-test-3",
        lambda messages: (_ for _ in ()).throw(AssertionError("agent should not run")),
        lambda: True,
    )
    assert result["status"] == "CANCELLED"
    assert result["iterations"] == 0
