# Licensed under a 3-clause BSD style license - see LICENSE.rst
from __future__ import absolute_import, division, unicode_literals, print_function
"""
User oriented WCS tools.
"""
import functools
from astropy.modeling.core import Model
from astropy.modeling import projections
from astropy.modeling import models
from astropy import coordinates as coord

from .wcs import WCS
from . import coordinate_frames
from .utils import UnsupportedTransformError, UnsupportedProjectionError
from .utils import _compute_lon_pole


__all__ = ['wcs_from_fiducial']


def wcs_from_fiducial(fiducial, coordinate_frame=None, projection=None,
                      transform=None, name='', domain=None):
    """
    Create a WCS object from a fiducial point in a coordinate frame.

    If an additional transform is supplied it is prepended to the projection.

    Parameters
    ----------
    fiducial : `~astropy.coordinates.SkyCoord` or tuple of float
        One of:
            A location on the sky in some standard coordinate system.
            A Quantity with spectral units.
            A list of the above.
    coordinate_frame : ~gwcs.coordinate_frames.CoordinateFrame`
        The output coordinate frame.
        If fiducial is not an instance of `~astropy.coordinates.SkyCoord`,
        ``coordinate_frame`` is required.
    projection : `~astropy.modeling.projections.Projection`
        Projection instance - required if there is a celestial component in
        the fiducial.
    transform : `~astropy.modeling.Model` (optional)
        An optional tranform to be prepended to the transform constructed by
        the fiducial point. The number of outputs of this transform must equal
        the number of axes in the coordinate frame.
    name : str
        Name of this WCS.
    domain : list of dicts
        Domain of this WCS. The format is a list of dictionaries for each
        axis in the input frame
        [{'lower': lowx, 'upper': highx, 'includes_lower': bool, 'includes_upper': bool}]
    """
    if transform is not None:
        if not isinstance(transform, Model):
            raise UnsupportedTransformError("Expected transform to be an instance"
                                            "of astropy.modeling.Model")
        transform_outputs = transform.n_outputs
    if isinstance(fiducial, coord.SkyCoord):
        coordinate_frame = coordinate_frames.CelestialFrame(reference_frame=fiducial.frame,
                                                            unit=(fiducial.spherical.lon.unit,
                                                                  fiducial.spherical.lat.unit))
        fiducial_transform = _sky_transform(fiducial, projection)
    elif isinstance(coordinate_frame, coordinate_frames.CompositeFrame):
        trans_from_fiducial = []
        for item in coordinate_frame.frames:
            ind = coordinate_frame.frames.index(item)
            try:
                model = frame2transform[item.__class__](fiducial[ind], projection=projection)
            except KeyError:
                raise TypeError("Coordinate frame {0} is not supported".format(item))
            trans_from_fiducial.append(model)
        fiducial_transform = functools.reduce(lambda x, y: x & y,
                                              [tr for tr in trans_from_fiducial])
    else:
        # The case of one coordinate frame with more than 1 axes.
        try:
            fiducial_transform = frame2transform[coordinate_frame.__class__](fiducial, projection=projection)
        except KeyError:
            raise TypeError("Coordinate frame {0} is not supported".format(coordinate_frame))

    if transform is not None:
        forward_transform = transform | fiducial_transform
    else:
        forward_transform = fiducial_transform
    if domain is not None:
        if len(domain) != forward_transform.n_outputs:
            raise ValueError("Expected the number of items in 'domain' to be equal to the "
                             "number of outputs of the forawrd transform.")
        forward_transform.meta['domain'] = domain
    return WCS(output_frame=coordinate_frame, forward_transform=forward_transform,
               name=name)


def _verify_projection(projection):
    if projection is None:
        raise ValueError("Celestial coordinate frame requires a projection to be specified.")
    if not isinstance(projection, projections.Projection):
        raise UnsupportedProjectionError(projection)


def _sky_transform(skycoord, projection):
    """
    A sky transform is a projection, followed by a rotation on the sky.
    """
    _verify_projection(projection)
    lon_pole = _compute_lon_pole(skycoord, projection)
    if isinstance(skycoord, coord.SkyCoord):
        lon, lat = skycoord.spherical.lon, skycoord.spherical.lat
    else:
        lon, lat = skycoord
    sky_rotation = models.RotateNative2Celestial(lon, lat, lon_pole)
    return projection | sky_rotation


def _spectral_transform(fiducial, **kwargs):
    """
    A spectral transform is a shift by the fiducial.
    """
    return models.Shift(fiducial)


def _frame2D_transform(fiducial, **kwargs):
    fiducial_transform = functools.reduce(lambda x, y: x & y,
                                          [models.Shift(val) for val in fiducial])
    return fiducial_transform


frame2transform = {coordinate_frames.CelestialFrame: _sky_transform,
                   coordinate_frames.SpectralFrame: _spectral_transform,
                   coordinate_frames.Frame2D: _frame2D_transform
                   }