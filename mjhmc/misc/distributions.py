"""
 This module contains the Distribution class which defines a standard
 interface for distributions It also provides several implemented
 distributions, which inherit from Distribution Any user-specified
 distributions should inherit from Distribution
"""
import numpy as np
from .utils import overrides, package_path
import os
from scipy import stats
import pickle

class Distribution(object):
    """
    Interface/abstract class for distributions.
    Any user-specified distributions should be defined by inheriting from this class and
     overriding the appropriate methods.
    """

    def __init__(self, ndims=2, nbatch=100):
        """ Creates a Distribution object

        :param ndims: the dimension of the state space for this distribution
        :param nbatch: the number of sampling particles to run simultaneously
        :returns: a Distribution object
        :rtype: Distribution

        """

        # distribution dimensions
        self.ndims = ndims
        # number of sampling particles to use
        self.nbatch = nbatch

        # TensorflowDistributions require some special treatment
        # this attribute is to be used instead of isinstance, as that would require
        # tensorflow to be imported globally
        if not hasattr(self, 'backend'):
            self.backend = 'numpy'

        # true iff being sampled with a jump process
        self.mjhmc = None

        # number of times energy op has been called
        self.E_count = 0

        # number of times gradient op has been called
        self.dEdX_count = 0

        # only set to true when I have a bias initialization and am being burned in
        # to generate and cache a fair initialization for continuous samplers
        self.generation_instance = False

        # set the state fairly. calls out to a cache
        self.init_X()


    def E(self, X):
        self.E_count += X.shape[1]
        return self.E_val(X)

    def E_val(self, X):
        """
        Subclasses should implement this with the correct energy function
        """
        raise NotImplementedError()


    def dEdX(self, X):
        self.dEdX_count += X.shape[1]
        return self.dEdX_val(X)

    def dEdX_val(self, X):
        """
        Subclasses should implement this with the correct energy gradient function
        """
        raise NotImplementedError()

    def __hash__(self):
        """ Subclasses should implement this as the hash of the tuple of all parameters
        that effect the distribution, including ndims. This is very important!!
        nbatch should not be part of the hash!! Including it will break everything

        As an example, see how this is implemented in Gaussian

        :returns: a hash of the relevant parameters of self
        :rtype: int
        """
        raise NotImplementedError()


    def init_X(self):
        """
        Sets self.Xinit to a good initial value
        """
        # TODO: make production ready by adding global flag to disable
        #  research options like this
        self.cached_init_X()

    def cached_init_X(self):
        """ Sets self.Xinit to cached (serialized) initial states for continuous-time samplers, generated by burn in
        *For use with continuous-time samplers only*

        :returns: None
        :rtype: none
        """
        distr_name = type(self).__name__
        distr_hash = hash(self)
        file_name = '{}_{}.pickle'.format(distr_name, distr_hash)
        file_prefix = '{}/initializations'.format(package_path())
        if file_name in os.listdir(file_prefix):
            with open('{}/{}'.format(file_prefix, file_name), 'rb') as cache_file:
                mjhmc_endpt, _, _, control_endpt  = pickle.load(cache_file)
                if self.mjhmc:
                    self.Xinit = mjhmc_endpt[:, :self.nbatch]
                else:
                    self.Xinit = control_endpt[:, :self.nbatch]
        else:
            from mjhmc.misc.gen_mj_init import MAX_N_PARTICLES, cache_initialization
            # modify this object so it can be used by gen_mj_init
            old_nbatch = self.nbatch
            self.nbatch = MAX_N_PARTICLES
            self.generation_instance = True

            # must rebuild now that nbatch is changed back
            if self.backend == 'tensorflow':
                self.build_graph()

            # start with biased initializations
            # changes self.nbatch
            try:
                self.gen_init_X()
            except NotImplementedError:
                # completely arbitrary choice
                self.Xinit = np.random.randn(self.ndims, self.nbatch)

            #generate and cache fair initialization
            cache_initialization(self)
            # reconstruct this object using fair initialization
            self.nbatch = old_nbatch
            self.generation_instance = False
            # must rebuild now that nbatch is changed back
            if self.backend == 'tensorflow':
                 self.build_graph()
            self.cached_init_X()



    def gen_init_X(self):
        """ Sets self.Xinit to generated initial states for the sampling particles
        *For use with discrete-time samplers only*

        :returns: None
        :rtype: None
        """
        raise NotImplementedError()

    def reset(self):
        """
        resets the object. returns self for convenience
        """
        self.E_count = 0
        self.dEdX_count = 0
        if not self.generation_instance:
            self.init_X()
        return self

    def __call__(self, X):
        """
        Convenience method for NUTS compatibility
        returns -E, -dEdX
        """
        rshp_X = X.reshape(len(X), 1)
        E = float(self.E(rshp_X))
        dEdX = self.dEdX(rshp_X).T[0]
        return -E, -dEdX

    def load_cache(self):
        """ Loads and returns the cached fair initializations and
         estimated variances associated with this
         distribution. Throws an error if the cache does not exist

        :returns: the loaded cache: (fair_initialization, emc_var_estimate, true_var_estimate)
        :rtype: (np.ndarray, float, float)
        """
        distr_name = type(self).__name__
        distr_hash = hash(self)
        file_name = '{}_{}.pickle'.format(distr_name, distr_hash)
        file_prefix = '{}/initializations'.format(package_path())
        with open('{}/{}'.format(file_prefix, file_name)) as cache_file:
            return pickle.load(cache_file)


class LambdaDistribution(Distribution):
    """ An `anonymous' distribution object for quick
    experimentation. Due to the initialization time that is required
    at first run it, one shouldn't use this object in the
    long-term. Rather create your own distribution class that inherits
    from Distribution.

    You should give your LambdaDistribution objects a name. Use a
    descriptive name, and use the same for functionally equivalent
    LambdaDistributions - the hash of the name is used to label the
    initialization information which is generated at first run time of
    a new distribution. This requirement is a side effect of the
    unfortunate fact that there is no computable hash function which
    assigns functionally identical programs to the same number.
    """


    #pylint: disable=too-many-arguments
    def __init__(self, energy_func=None, energy_grad_func=None, init=None, name=None):
        """ Creates an anonymous distribution object.

        :param ndims: the dimension of the state space for this distribution
        :param nbatch: the number of sampling particles to run simultaneously
        :param energy_func: function specifying the energy
        :param energy_grad_func: function specifying gradient of the energy
        :param name: name of this distribution. use the same name for
          functionally identical distributions
        :param init: fair initialization for this distribution. array of shape (ndims, nbatch)
        :returns: an anonymous distribution object
        :rtype: LambdaDistribution

        """
        self.energy_func = energy_func
        self.energy_grad_func = energy_grad_func
        self.init = init
        # TODO: raise warning if name is not passed
        self.name = name or str(np.random())
        super(LambdaDistribution, self).__init__(ndims=init.shape[0], nbatch=init.shape[1])

    @overrides(Distribution)
    def E_val(self, X):
        return np.sum(X*np.dot(self.J,X), axis=0).reshape((1,-1))/2.

    @overrides(Distribution)
    def dEdX_val(self, X):
        return np.dot(self.J,X)/2. + np.dot(self.J.T,X)/2.

    @overrides(Distribution)
    def gen_init_X(self):
        self.Xinit = self.init

    @overrides(Distribution)
    def __hash__(self):
        return hash((self.ndims, self.nbatch, self.name))




class Gaussian(Distribution):
    def __init__(self, ndims=2, nbatch=100, log_conditioning=6):
        """
        Energy function, gradient, and hyperparameters for the "ill
        conditioned Gaussian" example from the LAHMC paper.
        """
        self.conditioning = 10**np.linspace(-log_conditioning, 0, ndims)
        self.J = np.diag(self.conditioning)
        self.description = '%dD Anisotropic Gaussian, %g self.conditioning'%(ndims, 10**log_conditioning)
        super(Gaussian, self).__init__(ndims, nbatch)

    @overrides(Distribution)
    def E_val(self, X):
        return np.sum(X*np.dot(self.J,X), axis=0).reshape((1,-1))/2.

    @overrides(Distribution)
    def dEdX_val(self, X):
        return np.dot(self.J,X)/2. + np.dot(self.J.T,X)/2.

    @overrides(Distribution)
    def gen_init_X(self):
        self.Xinit = (1./np.sqrt(self.conditioning).reshape((-1,1))) * np.random.randn(self.ndims,self.nbatch)

    @overrides(Distribution)
    def __hash__(self):
        return hash((self.ndims, hash(tuple(self.conditioning))))

class RoughWell(Distribution):
    def __init__(self, ndims=2, nbatch=100, scale1=100, scale2=4):
        """
        Energy function, gradient, and hyperparameters for the "rough well"
        example from the LAHMC paper.
        """
        self.scale1 = scale1
        self.scale2 = scale2
        self.description = '{} Rough Well'.format(ndims)
        super(RoughWell, self).__init__(ndims, nbatch)

    @overrides(Distribution)
    def E_val(self, X):
        cosX = np.cos(X*2*np.pi/self.scale2)
        E = np.sum((X**2) / (2*self.scale1**2) + cosX, axis=0).reshape((1,-1))
        return E

    @overrides(Distribution)
    def dEdX_val(self, X):
        sinX = np.sin(X*2*np.pi/self.scale2)
        dEdX = X/self.scale1**2 + -sinX*2*np.pi/self.scale2
        return dEdX

    @overrides(Distribution)
    def gen_init_X(self):
        self.Xinit = self.scale1 * np.random.randn(self.ndims, self.nbatch)

    @overrides(Distribution)
    def __hash__(self):
        return hash((self.ndims, self.scale1, self.scale2))

class MultimodalGaussian(Distribution):
    def __init__(self, ndims=2, nbatch=100, separation=3):
        self.sep_vec = np.array([separation] * nbatch +
                                [0] * (ndims - 1) * nbatch).reshape(ndims, nbatch)
        # separated along first axis
        self.sep_vec[0] += separation
        super(MultimodalGaussian, self).__init__(ndims, nbatch)

    @overrides(Distribution)
    def E_val(self, X):
        trim_sep_vec = self.sep_vec[:, :X.shape[1]]
        return -np.log(np.exp(-np.sum((X + trim_sep_vec)**2, axis=0)) +
                       np.exp(-np.sum((X - trim_sep_vec)**2, axis=0)))

    @overrides(Distribution)
    def dEdX_val(self, X):
        # allows for partial batch size
        trim_sep_vec = self.sep_vec[:, :X.shape[1]]
        common_exp = np.exp(np.sum(4 * trim_sep_vec * X, axis=0))
        # floating point hax
        return ((2 * ((X - trim_sep_vec) * common_exp + trim_sep_vec + X)) /
                (common_exp + 1))


    @overrides(Distribution)
    def init_X(self):
        # okay, this is pointless... sep vecs cancel
        self.Xinit = ((np.random.randn(self.ndims, self.nbatch) + self.sep_vec) +
                (np.random.randn(self.ndims, self.nbatch) - self.sep_vec))

    @overrides(Distribution)
    def __hash__(self):
        return hash((self.ndims, self.separation))

class TestGaussian(Distribution):

    def __init__(self, ndims=2, nbatch=100, sigma=1.):
        """Simple default unit variance gaussian for testing samplers
        """
        self.sigma = sigma
        super(TestGaussian, self).__init__(ndims, nbatch)

    @overrides(Distribution)
    def E_val(self, X):
        return np.sum(X**2, axis=0).reshape((1, -1)) / (2. * self.sigma ** 2)

    @overrides(Distribution)
    def dEdX_val(self, X):
        return X/self.sigma**2

    @overrides(Distribution)
    def gen_init_X(self):
        self.Xinit = np.random.randn(self.ndims, self.nbatch)

    @overrides(Distribution)
    def __hash__(self):
        return hash((self.ndims, self.sigma))

#pylint: disable=too-many-instance-attributes
class ProductOfT(Distribution):
    """ Provides the product of T experts distribution
    """


    #pylint: disable=too-many-arguments
    def __init__(self, ndims=36, nbasis=36, nbatch=100, lognu=None, W=None, b=None):
        """ Product of T experts, assumes a fixed W that is sparse and alpha that is
        """
        # awkward hack to import theano in poe only
        try:
            import theano.tensor as T
            import theano
            self.theano = theano
            self.T = T
        except:
            raise ImportError("Theano could not be imported")

        if ndims != nbasis:
            raise NotImplementedError("Initializer only works for ndims == nbasis")
        self.ndims = ndims
        self.nbasis = nbasis
        self.nbatch = nbatch
        if W is None:
            W = np.eye(ndims, nbasis)
        self.weights = self.theano.shared(np.array(W, dtype='float32'), 'W')
        if lognu is None:
            pre_nu = np.random.rand(nbasis,) * 2 + 2.1
        else:
            pre_nu = np.exp(lognu)
        self.nu = self.theano.shared(np.array(pre_nu, dtype='float32'), 'nu')
        if b is None:
            b = np.zeros((nbasis,))
        self.bias = self.theano.shared(np.array(b, dtype='float32'), 'b')

        state = T.matrix()
        energy = self.E_def(state)
        gradient = T.grad(T.sum(energy), state)

        #@overrides(Distribution)
        self.E_val = self.theano.function([state], energy, allow_input_downcast=True)
        #@overrides(Distribution)
        self.dEdX_val = self.theano.function([state], gradient, allow_input_downcast=True)

        super(ProductOfT,self).__init__(ndims,nbatch)
        self.backend = 'theano'

    def E_def(self,X):
        """
        energy for a POE with student's-t expert in terms of:
                samples [# dimensions]x[# samples] X
                receptive fields [# dimensions]x[# experts] W
                biases [# experts] b
                degrees of freedom [# experts] nu
        """
        rshp_b = self.bias.reshape((1,-1))
        rshp_nu = self.nu.reshape((1, -1))
        alpha = (rshp_nu + 1.)/2.
        energy_per_expert = alpha * self.T.log(1 + ((self.T.dot(X.T, self.weights) + rshp_b) / rshp_nu) ** 2)
        energy = self.T.sum(energy_per_expert, axis=1).reshape((1, -1))
        return energy


    @overrides(Distribution)
    def gen_init_X(self):
        #hack to remap samples from a generic product of experts to
        #the model we are actually going to generate samples from
        Zinit = np.zeros((self.ndims, self.nbatch))
        for ii in xrange(self.ndims):
            Zinit[ii] = stats.t.rvs(self.nu.get_value()[ii], size=self.nbatch)

        Yinit = Zinit - self.bias.get_value().reshape((-1, 1))
        self.Xinit = np.dot(np.linalg.inv(self.weights.get_value()), Yinit)

    @overrides(Distribution)
    def __hash__(self):
        return hash((self.ndims,
                     self.nbasis,
                     hash(tuple(self.nu.get_value())),
                     hash(tuple(self.weights.get_value().ravel())),
                     hash(tuple(self.bias.get_value().ravel()))))
