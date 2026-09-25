import numpy as np

from app.features.prematch import PrematchState, training_rows


def test_target_and_future_scores_cannot_change_features(snapshot):
    target = snapshot.history[40]
    changed = [
        g.model_copy(update={"home_score": 20}) if g.date >= target.date else g
        for g in snapshot.history
    ]
    a = PrematchState.before(snapshot.history, target.date)
    b = PrematchState.before(changed, target.date)
    np.testing.assert_array_equal(
        a.vector(target.home, target.away, target.date),
        b.vector(target.home, target.away, target.date),
    )


def test_training_inference_feature_parity(snapshot):
    rows = list(training_rows(snapshot.history))
    game, vector, _ = rows[25]
    state = PrematchState.before(snapshot.history, game.date)
    np.testing.assert_array_equal(vector, state.vector(game.home, game.away, game.date))
    assert len(vector) == 67


def test_same_day_is_batch_before_update(snapshot):
    history = list(snapshot.history)
    day = history[40].date
    a = PrematchState.before(history, day)
    b = PrematchState.before(list(reversed(history)), day)
    np.testing.assert_array_equal(a.features("A", day), b.features("A", day))
