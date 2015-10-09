from mjhmc.search.objective import obj_func
from mjhmc.samplers.markov_jump_hmc import MarkovJumpHMC
from mjhmc.misc.distributions import ProductOfT 


def main(job_id, params):
    print "job id: {}, params: {}".format(job_id, params)
    return obj_func(MarkovJumpHMC, ProductOfT(nbatch=1), job_id, **params)