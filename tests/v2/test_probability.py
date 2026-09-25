import numpy as np
import pytest

from app.models.distributions import elo_probabilities, from_matrix, poisson_matrix
from app.models.mlp import MatchMLP


def test_score_margins_equal_ensemble():
    dist = from_matrix(poisson_matrix(1.8, 1.1), [0.1, 0.2, 0.7])
    assert np.tril(dist.scores, -1).sum() == pytest.approx(0.1)
    assert np.trace(dist.scores) == pytest.approx(0.2)
    assert np.triu(dist.scores, 1).sum() == pytest.approx(0.7)
    assert dist.home_advancement == pytest.approx(0.2)


def test_sample_full_distribution_not_top_three():
    dist = from_matrix(poisson_matrix(1.5, 1.2))
    rng = np.random.default_rng(42)
    samples = np.array([dist.sample(rng) for _ in range(15000)])
    assert abs(np.mean(samples[:, 0] > samples[:, 1]) - dist.probabilities[0]) < 0.02
    assert len(set(map(tuple, samples))) > 20


def test_symmetric_neutral_elo():
    forward = elo_probabilities(1800, 1600)
    backward = elo_probabilities(1600, 1800)
    np.testing.assert_allclose(forward, backward[::-1])


@pytest.mark.parametrize("probabilities", [[0.2, 0.2, 0.2], [float("nan"), 0, 1], [-0.1, 0.1, 1]])
def test_invalid_probability_rejected(probabilities):
    with pytest.raises(ValueError):
        from_matrix(poisson_matrix(1, 1), probabilities)


def test_mlp_consumes_all_features():
    import torch

    torch.manual_seed(1)
    model = MatchMLP().eval()
    x = torch.zeros((2, 68))
    x[1, 60] = 5
    assert not torch.allclose(model(x)[0], model(x)[1])
    with pytest.raises(ValueError):
        model(torch.zeros((1, 67)))
