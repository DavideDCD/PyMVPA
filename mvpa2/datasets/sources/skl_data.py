# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the PyMVPA package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Wrapper for sklearn datasets/data generators."""

__docformat__ = 'restructuredtext'

from mvpa2.base import externals

if externals.exists('skl', raise_=True):
    if externals.versions['skl'] >= '0.9':
        from sklearn import datasets as sklds
    else:
        from scikits.learn import datasets as sklds

    import inspect

    __all__ = []

    for fx in sklds.__dict__:
        if not (fx.startswith('make_') or fx.startswith('load_')) \
                or fx in ['load_filenames', 'load_files',
                          'load_sample_image', 'load_sample_images',
                          'load_svmlight_files', 'load_svmlight_file']:
            continue
        fx = getattr(sklds, fx)
        # argnames, varargs, varkw, defaults = inspect.getargspec(fx)
        argnames, varargs, varkw, defaults, kwonlyargs, kwonlydefaults, annotations = inspect.getfullargspec(fx)
        if defaults is not None:
            kwargs = list(zip(argnames[::-1], defaults[::-1]))[::-1]
        else:
            kwargs = tuple()
        args = argnames[:len(argnames) - len(kwargs)]
        sig = ''
        if len(args):
            sig += ', '.join(args)
        if len(kwargs):
            if len(sig):
                sig += ', '
            sig += ', '.join(['%s=%s' % (kw[0], repr(kw[1])) for kw in kwargs])
        if varargs:
            if len(sig):
                sig += ', '
            sig += '*%s' % varargs
        if varkw:
            if len(sig):
                sig += ', '
            sig += '**%s' % varkw

        pymvpa_fxname = 'skl_%s' % fx.__name__[5:]
        fxdef = '''
def %s(%s):
    """%s

    Notes
    -----
    This function has been auto-generated by wrapping %s() from the
    `sklearn <http://scikit-learn.org>`_ package. The documentation of
    this function has been kept verbatim. Consequently, the actual return
    value is not as described in the documentation, but the data is returned
    as a PyMVPA dataset.
    """
    from sklearn import datasets as sklds
    from mvpa2.datasets import Dataset
    data = sklds.%s(%s)
    if isinstance(data, tuple):
        ds = Dataset(data[0])
        if len(data) > 1:
            ds.sa['targets'] = data[1]
        if len(data) > 2:
            raise RuntimeError("sklearn function returned unexpected amount of data")
    else:
        ds = Dataset(data['data'])
        if 'DESCR' in data:
            ds.a['descr'] = data['DESCR']
        if 'feature_names' in data:
            ds.fa['names'] = data['feature_names']
        if 'target' in data:
            if 'target_names' in data:
                names = data['target_names']
                ds.sa['targets'] = [names[t] for t in data['target']]
            else:
                ds.sa['targets'] = data['target']
    return ds
''' % (pymvpa_fxname,
               sig,
               fx.__doc__,
               fx.__name__,
               fx.__name__,
               ', '.join(argnames))
        exec(fxdef)
        __all__.append(pymvpa_fxname)

