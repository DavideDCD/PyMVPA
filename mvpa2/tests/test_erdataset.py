# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the PyMVPA package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
'''Tests for the event-related dataset'''

from mvpa2.testing import *
from mvpa2.datasets import dataset_wizard
from mvpa2.mappers.flatten import FlattenMapper
from mvpa2.mappers.boxcar import BoxcarMapper
from mvpa2.mappers.fx import FxMapper
from mvpa2.datasets.eventrelated import (
    find_events,
    eventrelated_dataset,
    fit_event_hrf_model,
    extract_boxcar_event_samples,
    get_contrasts,
)
from mvpa2.datasets.sources import load_example_fmri_dataset
from mvpa2.mappers.zscore import zscore


def test_erdataset():
    # 3 chunks, 5 targets, blocks of 5 samples each
    nchunks = 3
    ntargets = 5
    blocklength = 5
    nfeatures = 2
    targets = np.tile(np.repeat(range(ntargets), blocklength), nchunks)
    chunks = np.repeat(np.arange(nchunks), ntargets * blocklength)
    samples = np.repeat(
                np.arange(nchunks * ntargets * blocklength),
                nfeatures).reshape(-1, nfeatures)
    ds = dataset_wizard(samples, targets=targets, chunks=chunks)
    # check if events are determined properly
    evs = find_events(targets=ds.sa.targets, chunks=ds.sa.chunks)
    for ev in evs:
        assert_equal(ev['duration'], blocklength)
    assert_equal(ntargets * nchunks, len(evs))
    for t in range(ntargets):
        assert_equal(len([ev for ev in evs if ev['targets'] == t]),
                     nchunks)
    # now turn `ds` into an eventreleated dataset
    erds = eventrelated_dataset(ds, evs)
    # the only unprefixed sample attributes are 
    assert_equal(sorted([a for a in ds.sa if not a.startswith('event')]),
                 ['chunks', 'targets'])
    # samples as expected?
    assert_array_equal(erds.samples[0],
                       np.repeat(np.arange(blocklength), nfeatures))
    # that should also be the temporal feature offset
    assert_array_equal(erds.samples[0], erds.fa.event_offsetidx)
    assert_array_equal(erds.sa.event_onsetidx, np.arange(0,71,5))
    # finally we should see two mappers
    assert_equal(len(erds.a.mapper), 2)
    assert_true(isinstance(erds.a.mapper[0], BoxcarMapper))
    assert_true(isinstance(erds.a.mapper[1], FlattenMapper))
    # check alternative event mapper
    # this one does temporal compression by averaging
    erds_compress = eventrelated_dataset(
                        ds, evs, event_mapper=FxMapper('features', np.mean))
    assert_equal(len(erds), len(erds_compress))
    assert_array_equal(erds_compress.samples[:,0], np.arange(2,73,5))
    #
    # now check the same dataset with event descretization
    tr = 2.5
    ds.sa['time'] = np.arange(nchunks * ntargets * blocklength) * tr
    evs = [{'onset': 4.9, 'duration': 6.2}]
    # doesn't work without conversion
    assert_raises(ValueError, eventrelated_dataset, ds, evs)
    erds = eventrelated_dataset(ds, evs, time_attr='time')
    assert_equal(len(erds), 1)
    assert_array_equal(erds.samples[0], np.repeat(np.arange(1,5), nfeatures))
    assert_array_equal(erds.sa.orig_onset, [evs[0]['onset']])
    assert_array_equal(erds.sa.orig_duration, [evs[0]['duration']])
    assert_array_almost_equal(erds.sa.orig_offset, [2.4])
    assert_array_equal(erds.sa.time, [np.arange(2.5, 11, 2.5)])
    # now with closest match
    erds = eventrelated_dataset(ds, evs, time_attr='time', match='closest')
    expected_nsamples = 3
    assert_equal(len(erds), 1)
    assert_array_equal(erds.samples[0],
                       np.repeat(np.arange(2, 2+expected_nsamples),
                                nfeatures))
    assert_array_equal(erds.sa.orig_onset, [evs[0]['onset']])
    assert_array_equal(erds.sa.orig_duration, [evs[0]['duration']])
    assert_array_almost_equal(erds.sa.orig_offset, [-0.1])
    assert_array_equal(erds.sa.time, [np.arange(5.0, 11, 2.5)])
    # now test the way back
    results = np.arange(erds.nfeatures)
    assert_array_equal(erds.a.mapper.reverse1(results),
                       results.reshape(expected_nsamples, nfeatures))
    # what about multiple results?
    nresults = 5
    results = dataset_wizard([results] * nresults)
    # and let's have an attribute to make it more difficult
    results.sa['myattr'] = np.arange(5)
    rds = erds.a.mapper.reverse(results)
    assert_array_equal(rds,
                       results.samples.reshape(nresults * expected_nsamples,
                                               nfeatures))
    assert_array_equal(rds.sa.myattr, np.repeat(results.sa.myattr,
                                               expected_nsamples))
    evs = [dict(onset=12, duration=2), dict(onset=70, duration=3)]
    evds = extract_boxcar_event_samples(ds, evs)
    # it goes for the max of all durations
    assert_equal(evds.shape, (len(evs), 3 * ds.nfeatures))
    # overide duration
    evds = extract_boxcar_event_samples(ds, evs, event_duration=1)
    assert_equal(evds.shape, (len(evs), 1 * ds.nfeatures))
    assert_equal(np.unique(evds.samples[1]), 70)
    # overide onset
    evds = extract_boxcar_event_samples(ds, evs, event_offset=2)
    assert_equal(evds.shape, (len(evs), 3 * ds.nfeatures))
    assert_equal(np.unique(evds.samples[1, :nfeatures]), 72)
    # overide both
    evds = extract_boxcar_event_samples(ds, evs, event_offset=-2,
                                        event_duration=1)
    assert_equal(evds.shape, (len(evs), 1 * ds.nfeatures))
    assert_equal(np.unique(evds.samples[1]), 68)

def test_hrf_modeling():
    skip_if_no_external('nibabel')
    skip_if_no_external('nipy') # ATM relies on NiPy's GLM implementation
    # taking subset of the dataset to speed testing up
    ds = load_example_fmri_dataset('25mm', literal=True)[{'chunks': [0, 1]}, :3]
    # TODO: simulate short dataset with known properties and use it
    # for testing
    events = find_events(targets=ds.sa.targets, chunks=ds.sa.chunks)
    tr = ds.a.imghdr['pixdim'][4]
    for ev in events:
        for a in ('onset', 'duration'):
            ev[a] = ev[a] * tr
    evds = eventrelated_dataset(ds, events, time_attr='time_coords',
                                condition_attr='targets',
                                design_kwargs=dict(drift_model='blank'),
                                glmfit_kwargs=dict(model='ols'),
                                model='hrf')
    # same voxels
    assert_equal(ds.nfeatures, evds.nfeatures)
    assert_array_equal(ds.fa.voxel_indices, evds.fa.voxel_indices)
    # one sample for each condition, plus constant
    assert_equal(sorted(ds.sa['targets'].unique), sorted(evds.sa.targets))
    assert_equal(evds.a.add_regs.sa.regressor_names[0], 'constant')
    # with centered data
    zscore(ds)
    evds_demean = eventrelated_dataset(ds, events, time_attr='time_coords',
                                condition_attr='targets',
                                design_kwargs=dict(drift_model='blank'),
                                glmfit_kwargs=dict(model='ols'),
                                model='hrf')
    # after demeaning the constant should consume a lot less
    assert(evds.a.add_regs[0].samples.mean()
           > evds_demean.a.add_regs[0].samples.mean())
    # from eyeballing the sensitivity example -- would be better to test this on
    # the tutorial data
    assert(evds_demean[evds.sa.targets == 'shoe'].samples.max() \
           > evds_demean[evds.sa.targets == 'bottle'].samples.max())
    # HRF models
    assert('regressors' in evds.sa)
    assert('regressors' in evds.a.add_regs.sa)
    assert_equal(evds.sa.regressors.shape[1], len(ds))

    # custom regressors
    evds_regrs = eventrelated_dataset(ds, events, time_attr='time_coords',
                                condition_attr='targets',
                                regr_attrs=['time_indices'],
                                design_kwargs=dict(drift_model='blank'),
                                glmfit_kwargs=dict(model='ols'),
                                model='hrf')
    # verify that nothing screwed up time_coords
    assert_equal(ds.sa.time_coords[0], 0)
    assert_equal(len(evds_regrs), len(evds))
    # one more output sample in .a.add_regs
    assert_equal(len(evds_regrs.a.add_regs) - 1, len(evds.a.add_regs))
    # comes last before constant
    assert_equal('time_indices', evds_regrs.a.add_regs.sa.regressor_names[-2])
    # order of main regressors is unchanged
    assert_array_equal(evds.sa.targets, evds_regrs.sa.targets)

    # custom multiple regressors
    ds.sa['time_indices_squared'] = ds.sa.time_indices ** 2
    # custom regressors
    evds_regrs = eventrelated_dataset(ds, events, time_attr='time_coords',
                                condition_attr='targets',
                                regr_attrs=['time_indices', 'time_indices_squared'],
                                design_kwargs=dict(drift_model='blank'),
                                glmfit_kwargs=dict(model='ols'),
                                model='hrf')
    # verify that nothing screwed up time_coords
    assert_equal(ds.sa.time_coords[0], 0)
    assert_equal(len(evds_regrs), len(evds))
    # two more output samples in .a.add_regs
    assert_equal(len(evds_regrs.a.add_regs) - 2, len(evds.a.add_regs))
    # come last before constant
    assert_array_equal(
        ['time_indices', 'time_indices_squared'],
        evds_regrs.a.add_regs.sa.regressor_names[-3:-1])
    # order of main regressors is unchanged
    assert_array_equal(evds.sa.targets, evds_regrs.sa.targets)

    # custom multiple regressors with multidimensional one
    ds.sa['time_indices_powers'] = np.vstack([ds.sa.time_indices ** 2,
                                              ds.sa.time_indices ** 3]).T
    # custom regressors
    evds_regrs = eventrelated_dataset(ds, events, time_attr='time_coords',
                                condition_attr='targets',
                                regr_attrs=['time_indices', 'time_indices_powers'],
                                design_kwargs=dict(drift_model='blank'),
                                glmfit_kwargs=dict(model='ols'),
                                model='hrf')
    # verify that nothing screwed up time_coords
    assert_equal(ds.sa.time_coords[0], 0)
    assert_equal(len(evds_regrs), len(evds))
    # three more output samples in .a.add_regs
    assert_equal(len(evds_regrs.a.add_regs) - 3, len(evds.a.add_regs))
    # come last before constant
    assert_array_equal(
        ['time_indices', 'time_indices_powers.0', 'time_indices_powers.1'],
        evds_regrs.a.add_regs.sa.regressor_names[-4:-1])
    # order of main regressors is unchanged
    assert_array_equal(evds.sa.targets, evds_regrs.sa.targets)

    # custom regressors from external sources
    evds_regrs = eventrelated_dataset(ds, events, time_attr='time_coords',
                                condition_attr='targets',
                                regr_attrs=['time_coords'],
                                design_kwargs=dict(drift_model='blank',
                                                   add_regs=np.linspace(1, -1, len(ds))[None].T,
                                                   add_reg_names=['negative_trend']),
                                glmfit_kwargs=dict(model='ols'),
                                model='hrf')
    assert_equal(len(evds_regrs), len(evds))
    # But we got one more in additional regressors
    assert_equal(len(evds_regrs.a.add_regs) - 2, len(evds.a.add_regs))
    # comes last before constant
    assert_array_equal(['negative_trend', 'time_coords', 'constant'],
                       evds_regrs.a.add_regs.sa.regressor_names)
    # order is otherwise unchanged
    assert_array_equal(evds.sa.targets, evds_regrs.sa.targets)

    # HRF models with estimating per each chunk
    assert_equal(ds.sa.time_coords[0], 0)
    evds_regrs = eventrelated_dataset(ds, events, time_attr='time_coords',
                                condition_attr=['targets', 'chunks'],
                                regr_attrs=['time_indices'],
                                design_kwargs=dict(drift_model='blank'),
                                glmfit_kwargs=dict(model='ols'),
                                model='hrf')
    assert_true('add_regs' in evds_regrs.a)
    assert_true('time_indices' in evds_regrs.a.add_regs.sa.regressor_names)

    assert_equal(len(ds.UC) * len(ds.UT), len(evds_regrs))
    assert_equal(len(evds_regrs.UC) * len(evds_regrs.UT), len(evds_regrs))

    from mvpa2.mappers.fx import mean_group_sample
    evds_regrs_meaned = mean_group_sample(['targets'])(evds_regrs)
    assert_array_equal(evds_regrs_meaned.T, evds.T) # targets should be the same

    #corr = np.corrcoef(np.vstack((evds.samples, evds_regrs_meaned)))
    #import pydb; pydb.debugger()
    #pass
    #i = 1


def test_get_contrasts():
    # preamble borrowed from the previous test
    skip_if_no_external('nibabel')
    skip_if_no_external('nipy')  # ATM relies on NiPy's GLM implementation
    # taking subset of the dataset to speed testing up
    ds = load_example_fmri_dataset('25mm', literal=True)[{'chunks': [0, 1]}, :3]
    # TODO: simulate short dataset with known properties and use it
    # for testing
    events = find_events(targets=ds.sa.targets, chunks=ds.sa.chunks)
    tr = ds.a.imghdr['pixdim'][4]
    for ev in events:
        for a in ('onset', 'duration'):
            ev[a] = ev[a] * tr
    evds = fit_event_hrf_model(
        ds, events=events, time_attr='time_coords',
        condition_attr='targets',
        design_kwargs=dict(drift_model='blank'),
        glmfit_kwargs=dict(model='ols'),
        return_model=True,
    )
    # Simple one -- stat per each condition
    cons = get_contrasts(evds)
    # and let's get p-values
    cons_p = get_contrasts(evds, fxname='p_value')
    # Without contrasts explicitly prescribed -- there will be one per each
    # condition
    assert_array_equal(cons.UT, evds.UT)
    # and per each feature
    assert_equal(cons.shape, (len(evds.UT), evds.nfeatures))
    assert_array_less(cons_p, 1)
    assert_array_less(0, cons_p)

    cons_fh = get_contrasts(
        evds,
        contrasts={
            'face-house': {'face': 1, 'house': -1},
            'betterface': {'face': 1, 'house': -0.5, 'scrambledpix': -0.5}
        },
    )

    # print(cons_fh.samples)
    assert_array_equal(cons_fh.UT, ['betterface', 'face-house'])

    # and nipy does one tailed test so all p-values should correspond to z-s
    skip_if_no_external('scipy')
    import scipy.stats.distributions as ssd
    assert_array_almost_equal(ssd.norm().isf(cons_p), cons)

