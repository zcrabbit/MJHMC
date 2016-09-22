"""
  This module contains the TensorflowDistribution base class and distributions that inherit from it
"""

import numpy as np
import tensorflow as tf
from .utils import overrides, package_path
import os
from scipy import stats
import pickle

from mjhmc.misc.distributions import Distribution


class TensorflowDistribution(Distribution):
    """ Base class for distributions defined by energy functions written
    in Tensorflow

    You should give your TensorflowDistribution objects a name. Use a
    descriptive name, and use the same for functionally equivalent
    TensorflowDistributions - the hash of the name is used to label the
    initialization information which is generated at first run time of
    a new distribution. This requirement is a side effect of the
    unfortunate fact that there is no computable hash function which
    assigns functionally identical programs to the same number.

    TensorflowDistribution is subclassed by defining the distribution energy op in
    build_energy_op
    """

    #pylint: disable=too-many-arguments
    def __init__(self, name=None, sess=None):
        """ Creates a TensorflowDistribution object

        ndims and nbatch are inferred from init
        nbatch must match shape of energy_op

        :param graph: the graph in which energy_op, state and state_placeholder were constructed
        :param energy_func: energy function op
        :param state: Variable taken as input by energy_func of the same shape as init
        :param state_placeholder: placeholder used to initialize state. of same shape as init
        :param init: fair initialization for this distribution. array of shape (ndims, nbatch)
        :param name: name of this distribution. use the same name for functionally identical distributions
        :param sess: optional session. If none, one will be created
        :returns: TensorflowDistribution object
        :rtype: TensorflowDistribution
        """
        self.graph = tf.Graph()
        with self.graph.as_default():
            self.sess = sess or tf.Session()


            ndims, nbatch = self.build_graph()
            self.name = name or self.energy_op.op.name

        super(TensorflowDistribution, self).__init__(ndims=ndims, nbatch=nbatch)
        self.backend = 'tensorflow'

    def build_graph(self):
        with self.graph.as_default():
            self.build_energy_op()
            ndims, nbatch = self.state.get_shape().as_list()
            self.state_pl = tf.placeholder(tf.float32, [ndims, None])

            self.assign_op = self.state.assign(self.state_pl)
            self.grad_op = tf.gradients(self.energy_op, self.state)[0]
            self.sess.run(tf.initialize_all_variables())
            return ndims, nbatch


    def build_energy_op(self):
        """ Sets self.state and self.energy_op
        """
        raise NotImplementedError("this method must be defined to subclass TensorflowDistribution")


    @overrides(Distribution)
    def E_val(self, X):
        with self.graph.as_default():
            _, energy = self.sess.run([self.assign_op, self.energy_op], feed_dict={self.state_pl: X})
            return energy

    @overrides(Distribution)
    def dEdX_val(self, X):
        with self.graph.as_default():
            _, grad = self.sess.run([self.assign_op, self.grad_op], feed_dict={self.state_pl: X})
            return grad

    @overrides(Distribution)
    def gen_init_X(self):
        self.Xinit = self.init

    @overrides(Distribution)
    def __hash__(self):
        return hash((self.ndims, self.name))

class Funnel(TensorflowDistribution):
    """ This class implements the Funnel distribution as specified in Neal, 2003
    In particular:
      x_0 ~ N(0, scale^2)
      x_i ~ N(0, e^x_0); i in {1, ... ,ndims}
    """

    def __init__(self,scale=1.0, nbatch=50, ndims=10):
        self.scale = float(scale)
        self.ndims = ndims
        self.nbatch = nbatch
        self.gen_init_X()

        super(Funnel, self).__init__(name='Funnel')

    @overrides(TensorflowDistribution)
    def build_energy_op(self):
        with self.graph.as_default():
            self.state = tf.Variable(np.zeros((self.ndims, self.nbatch)), name='state', dtype=tf.float32)
            # [1, nbatch]
            e_x_0 = tf.neg((self.state[0, :] ** 2) / (self.scale ** 2), name='E_x_0')
            # [ndims - 1, nbatch]
            e_x_k = tf.neg((self.state[1:, :] ** 2) / tf.exp(self.state[0, :]), name='E_x_k')
            # [nbatch]
            self.energy_op = tf.reduce_sum(tf.add(e_x_0, e_x_k), 0, name='energy_op')


    @overrides(Distribution)
    def gen_init_X(self):
        x_0 = np.random.normal(scale=self.scale, size=(1, self.nbatch))
        x_k = np.random.normal(scale=np.exp(x_0), size=(self.ndims - 1, self.nbatch))
        self.Xinit = np.vstack((x_0, x_k))

    @overrides(Distribution)
    def __hash__(self):
        return hash((self.scale, self.ndims))

class TFGaussian(TensorflowDistribution):
    """ Standard gaussian implemented in tensorflow
    """
    def __init__(self, ndims=2, nbatch=100, sigma=1.):
        self.ndims  = ndims
        self.nbatch = nbatch
        self.sigma = sigma
        self.gen_init_X()

        super(TFGaussian, self).__init__(name='TFGaussian')

    @overrides(TensorflowDistribution)
    def build_energy_op(self):
        with self.graph.as_default():
            self.state = tf.Variable(np.zeros((self.ndims, self.nbatch)), name='state', dtype=tf.float32)
            self.energy_op = tf.reduce_sum(self.state ** 2, 0) / (2 * self.sigma ** 2)

    @overrides(Distribution)
    def gen_init_X(self):
        self.Xinit = np.random.randn(self.ndims, self.nbatch)

    @overrides(Distribution)
    def __hash__(self):
        return hash((self.ndims, self.sigma))
