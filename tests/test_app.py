from fishmindos import FishMindOSApp


def test_delivery_flow_success() -> None:
    app = FishMindOSApp()
    result = app.run_text("到行政拿纸巾送到厕所")

    assert result["status"] == "success"
    assert len(result["events"]) == 5
    assert result["events"][0].detail.startswith("已到达")
