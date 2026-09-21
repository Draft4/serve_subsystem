from tennis_serve_launcher_adapter.adapter_core import (
    FeedResultTracker,
    feedback_directions_match,
    map_feedback,
    map_targets,
)


def test_default_upper_lower_mapping():
    assert map_targets(2000, 1800, 1, 1, -1) == (2000, -1800)
    assert map_feedback(1998.4, -1802.1, 1) == (1998, 1802)


def test_swapped_upper_lower_mapping():
    assert map_targets(2000, 1800, 2, 1, -1) == (1800, -2000)
    assert map_feedback(1799.6, -2001.2, 2) == (2001, 1800)


def test_feedback_direction_check_detects_reversed_motor():
    assert feedback_directions_match(2000.0, -1800.0, 2000, -1800)
    assert not feedback_directions_match(-2000.0, -1800.0, 2000, -1800)
    assert feedback_directions_match(20.0, -20.0, 2000, -1800, 100.0)


def test_feed_success_requires_completed_count_increment():
    tracker = FeedResultTracker(7.0)
    tracker.start("feed-1", 4, 10.0)
    tracker.update(4, 3, 5, "", 10.2)
    assert tracker.saw_progress
    assert not tracker.result_valid
    tracker.update(5, 0, 6, "", 11.0)
    assert tracker.result_valid
    assert tracker.succeeded
    assert tracker.detail == "FEED_COMPLETE"


def test_feed_failure_after_progress_and_timeout():
    tracker = FeedResultTracker(7.0)
    tracker.start("feed-2", 8, 20.0)
    tracker.update(8, 1, 2, "", 20.1)
    tracker.update(8, 10, 14, "", 26.1)
    assert tracker.result_valid
    assert not tracker.succeeded

    timeout = FeedResultTracker(7.0)
    timeout.start("feed-3", 8, 30.0)
    timeout.update(8, 6, 7, "", 37.1)
    assert timeout.result_valid
    assert not timeout.succeeded
    assert timeout.detail.startswith("FEED_TIMEOUT")


def test_feed_timeout_advances_without_new_feeder_messages():
    tracker = FeedResultTracker(7.0)
    tracker.start("feed-4", 3, 10.0)
    tracker.tick(17.1)
    assert tracker.result_valid
    assert not tracker.succeeded
    assert tracker.detail == "FEED_TIMEOUT_NO_RESULT"
