"""
========================================================================================
Wrap landlab component with the Basic Modeling Interface (:mod:`landlab.bmi.bmi_bridge`)
========================================================================================

.. sectionauthor:: Eric Hutton

Function reference
------------------

The `wrap_as_bmi` function wraps a landlab component class so that it
exposes a Basic Modelling Interface.

"""
import numpy as np
from bmipy import Bmi

from ..core import load_params
from ..core.model_component import Component
from ..framework.decorators import snake_case
from ..grid.create import grids_from_file


class TimeStepper(object):

    """Step through time.

    Parameters
    ----------
    start : float, optional
        Clock start time.
    stop : float, optional
        Stop time.
    step : float, optional
        Time step.

    Examples
    --------
    >>> from landlab.bmi import TimeStepper
    >>> time_stepper = TimeStepper()
    >>> time_stepper.start
    0.0
    >>> time_stepper.stop is None
    True
    >>> time_stepper.step
    1.0
    >>> time_stepper.time
    0.0
    >>> for _ in range(10): time_stepper.advance()
    >>> time_stepper.time
    10.0
    >>> time_stepper = TimeStepper(1., 13., 2.)
    >>> [time for time in time_stepper]
    [1.0, 3.0, 5.0, 7.0, 9.0, 11.0]
    """

    def __init__(self, start=0.0, stop=None, step=1.0):
        self._start = start
        self._stop = stop
        self._step = step

        self._time = start

    def __iter__(self):
        if self.stop is None:
            while 1:
                yield self._time
                self._time += self._step
        else:
            while self._time < self._stop:
                yield self._time
                self._time += self._step
        return

    @property
    def time(self):
        """Current time."""
        return self._time

    @property
    def start(self):
        """Start time."""
        return self._start

    @property
    def stop(self):
        """Stop time."""
        return self._stop

    @property
    def step(self):
        """Time Step."""
        return self._step

    @step.setter
    def step(self, new_val):
        """Change the time step."""
        self._step = new_val

    def advance(self):
        """Advance the time stepper by one time step."""
        self._time += self.step
        if self._stop is not None and self._time > self._stop:
            raise StopIteration()


def wrap_as_bmi(cls):
    """Wrap a landlab class so it exposes a BMI.

    Parameters
    ----------
    cls : class
        A landlab class that inherits from `Component`.

    Returns
    -------
    class
        A wrapped class that exposes a BMI.

    Examples
    --------
    >>> from landlab.bmi import wrap_as_bmi
    >>> from landlab.components.flexure import Flexure

    >>> BmiFlexure = wrap_as_bmi(Flexure)
    >>> flexure = BmiFlexure()

    >>> config = \"\"\"
    ... flexure:
    ...     eet: 10.e+3
    ...     method: flexure
    ... clock:
    ...     start: 0.
    ...     stop: 10.
    ...     step: 2.
    ... grid:
    ...     raster_model_grid:
    ...     - [20, 40]
    ...     - xy_spacing: [2000., 1000.]
    ... \"\"\"
    >>> flexure.initialize(config)
    >>> flexure.get_output_var_names()
    ('lithosphere_surface__elevation_increment',)
    >>> flexure.get_var_grid('lithosphere_surface__elevation_increment')
    0
    >>> flexure.get_grid_shape(0, np.empty(flexure.get_grid_rank(0), dtype=int))
    array([20, 40])
    >>> dz = np.empty(flexure.get_grid_size(0))
    >>> _ = flexure.get_value('lithosphere_surface__elevation_increment', dz)

    >>> np.all(dz == 0.)
    True
    >>> flexure.get_current_time()
    0.0

    >>> flexure.get_input_var_names()
    ('lithosphere__overlying_pressure_increment',)
    >>> load = np.zeros((20, 40), dtype=float)
    >>> load[0, 0] = 1.
    >>> flexure.set_value('lithosphere__overlying_pressure_increment', load)
    >>> flexure.update()
    >>> flexure.get_current_time()
    2.0
    >>> _ = flexure.get_value('lithosphere_surface__elevation_increment', dz)
    >>> np.all(dz == 0.)
    False
    """
    if not issubclass(cls, Component):
        raise TypeError("class must inherit from Component")

    class BmiWrapper(Bmi):
        __doc__ = """
        Basic Modeling Interface for the {name} component.
        """.format(
            name=cls.__name__
        ).strip()

        _cls = cls

        def __init__(self):
            self._base = None
            self._clock = None
            super(BmiWrapper, self).__init__()

        def get_component_name(self):
            """Name of the component."""
            return self._cls.name

        def get_input_var_names(self):
            """Names of the input exchange items."""
            return self._cls.input_var_names

        def get_output_var_names(self):
            """Names of the output exchange items."""
            return self._cls.output_var_names

        def get_current_time(self):
            """Current component time."""
            return self._clock.time

        def get_end_time(self):
            """Stop time for the component."""
            return self._clock.stop

        def get_start_time(self):
            """Start time of the component."""
            return self._clock.start

        def get_time_step(self):
            """Component time step."""
            return self._clock.step

        def get_time_units(self):
            """Time units used by the component."""
            raise NotImplementedError("get_time_units not implemented")

        def initialize(self, config_file):
            """Initialize the component from a file.

            BMI-wrapped Landlab components use input files in YAML format.
            Component-specific parameters are listed at the top level,
            followed by grid and then time information. An example input
            file looks like::

                flexure:
                    eet: 15.e+3
                clock:
                    start: 0
                    stop: 100.
                    step: 2.
                grid:
                    type: raster
                    shape: [20, 40]
                    spacing: [1000., 2000.]

            In this case, a `RasterModelGrid` is created (with the given shape
            and spacing) and passed to the underlying landlab component. The
            `eet=15000.` is also given to the component but as a keyword
            parameter. The BMI clock is initialized with the given parameters.

            Parameters
            ----------
            config_file : str or file_like
                YAML-formatted input file for the component.
            """
            grid = grids_from_file(config_file, section="grid")
            if not grid:
                raise ValueError("no grid in config file ({0})".format(config_file))
            elif len(grid) > 1:
                raise ValueError(
                    "multiple grids in config file ({0})".format(config_file)
                )
            else:
                grid = grid[0]

            params = load_params(config_file)
            params.pop("grid")
            clock_params = params.pop("clock")
            self._clock = TimeStepper(**clock_params)

            self._base = self._cls(grid, **params.pop(snake_case(cls.__name__), {}))

        def update(self):
            """Update the component one time step."""
            if hasattr(self._base, "update"):
                self._base.update()
            self._clock.advance()

        def update_frac(self, frac):
            """Update the component a fraction of a time step."""
            time_step = self.get_time_step()
            self._clock.step = time_step * frac
            self.update()
            self._clock.step = time_step

        def update_until(self, then):
            """Update the component until a given time."""
            n_steps = (then - self.get_current_time()) / self.get_time_step()
            for _ in range(int(n_steps)):
                self.update()
            self.update_frac(n_steps - int(n_steps))

        def finalize(self):
            """Clean-up the component."""
            pass

        def get_var_grid(self, name):
            """Get the grid id for a variable."""
            return 0

        def get_var_itemsize(self, name):
            """Get the size of elements of a variable."""
            return np.dtype("float").itemsize

        def get_var_nbytes(self, name):
            """Get the total number of bytes used by a variable."""
            return self.get_itemsize(name) * self._base.grid.number_of_nodes

        def get_var_type(self, name):
            """Get the data type for a variable."""
            return str(np.dtype("float"))

        def get_var_units(self, name):
            """Get the unit used by a variable."""
            return self._cls.var_units(name)

        def get_value_ref(self, name):
            """Get a reference to a variable's data."""
            return self._base.grid.at_node[name]

        def get_value(self, name, dest):
            """Get a copy of a variable's data."""
            dest[:] = self._base.grid.at_node[name]
            return dest

        def set_value(self, name, values):
            """Set the values of a variable."""
            if name in self.get_input_var_names():
                if name in self._base.grid.at_node:
                    self._base.grid.at_node[name][:] = values.flat
                else:
                    self._base.grid.at_node[name] = values
            else:
                raise KeyError("{name} is not an input item".format(name=name))

        def get_grid_origin(self, grid, origin):
            """Get the origin for a structured grid."""
            origin[:] = (self._base.grid.node_y[0], self._base.grid.node_x[0])
            return origin

        def get_grid_rank(self, grid):
            """Get the number of dimensions of a grid."""
            return 2

        def get_grid_shape(self, grid, shape):
            """Get the shape of a structured grid."""
            shape[:] = (
                self._base.grid.number_of_node_rows,
                self._base.grid.number_of_node_columns,
            )
            return shape

        def get_grid_spacing(self, grid, spacing):
            """Get the row and column spacing of a structured grid."""
            spacing[:] = (self._base.grid.dy, self._base.grid.dx)
            return spacing

        def get_grid_type(self, grid):
            """Get the type of grid."""
            return "uniform_rectilinear"

        def get_grid_edge_count(self, grid):
            return self._base.grid.number_of_links

        def get_grid_edge_nodes(self, grid, edge_nodes):
            return self._base.grid.nodes_at_link.reshape((-1,))

        def get_grid_face_count(self, grid):
            return self._base.grid.number_of_patches

        def get_grid_face_nodes(self, grid, face_nodes):
            return self._base.grid.nodes_at_patch

        def get_grid_node_count(self, grid):
            return self._base.grid.number_of_nodes

        def get_grid_nodes_per_face(self, grid, nodes_per_face):
            raise NotImplementedError("get_grid_nodes_per_face")

        def get_grid_size(self, grid):
            return self._base.grid.number_of_nodes

        def get_grid_x(self, grid, x):
            return self._base.grid.x_of_node

        def get_grid_y(self, grid, y):
            return self._base.grid.y_of_node

        def get_grid_z(self, grid, z):
            raise NotImplementedError("get_grid_z")

        def get_value_at_indices(self, name, dest, inds):
            raise NotImplementedError("get_value_at_indices")

        def get_value_ptr(self, name):
            raise NotImplementedError("get_value_ptr")

        def get_var_location(self, name):
            return self._base._var_mapping[name]

        def set_value_at_indices(self, name, inds, src):
            raise NotImplementedError("set_value_at_indices")

    BmiWrapper.__name__ = cls.__name__
    return BmiWrapper
