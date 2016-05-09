from copy import copy

import numpy as np
from numpy import pi, sqrt, polyval

from ..wsolve import wpolyfit
from ..uncertainty import Uncertainty as U, interp

class FootprintData(object):
    def __init__(self, p, dp):
        self.p = p
        self.dp = dp
    def get_metadata(self):
        #return {"p": self.p.tolist(), "dp": self.dp.tolist()}
        return {
            "slope": self.p[0],
            "intercept": self.p[1],
            # these next are intentionally different from the names of 
            # the inputs fields in the footprint module, so that
            # they don't populate those fields when running manually.
            "slope_fit_error_": self.dp[0],
            "intercept_fit_error": self.dp[1]
        }

def fit_footprint(data, low, high, kind='line'):
    """
    Fit the footprint using data points over a range.

    Range should be a list of pairs of indices, one per data line that is
    to be simultaneously fitted.
    """
    # Join the ranges from the individual data sets
    x, y, dy = [], [], []
    for data_k in data:
        idx = np.ones_like(data_k.Qz, dtype='bool')
        if low is not None:
            idx = idx & (data_k.Qz >= low) 
        if high is not None:
            idx = idx & (data_k.Qz <= high)
        x.append(data_k.Qz[idx])
        y.append(data_k.v[idx])
        dy.append(data_k.dv[idx])
    
    x = np.hstack(x)
    y = np.hstack(y)
    dy = np.hstack(dy)
    if len(x):
        p, dp = _fit_footprint_data(x, y, dy, kind)
        return FootprintData(p, dp)
    else:
        return None


def fit_footprint_shared_range(data, low, high, kind='line'):
    r"""
    Fit the footprint using data points over a range.

    The fit is restricted to *low <= x <= high*.  *kind* can be 'plateau' if
    the footprint is a constant scale factor, 'slope' if the footprint should
    go through the origin, or 'line' if the footprint is a slope that does
    not go through the origin.

    Note: this algorithm is provided for compatibility with the older reflpak
    program.  New datasets need to include support for overlapping points
    with different $\Delta Q$.
    """
    # Join all the datasets
    x, y, dy = [], [], []
    for d in data:
        x.append(d.Qz)
        y.append(d.v)
        dy.append(d.dv)
    x = np.hstack(x)
    y = np.hstack(y)
    dy = np.hstack(dy)
    

    if low > high:
        low, high = high, low
    idx = (x >= low) & (x <= high)
    x, y, dy = x[idx], y[idx], dy[idx]
    p, dp = _fit_footprint_data(x, y, dy, kind)
    return FootprintData(p, dp)


def apply_fitted_footprint(data, fitted_footprint, range):
    p, dp = fitted_footprint.p, fitted_footprint.dp
    Qmin, Qmax = range
    if Qmax is None:
        Qmax = data.Qz.max()
    if Qmin is None:
        Qmin = data.Qz.min()
    footprint = _generate_footprint_curve(p, dp, data.Qz, Qmin, Qmax)
    _apply_footprint(data, footprint)


def apply_measured_footprint(data, measured_footprint):
    x = measured_footprint.Qz
    y = U(measured_footprint.v, measured_footprint.dv**2)
    footprint  = interp(data.Qz, x, y, left=U(1.0,0.0), right=U(1.0,0.0))
    _apply_footprint(data, footprint)


def apply_abinitio_footprint(data, A, B, Io, length, offset):
    if A > B:
        raise ValueError("A must be less than B")
    y = _abinitio_footprint(data.slit.x, data.Qz, data.detector.wavelength,
                            A, B, Io, length, offset)
    footprint = U(y, 0.0)
    _apply_footprint(data, footprint)


def _apply_footprint(data, footprint):
    refl = U(data.v, data.dv**2)
    # Ignore footprint <= 0
    bad_correction = (footprint.x <= 0.)  # type: np.ndarray
    if bad_correction.any():
        footprint = copy(footprint)
        footprint.x = copy(footprint.x)
        footprint.x[bad_correction] = 1.0
        footprint.variance[bad_correction] = 0.0
    corrected_refl = refl/footprint
    data.v, data.dv = corrected_refl.x, corrected_refl.dx


def _fit_footprint_data(x, y, dy, kind):
    """
    Fit the footprint from the measurement in *x*, *y*, *dy*.

    The fit is restricted to *low <= x <= high*.  *kind* can be 'plateau' if
    the footprint is a constant scale factor, 'slope' if the footprint should
    go through the origin, or 'line' if the footprint is a slope that does
    not go through the origin.
    """
    if len(x) < 2:
        p, dp = np.array([0., 1.]), np.array([0., 0.])
    elif kind== 'plateau':
        poly = wpolyfit(abs(x), y, dy, degree=0, origin=False)
        p, dp = poly.coeff, poly.std
        p, dp = np.hstack((0, p)), np.hstack((0, dp))
    elif kind == 'slope':
        poly = wpolyfit(abs(x), y, dy, degree=1, origin=True)
        p, dp = poly.coeff, poly.std
    elif kind == 'line':
        poly = wpolyfit(abs(x), y, dy, degree=1, origin=False)
        p, dp = poly.coeff, poly.std
    else:
      raise TypeError('unknown footprint type %r'%kind)
    return p, dp


def _generate_footprint_curve(p, dp, x, xmin, xmax):
    """
    Return the footprint correction for the fitted footprint *p*, *dp*.

    The footprint is calculated at the measured points *x*, and applied
    between *xmin* and *xmax*.
    """
    ## order min and max correctly
    xmin, xmax = abs(xmin), abs(xmax)
    if xmin > xmax:
        xmin, xmax = xmax, xmin

    ## linear between Qmin and Qmax
    y = polyval(p,abs(x))
    var_y = polyval(dp**2, x**2)

    ## ignore values below Qmin
    y[abs(x) < xmin] = 1.
    var_y[abs(x) < xmin] = 0.
    ## stretch Qmax to the end of the range
    y[abs(x) > xmax] = polyval(p, xmax)
    var_y[abs(x) > xmax] = polyval(dp**2, xmax**2)

    return U(y, var_y)


def apply(fp, R):
    """
    Scale refl by footprint, ignoring zeros
    """
    x, y, dy = R
    correction = fp.calc()
    correction += (correction == 0)  # avoid divide by zero errors
    corrected_y = y / correction
    corrected_dy = dy / correction
    return corrected_y, corrected_dy


def _abinitio_footprint(slit, Qz, wavelength, A, B, Io, length, offset):
    L1 = length/2. + offset
    L2 = length/2. - offset

    wA = slit * A/2.
    wB = slit * B/2.

    # Algorithm for converting Qx-Qz to alpha-beta:
    #   beta = 2 asin(wavelength/(2 pi) sqrt(Qx^2+Qz^2)/2) * 180/pi
    #        = asin(wavelength sqrt(Qx^2+Qz^2) /(4 pi)) / (pi/360)
    #   theta = atan2(Qx,Qz) * 180/pi
    #   alpha = theta + beta/2
    # Since we are in the specular condition, Qx = 0
    #   Qx = 0 => theta => 0 => alpha = beta/2
    #          => alpha = 2 asin(wavelength sqrt(Qz^2)/(4 pi)) / 2
    #          => alpha = asin (wavelength Qz / 4 pi) in radians
    # Length of intersection d = L sin (alpha)
    #          => d = L sin (asin (wavelength Qz / 4 pi))
    #          => d = L wavelength Qz/(4 pi)

    #: low edge of the sample
    low = L2*wavelength * Qz / (4 * pi)  # low edge of the sample
    high = L1*wavelength * Qz / (4 * pi)  # high edge of the sample
    Alow = integrate(wA, wB, low)
    Ahigh = integrate(wA, wB, high)

    # Total area of intersection is the sum of the areas of the regions
    # Normalize that by the total area of the beam (A+B)/2 and scale by
    # the incident intensity.  Note that the factor of 2 is already
    # incorporated into wA and wB.
    abfoot_y = Io * (Alow + Ahigh) / (wA+wB)
    return abfoot_y

def integrate(wA, wB, edge):
    # if wB==wA then we have 0 * (1-0/(2*0)) which is zero.  To avoid
    # numerical problems, we force the minimum possible step.
    if wA == wB:
        wB = wA*(1.+1e-16)

    # Compute B as area under triangular region
    # Length of intersection in triangular region
    B = (edge-wA)*((edge>wA) & (edge<wB)) + (wB-wA)*(edge>=wB)
    # Area of intersection in triangular region;
    B *= (1 - B/(2*(wB-wA)+1e-16))
    # Area of intersection in rectangular region
    area = edge*(edge<=wA) + wA*(edge>wA) + B

    return area


def spill(slit, Qz, wavelength, detector_distance, detector_width, thickness,
          A, B, Io, length, offset):
    """
    The primary beam on the detector is the beam reflected from the
    sample. Beam spill is the portion of the beam which is not
    intercepted by the sample but is still incident on the detector.
    This happens at low angles.  Above the sample this is fairly
    simple, being just that portion which is not reflected.  Below
    the sample there is the effect of the the thickness of the
    sample which shades the beam plus the fact that the detector is
    moving out of the path of the beam. At low angles there will also
    be some beam transmitted through the sample, but this is assumed
    to be orders of magnitude smaller than the direct beam so we can
    safely ignore it.  The final effect is the width of the back
    slits which cuts down the transmitted beam.
    """
    if True:
        raise NotImplementedError()

    # It is too difficult to compute beam spill for now.  Leave this
    # pseudo code around in case we decide to implement it later.
    L1 = length/2. + offset
    L2 = length/2. - offset
    wA = slit * A/2.
    wB = slit * B/2.

    # low: low edge of the sample
    # high: high edge of the sample
    # low2: low edge of the sample bottom
    # high2: max(sample,detector)
    # det: low edge of the detector
    # refl: area of intersection
    # spill_lo: area of spill below
    # spill_hi: area of spill above

    # Algorithm for converting Qx-Qz to alpha-beta:
    #   beta = 2 asin(wavelength/(2 pi) sqrt(Qx^2+Qz^2)/2) * 180/pi
    #        = asin(wavelength sqrt(Qx^2+Qz^2) /(4 pi)) / (pi/360)
    #   theta = atan2(Qx,Qz) * 180/pi
    #   alpha = theta + beta/2
    # Since we are in the specular condition, Qx = 0
    #   Qx = 0 => theta => 0 => alpha = beta/2
    #          => alpha = 2 asin(wavelength sqrt(Qz^2)/(4 pi)) / 2
    #          => alpha = asin (wavelength Qz / 4 pi) in radians
    # Length of intersection d = L sin (alpha)
    #          => d = L sin (asin (wavelength Qz / 4 pi))
    #          => d = L wavelength Qz/(4 pi)
    low = -L2*wavelength * Qz / (4 * pi)
    high = L1*wavelength * Qz / (4 * pi)
    area = integrate(wA, wB, low, high)

    # From trig, the bottom of the detector is located at
    #    d sin T - D/2 cos T
    # where d is the detector distance and D is the detector length.
    # Using cos(asin(x)) = sqrt(1-x^2), this is
    #    d wavelength Qz/4pi - D/2 sqrt(1-(wavelength Qz/4pi)^2)
    det = (detector_distance*wavelength*Qz/(4*pi)
           - detector_width/2 * sqrt(1 - (wavelength*Qz/(4*pi))**2))

    # From trig, the projection of thickness in the plane normal to
    # the beam is
    #    thickness/cos(theta) = thickness/sqrt(1-(wavelength Qz/4 pi)^2)
    # since cos(asin(x)) = sqrt(1-x^2).
    low2 = low - thickness / sqrt(1 - (wavelength*Qz/(4*pi))**2)
    high2 = det*(det>=high) + high*(det<high)
    spill_low = integrate(wA, wB, det, low2)
    spill_high = integrate(wA, wB, high2, wB)

    # Total area of intersection is the sum of the areas of the regions
    # Normalize that by the total area of the beam (A+B)/2
    abfoot_y = 2 * Io * (area + spill_low + spill_high) / (wA+wB)
    return abfoot_y
