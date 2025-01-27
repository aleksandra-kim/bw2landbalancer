import bw2data as bd
import numpy as np
import warnings
import pyprind
from .activity_land_balancer import ActivityLandBalancer
from presamples import create_presamples_package, split_inventory_presamples


class DatabaseLandBalancer:
    """Used to create balanced land samples to override unbalanced sample

    Developed to bring some sanity to independently sampled land exchange
    values, specifically for the ecoinvent database. Because different land
    exchanges in this database are not parameterized (at least after datasets
    have gone through system modelling algorithms), the independently sampled
    land transformation exchange values result in faulty land transformation
    balances at an individual unit processes level.

    This database-level package and its associated activity-level
    package `ActivityLandBalancer` rebalance land samples to ensure that the
    ratio of ratio of "land transformation from" to "land transformation to"
    is maintained across MonteCarlo iterations. The balanced samples can be
    stored in a `presamples` package, see https://presamples.readthedocs.io/

    This package has database-level attributes and methods. It identifies and
    classifies land exchanges in a database. Actual sample generation
    is carried out in activity-level class `ActivityLandBalancer`, called here
    from method `add_samples_for_act`.

    Parameters:
    -----------
       database_name: string
           Name of the LCI database in the brightway2 project
       biosphere: string, default='biosphere3'
           Name of the biosphere database in the brighway2 database
       group: string, default='land'
           Name of the parameter group name. Used in the generation of samples.
       land_from_patterns: list of strings, default ['Transformation, from']
           List of string patterns identifying land states prior to transformation
       land_to_patterns: list of strings, default ['Transformation, to']
           List of string patterns identifying land states after transformation

    Attributes:
    -----------
       all_land_keys: list
           List of all keys of land elementary flows
       land_in_keys: list
           List of all keys of elementary flows associated with land states prior
           to transformation
       land_out_keys: list
           List of all keys of elementary flows associated with land states after
            transformation
       database_name: string
           Name of the LCI database in the brightway2 project
       biosphere: string, default='biosphere3'
           Name of the biosphere database in the brighway2 database
       group: string, default='land'
           Name of the parameter group name. Used in the generation of samples.
       matrix_indices: list
           List of numpy structured arrays containing the matrix indices associated
           with samples
       matrix_samples: list
           List of numpy arrays with samples
    """
    def __init__(
        self,
        database_name,
        biosphere='biosphere3',
        group="land",
        land_from_patterns=('Transformation, from', ),
        land_to_patterns=('Transformation, to', ),
    ):

        # Check that the database exists in the current project
        print("Validating data")
        if database_name not in bd.databases:
            raise ValueError("Database {} not imported".format(database_name))
        self.database_name = database_name
        if biosphere not in bd.databases:
            raise ValueError("Database {} not imported".format(biosphere))
        self.biosphere = biosphere
        self.group = group
        self.matrix_indices = []
        self.matrix_samples = None

        print("Getting information on land transformation exchanges")
        self.land_in_keys = []
        for ef in bd.Database(self.biosphere):
            for land_from_pattern in land_from_patterns:
                if land_from_pattern in ef['name']:
                    self.land_in_keys.append(ef.key)
        self.land_out_keys = []
        for ef in bd.Database(self.biosphere):
            for land_to_pattern in land_to_patterns:
                if land_to_pattern in ef['name']:
                    self.land_out_keys.append(ef.key)

        self.all_land_keys = self.land_in_keys + self.land_out_keys

    def add_samples_for_act(self, act_key, iterations):
        """Add samples and indices for given activity

        Actual samples generated by a ActivityLandBalancer instance.
        The samples and associated matrix indices are formatted for writing
        presamples and are respectively stored in the matrix_samples and
        matrix_indices attributes.

        Parameters:
        -----------
           act_key: tuple
               Key of target activity in database
           iterations: int
               Number of iterations in generated samples
        """
        ab = ActivityLandBalancer(act_key, self)
        for data in ab.generate_samples(iterations):
            if len(data[1][0]) == 2:
                for row in data[1]:
                    self.matrix_indices.append((row[0], row[1], 'biosphere'))
            else:
                self.matrix_indices.extend(data[1])
            if self.matrix_samples is None:
                self.matrix_samples = data[0]
            else:
                self.matrix_samples = np.concatenate([self.matrix_samples, data[0]], axis=0)

    def add_samples_for_all_acts(self, iterations):
        """Add samples and indices for all activities in database

        Iterates through all activities in database and calls activity-
        level method add_samples_for_act

        Parameters:
        -----------
           iterations: int
               Number of iterations in generated samples

        """
        act_keys = [act.key for act in bd.Database(self.database_name)]
        for act_key in pyprind.prog_bar(act_keys):
            self.add_samples_for_act(bd.get_activity(act_key), iterations)

    def create_presamples(self, name=None, id_=None, overwrite=False, dirpath=None, seed='sequential'):
        """Create a presamples package from generated samples

        Parameters
        -----------
           name: str, optional
               A human-readable name for these samples.
           \id_: str, optional
               Unique id for this collection of presamples. Optional, generated automatically if not set.
           overwrite: bool, default=False
               If True, replace an existing presamples package with the same ``\id_`` if it exists.
           dirpath: str, optional
               An optional directory path where presamples can be created.
               If None, a subdirectory in the ``project`` folder.
           seed: {None, int, "sequential"}, optional, default="sequential"
               Seed used by indexer to return array columns in random order. Can be an integer, "sequential" or None.
        """
        if not all([self.matrix_samples is not None, self.matrix_indices]):
            warnings.warn(
                "No presamples created because there were no matrix data. "
                "Make sure to run `add_samples_for_all_acts` or "
                "`add_samples_for_act` for a set of acts first."
            )
            return

        id_, dirpath = create_presamples_package(
            matrix_data=split_inventory_presamples(self.matrix_samples, self.matrix_indices),
            name=name, id_=id_, overwrite=overwrite, dirpath=dirpath, seed=seed)
        print("Presamples with id_ {} written at {}".format(id_, dirpath))
        return id_, dirpath
