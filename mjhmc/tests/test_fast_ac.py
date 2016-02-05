"""
This module contains unit tests for the theano autocorrelation function
"""
import unittest
import numpy as np

from mjhmc.fast.hmc import normed_autocorrelation
from mjhmc.misc.autocor import slow_autocorrelation, sample_to_df

from mjhmc.misc.distributions import Gaussian, MultimodalGaussian
from mjhmc.samplers.markov_jump_hmc import MarkovJumpHMC


class TestFastAutocorrelation(unittest.TestCase):
    """
    Test class for theano autocorrelation function
    """

    def setUp(self):
        np.random.seed(2015)


    def test_autocorrelation_good_init(self):
        """ Tests that the legacy and fast ac implementations produce identical output
        when the sampler is not initialized in a biased manner
        (meaning we don't have to worry about variance mismatch)

        :returns: None
        :rtype: None
        """
        gaussian = Gaussian()
        sample_df = sample_to_df(MarkovJumpHMC, gaussian, num_steps=1000)
        slow_ac_df = slow_autocorrelation(sample_df)
        slow_ac = slow_ac_df.autocorrelation.as_matrix()
        fast_ac_df = normed_autocorrelation(sample_df)
        fast_ac = fast_ac_df.autocorrelation.as_matrix()
        self.assertTrue(np.isclose(slow_ac, fast_ac).all())


    def test_autocorrelation_bad_init(self):
        """ Tests that the legacy and fast ac implementations produce identical output
        when the sampler is initialized with a bias set of samples

        :returns: None
        :rtype: None
        """
        gaussian = MultimodalGaussian()
        sample_df = sample_to_df(MarkovJumpHMC, gaussian, num_steps=1000)
        slow_ac_df = slow_autocorrelation(sample_df)
        slow_ac = slow_ac_df.autocorrelation.as_matrix()
        fast_ac_df = normed_autocorrelation(sample_df)
        fast_ac = fast_ac_df.autocorrelation.as_matrix()
        self.assertTrue(np.isclose(slow_ac, fast_ac).all())