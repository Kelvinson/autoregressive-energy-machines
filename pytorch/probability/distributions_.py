import math
import sys
import torch

from numbers import Number
from torch import distributions
from torch.distributions import constraints
from torch.distributions.exp_family import ExponentialFamily
from torch.distributions.utils import _standard_normal, broadcast_all

q = sys.exit


class Normal_(ExponentialFamily):
    r"""
    Creates a normal (also called Gaussian) distribution parameterized by
    :attr:`loc` and :attr:`scale`.
    Example::
        >>> m = Normal(torch.tensor([0.0]), torch.tensor([1.0]))
        >>> m.sample()  # normally distributed with loc=0 and scale=1
        tensor([ 0.1046])
    Args:
        loc (float or Tensor): mean of the distribution (often referred to as mu)
        scale (float or Tensor): standard deviation of the distribution
            (often referred to as sigma)
    """
    arg_constraints = {'loc': constraints.real, 'scale': constraints.positive}
    support = constraints.real
    has_rsample = True
    _mean_carrier_measure = 0

    @property
    def mean(self):
        return self.loc

    @property
    def stddev(self):
        return self.scale

    @property
    def variance(self):
        return self.stddev.pow(2)

    def __init__(self, loc, scale, validate_args=None):
        self.loc, self.scale = broadcast_all(loc, scale)
        if isinstance(loc, Number) and isinstance(scale, Number):
            batch_shape = torch.Size()
        else:
            batch_shape = self.loc.size()
        super(Normal_, self).__init__(batch_shape, validate_args=validate_args)

    def expand(self, batch_shape, _instance=None):
        new = self._get_checked_instance(Normal_, _instance)
        batch_shape = torch.Size(batch_shape)
        new.loc = self.loc.expand(batch_shape)
        new.scale = self.scale.expand(batch_shape)
        super(Normal_, new).__init__(batch_shape, validate_args=False)
        new._validate_args = self._validate_args
        return new

    def sample(self, sample_shape=torch.Size()):
        shape = self._extended_shape(sample_shape)
        with torch.no_grad():
            return torch.normal(self.loc.expand(shape), self.scale.expand(shape))

    def rsample(self, sample_shape=torch.Size()):
        shape = self._extended_shape(sample_shape)
        eps = _standard_normal(shape, dtype=self.loc.dtype, device=self.loc.device)
        return self.loc + eps * self.scale

    def log_prob(self, value):
        if self._validate_args:
            self._validate_sample(value)
        log_scale = math.log(self.scale) if isinstance(self.scale,
                                                       Number) else self.scale.log()
        return -0.5 * ((value - self.loc) / self.scale) ** 2 - log_scale - 0.5 * math.log(
            2 * math.pi)

    def cdf(self, value):
        if self._validate_args:
            self._validate_sample(value)
        return 0.5 * (1 + torch.erf(
            (value - self.loc) * self.scale.reciprocal() / math.sqrt(2)))

    def icdf(self, value):
        if self._validate_args:
            self._validate_sample(value)
        return self.loc + self.scale * torch.erfinv(2 * value - 1) * math.sqrt(2)

    def entropy(self):
        return 0.5 + 0.5 * math.log(2 * math.pi) + torch.log(self.scale)

    @property
    def _natural_params(self):
        return (self.loc / self.scale.pow(2), -0.5 * self.scale.pow(2).reciprocal())

    def _log_normalizer(self, x, y):
        return -0.25 * x.pow(2) / y + 0.5 * torch.log(-math.pi / y)


class MixtureSameFamily(distributions.Distribution):
    def __init__(self, mixture_distribution, components_distribution):
        self.mixture_distribution = mixture_distribution
        self.components_distribution = components_distribution

        super().__init__(
            batch_shape=self.components_distribution.batch_shape,
            event_shape=self.components_distribution.event_shape
        )

    def sample(self, sample_shape=torch.Size()):
        mixture_mask = self.mixture_distribution.sample(sample_shape)  # [S, B, D, M]
        if len(mixture_mask.shape) == 3:
            mixture_mask = mixture_mask[:, None, ...]
        components_samples = self.components_distribution.rsample(
            sample_shape)  # [S, B, D, M]
        samples = torch.sum(mixture_mask * components_samples, dim=-1)  # [S, B, D]
        return samples

    def log_prob(self, value):
        # pad value for evaluation under component density
        value = value.permute(2, 0, 1)  # [S, B, D]
        value = value[..., None].repeat(1, 1, 1, self.batch_shape[-1])  # [S, B, D, M]
        log_prob_components = self.components_distribution.log_prob(value).permute(1, 2,
                                                                                   3, 0)

        # calculate numerically stable log coefficients, and pad
        log_prob_mixture = self.mixture_distribution.logits
        log_prob_mixture = log_prob_mixture[..., None]
        return torch.logsumexp(log_prob_mixture + log_prob_components, dim=-2)


def main():
    pass


if __name__ == '__main__':
    main()
