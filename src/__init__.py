"""UZ CS Clinic Appointment System.

The package is deliberately dependency-free at runtime.  All time is supplied
by an injected :class:`src.clock.Clock`; the wall clock is never read.
"""

__version__ = "1.0.0"
