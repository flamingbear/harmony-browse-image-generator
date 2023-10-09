"""Tests covering the size module."""

from unittest import TestCase
from unittest.mock import MagicMock, patch

import rasterio
from harmony.message import Message
from rasterio import Affine
from rasterio.crs import CRS

from harmony_browse_image_generator.crs import PREFERRED_CRS
from harmony_browse_image_generator.exceptions import HyBIGValueError
from harmony_browse_image_generator.sizes import (
    METERS_PER_DEGREE,
    best_guess_scale_extent,
    best_guess_target_dimensions,
    choose_scale_extent,
    choose_target_dimensions,
    compute_cells_per_tile,
    compute_tile_boundaries,
    compute_tile_dimensions,
    create_tiled_output_parameters,
    epsg_3031_resolutions,
    epsg_3413_resolutions,
    epsg_4326_resolutions,
    find_closest_resolution,
    get_rasterio_parameters,
    get_target_grid_parameters,
    icd_defined_extent_from_crs,
    needs_tiling,
    resolution_in_target_crs_units,
)
from tests.unit.utility import rasterio_test_file

nsidc_ease2_36km_grid = {
    'epsg': 6933,
    'width': 964,
    'height': 406,
    'left': -17367530.44,
    'bottom': -7314540.49,
    'right': 17367529.639999997,
    'top': 7314540.83,
    'xres': 36032.22,
    'yres': 36032.22,
}

nsidc_np_seaice_grid = {
    'epsg': 3413,
    'width': 304,
    'height': 448,
    'left': -3850000.0,
    'bottom': -5350000.0,
    'right': 3750000.0,
    'top': 5850000.0,
    'xres': 25000.0,
    'yres': 25000.0,
}

sp_seaice_grid = {
    'epsg': 3031,
    'width': 316,
    'height': 332,
    'left': -3950000.0,
    'bottom': -3950000.0,
    'right': 3950000.0,
    'top': 4350000.0,
    'xres': 25000.0,
    'yres': 25000.0,
}


class TestGetTargetGridParameters(TestCase):
    """Params from Message and input metadata."""

    def test_grid_parameters_from_harmony_message_has_complete_information(self):
        height = nsidc_np_seaice_grid['height']
        width = nsidc_np_seaice_grid['width']
        crs = CRS.from_epsg(nsidc_np_seaice_grid['epsg'])
        scale_extents = {
            'xmin': nsidc_np_seaice_grid['left'],
            'ymin': nsidc_np_seaice_grid['bottom'],
            'xmax': nsidc_np_seaice_grid['right'],
            'ymax': nsidc_np_seaice_grid['top'],
        }

        message = Message(
            {
                'format': {
                    'height': height,
                    'width': width,
                    'srs': {'wkt': crs.to_wkt(version='WKT2')},
                    'scaleExtent': {
                        'x': {
                            'min': scale_extents['xmin'],
                            'max': scale_extents['xmax'],
                        },
                        'y': {
                            'min': scale_extents['ymin'],
                            'max': scale_extents['ymax'],
                        },
                    },
                }
            }
        )
        expected_transform = Affine.translation(
            nsidc_np_seaice_grid['left'], nsidc_np_seaice_grid['top']
        ) * Affine.scale(
            nsidc_np_seaice_grid['xres'], -1 * nsidc_np_seaice_grid['yres']
        )

        expected_parameters = {
            'width': width,
            'height': height,
            'crs': crs,
            'transform': expected_transform,
        }

        actual_parameters = get_target_grid_parameters(message, None)
        self.assertDictEqual(expected_parameters, actual_parameters)

    def test_grid_parameters_from_harmony_no_message_information(self):
        """input granule is in preferred_crs on a 25km grid

        But has grid extents different from the ICD defaults.

        """

        preferred_scale_extent = {
            'xmin': -4194304.0,
            'ymin': -4194304.0,
            'xmax': 4194304.0,
            'ymax': 4194304.0,
        }
        expected_height = round(
            (preferred_scale_extent['ymax'] - preferred_scale_extent['ymin'])
            / sp_seaice_grid['yres']
        )  # 336
        expected_width = round(
            (preferred_scale_extent['xmax'] - preferred_scale_extent['xmin'])
            / sp_seaice_grid['xres']
        )  # 336

        expected_y_resolution = (
            preferred_scale_extent['ymax'] - preferred_scale_extent['ymin']
        ) / expected_height
        expected_x_resolution = (
            preferred_scale_extent['xmax'] - preferred_scale_extent['xmin']
        ) / expected_width

        expected_transform = Affine.translation(
            preferred_scale_extent['xmin'], preferred_scale_extent['ymax']
        ) * Affine.scale(expected_x_resolution, -1 * expected_y_resolution)

        crs = CRS.from_epsg(sp_seaice_grid['epsg'])
        expected_parameters = {
            'height': expected_height,
            'width': expected_width,
            'crs': crs,
            'transform': expected_transform,
        }

        height = sp_seaice_grid['height']
        width = sp_seaice_grid['width']
        with rasterio_test_file(
            height=height,
            width=width,
            crs=crs,
            transform=Affine.translation(sp_seaice_grid['left'], sp_seaice_grid['top'])
            * Affine.scale(sp_seaice_grid['xres'], -1 * sp_seaice_grid['yres']),
        ) as tmp_file:
            message = Message({'format': {}})
            with rasterio.open(tmp_file) as dataset_in:
                actual_parameters = get_target_grid_parameters(message, dataset_in)
                self.assertDictEqual(expected_parameters, actual_parameters)


class TestRasterioParameters(TestCase):
    """Returns grid Params in rasterio format."""

    def test_parameters(self):
        width = nsidc_np_seaice_grid['width']
        height = nsidc_np_seaice_grid['height']
        west = nsidc_np_seaice_grid['left']
        north = nsidc_np_seaice_grid['top']
        east = nsidc_np_seaice_grid['right']
        south = nsidc_np_seaice_grid['bottom']
        xres = nsidc_np_seaice_grid['xres']
        yres = nsidc_np_seaice_grid['yres']

        crs = CRS.from_epsg(nsidc_np_seaice_grid['epsg'])
        dimensions = {'width': width, 'height': height}
        scale_extent = {'xmin': west, 'ymax': north, 'xmax': east, 'ymin': south}

        expected_parameters = {
            'width': width,
            'height': height,
            'crs': crs,
            'transform': Affine(xres, 0.0, west, 0.0, -1 * yres, north),
        }

        actual_parameters = get_rasterio_parameters(crs, scale_extent, dimensions)
        self.assertDictEqual(expected_parameters, actual_parameters)


class TestTiling(TestCase):
    """Tests for Tiling images."""


    def test_needs_tiling(self):
        """ Does the grid need to be tiled. The grid parameters checked in each
            test only the x resolution from the Affine matrix and whether the
            CRS is projected or geographic.

        """
        with self.subTest('Projected, needs tiling'):
            grid_parameters = {
                'height': 400,
                'width': 400,
                'crs': CRS.from_epsg(nsidc_np_seaice_grid['epsg']),
                'transform': Affine(400, 0.0, -3850000.0, 0.0, 400, 5850000.0)
            }
            self.assertTrue(needs_tiling(grid_parameters))

        with self.subTest('Projected, does not need tiling'):
            grid_parameters = {
                'height': 400,
                'width': 400,
                'crs': CRS.from_epsg(nsidc_np_seaice_grid['epsg']),
                'transform': Affine(600, 0.0, -3850000.0, 0.0, 600, 5850000.0)
            }
            self.assertFalse(needs_tiling(grid_parameters))

        with self.subTest('Geographic, needs tiling'):
            grid_parameters = {
                'height': 180000,
                'width': 360000,
                'crs': CRS.from_epsg(4326),
                'transform': Affine(0.001, 0.0, -180, 0.0, -0.001, 180)
            }
            self.assertTrue(needs_tiling(grid_parameters))

        with self.subTest('Geographic, does not need tiling'):
            grid_parameters = {
                'height': 1800,
                'width': 3600,
                'crs': CRS.from_epsg(4326),
                'transform': Affine(0.1, 0.0, -180, 0.0, -0.1, 180)
            }
            self.assertFalse(needs_tiling(grid_parameters))

    def test_compute_cells_per_tile(self):
        """test how tiles sizes are generated."""
        projected_crs = CRS.from_string(PREFERRED_CRS['north'])
        unprojected_crs = CRS.from_string(PREFERRED_CRS['global'])

        with self.subTest('projected CRS - meters'):
            resolution = 500.0
            expected_cells_per_tile = 2000
            actual_cells_per_tile = compute_cells_per_tile(resolution, projected_crs)
            self.assertEqual(expected_cells_per_tile, actual_cells_per_tile)
            self.assertIsInstance(actual_cells_per_tile, int)


        with self.subTest('unprojected CRS - degrees'):
            resolution = 0.009
            expected_cells_per_tile = 1111
            actual_cells_per_tile = compute_cells_per_tile(resolution, unprojected_crs)
            self.assertEqual(expected_cells_per_tile, actual_cells_per_tile)
            self.assertIsInstance(actual_cells_per_tile, int)


    def test_compute_tile_boundaries_exact(self):
        """tests subdivision of output image."""
        cells_per_tile = 10
        full_width = 10 * 4
        expected_origins = [0.0, 10.0, 20.0, 30.0, 40.0]

        actual_origins = compute_tile_boundaries(cells_per_tile, full_width)

        self.assertEqual(expected_origins, actual_origins)

    def test_compute_tile_boundaries_with_leftovers(self):
        """tests subdivision of output image."""
        cells_per_tile = 10
        full_width = 10 * 4 + 3
        expected_origins = [0.0, 10.0, 20.0, 30.0, 40.0, 43.0]

        actual_origins = compute_tile_boundaries(cells_per_tile, full_width)

        self.assertEqual(expected_origins, actual_origins)

    def test_compute_tile_dimensions_uniform(self):
        """test tile dimensions."""
        tile_origins = [0.0, 10.0, 20.0, 30.0, 40.0, 43.0]
        expected_dimensions = [10.0, 10.0, 10.0, 10.0, 3.0, 0.0]

        actual_dimensions = compute_tile_dimensions(tile_origins)

        self.assertEqual(expected_dimensions, actual_dimensions)

    def test_compute_tile_dimensions_nonuniform(self):
        """test tile dimensions."""
        tile_origins = [0.0, 20.0, 35.0, 40.0, 43.0]
        expected_dimensions = [20.0, 15.0, 5.0, 3.0, 0.0]

        actual_dimensions = compute_tile_dimensions(tile_origins)

        self.assertEqual(expected_dimensions, actual_dimensions)

    @patch('harmony_browse_image_generator.sizes.compute_cells_per_tile')
    @patch('harmony_browse_image_generator.sizes.needs_tiling')
    def test_create_tile_output_parameters(
        self, needs_tiling_mock, cells_per_tile_mock
    ):
        """Test splitting of gridParams into sub-tiles.

        Use a standard .05 degree unprojected grid 7200x3600

        For expectation convenience, override the cells_per_tile.  by using
        2800 cells per tile, we will generate a 3x2 output grid
        The Affine definition:
                Affine(xres, 0.0, <Long>, 0.0, -yres, <Latitude>),

        width:
        -180                   -40                        100                 180
        +-----------------------+--------------------------+-------------------+
        0                       2800                     5600                7200

        height:
        90                             -50               -90
        +------------------------------+-------------------+
        0                             2800               3600


        Check the locations. Each cell is .05deg
        2800 cells * .05 deg = 140.deg
        -180.0 + 140 = -40
        -40 + 140 = 100
        etc.

        """
        needs_tiling_mock.return_value = True
        cells_per_tile_mock.return_value = 2800

        grid_parameters = {
            'width': 7200,
            'height': 3600,
            'crs': CRS.from_string(PREFERRED_CRS['global']),
            'transform': Affine(0.05, 0.0, -180.0, 0.0, -0.05, 90.0),
        }

        expected_grid_list = [
            {
                'width': 2800,
                'height': 2800,
                'crs': CRS.from_epsg(4326),
                'transform': Affine(0.05, 0.0, -180.0, 0.0, -0.05, 90.0),
            },
            {
                'width': 2800,
                'height': 2800,
                'crs': CRS.from_epsg(4326),
                'transform': Affine(0.05, 0.0, -40.0, 0.0, -0.05, 90.0),
            },
            {
                'width': 1600,
                'height': 2800,
                'crs': CRS.from_epsg(4326),
                'transform': Affine(0.05, 0.0, 100.0, 0.0, -0.05, 90.0),
            },
            {
                'width': 2800,
                'height': 800,
                'crs': CRS.from_epsg(4326),
                'transform': Affine(0.05, 0.0, -180.0, 0.0, -0.05, -50.0),
            },
            {
                'width': 2800,
                'height': 800,
                'crs': CRS.from_epsg(4326),
                'transform': Affine(0.05, 0.0, -40.0, 0.0, -0.05, -50.0),
            },
            {
                'width': 1600,
                'height': 800,
                'crs': CRS.from_epsg(4326),
                'transform': Affine(0.05, 0.0, 100.0, 0.0, -0.05, -50.0),
            },
        ]
        expected_tile_locator = [
            {'col': 0, 'row': 0},
            {'col': 1, 'row': 0},
            {'col': 2, 'row': 0},
            {'col': 0, 'row': 1},
            {'col': 1, 'row': 1},
            {'col': 2, 'row': 1},
        ]

        actual_grid_list, actual_tile_locator = create_tiled_output_parameters(
            grid_parameters
        )

        self.assertListEqual(expected_grid_list, actual_grid_list)
        self.assertListEqual(expected_tile_locator, actual_tile_locator)


class TestChooseScaleExtent(TestCase):
    """Test for correct scale extents."""

    def test_scale_extent_in_harmony_message(self):
        """Basic case of user supplied scaleExtent."""
        message = Message(
            {
                'format': {
                    'scaleExtent': {
                        'x': {'min': 0.0, 'max': 1000.0},
                        'y': {'min': 0.0, 'max': 500.0},
                    }
                }
            }
        )
        expected_scale_extent = {
            'xmin': 0.0,
            'ymin': 0.0,
            'xmax': 1000.0,
            'ymax': 500.0,
        }
        crs = None
        actual_scale_extent = choose_scale_extent(message, crs)
        self.assertDictEqual(expected_scale_extent, actual_scale_extent)

    @patch('harmony_browse_image_generator.sizes.best_guess_scale_extent')
    @patch('harmony_browse_image_generator.sizes.icd_defined_extent_from_crs')
    def test_preferred_crs(self, mock_icd_extents, mock_best_guess):
        """Preferred CRS will default to ICD expected."""
        target_crs = CRS.from_string(PREFERRED_CRS['north'])
        message = Message({})
        choose_scale_extent(message, target_crs)

        mock_icd_extents.assert_called_once_with(target_crs)
        mock_best_guess.assert_not_called()

    @patch('harmony_browse_image_generator.sizes.best_guess_scale_extent')
    @patch('harmony_browse_image_generator.sizes.icd_defined_extent_from_crs')
    def test_guess_extents_from_crs(self, mock_icd_extents, mock_best_guess):
        """un-preferred CRS will try to guess scale extents."""
        target_crs = CRS.from_string('EPSG:6931')
        message = Message({})
        choose_scale_extent(message, target_crs)

        mock_icd_extents.assert_not_called()
        mock_best_guess.assert_called_once_with(target_crs)


class TestChooseTargetDimensions(TestCase):
    def test_message_has_dimensions(self):
        message = Message({'format': {'height': 30, 'width': 40}})
        expected_dimensions = {'height': 30, 'width': 40}
        actual_dimensions = choose_target_dimensions(message, None, None, None)
        self.assertDictEqual(expected_dimensions, actual_dimensions)

    def test_message_has_scale_sizes(self):
        message = Message({'format': {'scaleSize': {'x': 10, 'y': 10}}})
        # scaleExtents are already extracted.
        scale_extent = {'xmin': 0.0, 'xmax': 2000.0, 'ymin': 0.0, 'ymax': 1000.0}

        expected_dimensions = {'height': 100, 'width': 200}
        actual_dimensions = choose_target_dimensions(message, None, scale_extent, None)
        self.assertDictEqual(expected_dimensions, actual_dimensions)

    @patch('harmony_browse_image_generator.sizes.best_guess_target_dimensions')
    def test_message_has_no_information(self, mock_best_guess_target_dimensions):
        """Test message with no information gets sent to best guess."""
        message = Message({})
        scale_extent = MagicMock()
        dataset = MagicMock()
        target_crs = MagicMock()

        choose_target_dimensions(message, dataset, scale_extent, target_crs)

        mock_best_guess_target_dimensions.assert_called_once_with(
            dataset, scale_extent, target_crs
        )

    @patch('harmony_browse_image_generator.sizes.best_guess_target_dimensions')
    def test_message_has_just_one_dimension(self, mock_best_guess_target_dimensions):
        """Message with only one dimension.

        This message is ignored and the request is sent to the guess best
        dimension routine

        """
        message = Message({'format': {'height': 30}})
        scale_extent = MagicMock()
        dataset = MagicMock()
        target_crs = MagicMock()

        choose_target_dimensions(message, dataset, scale_extent, target_crs)

        mock_best_guess_target_dimensions.assert_called_once_with(
            dataset, scale_extent, target_crs
        )


class TestICDDefinedExtentFromCrs(TestCase):
    """Ensure standard CRS yield standard scaleExtents.

    The expected scale extents are pulled from the ICD document.

    """

    def test_global_preferred_crs(self):
        crs = CRS.from_string(PREFERRED_CRS['global'])
        expected_scale_extent = {
            'xmin': -180.0,
            'ymin': -90.0,
            'xmax': 180.0,
            'ymax': 90.0,
        }
        actual_scale_extent = icd_defined_extent_from_crs(crs)
        self.assertDictEqual(expected_scale_extent, actual_scale_extent)

    def test_south_preferred_crs(self):
        crs = CRS.from_string(PREFERRED_CRS['south'])
        expected_scale_extent = {
            'xmin': -4194304.0,
            'ymin': -4194304.0,
            'xmax': 4194304.0,
            'ymax': 4194304.0,
        }
        actual_scale_extent = icd_defined_extent_from_crs(crs)
        self.assertDictEqual(expected_scale_extent, actual_scale_extent)

    def test_north_preferred_crs(self):
        crs = CRS.from_string(PREFERRED_CRS['north'])
        expected_scale_extent = {
            'xmin': -4194304.0,
            'ymin': -4194304.0,
            'xmax': 4194304.0,
            'ymax': 4194304.0,
        }
        actual_scale_extent = icd_defined_extent_from_crs(crs)
        self.assertDictEqual(expected_scale_extent, actual_scale_extent)

    def test_non_preferred(self):
        crs = CRS.from_string('EPSG:4311')
        with self.assertRaises(HyBIGValueError) as excepted:
            icd_defined_extent_from_crs(crs)

        self.assertEqual(excepted.exception.message, 'Invalid input CRS: EPSG:4311')
        pass


class TestBestGuessScaleExtent(TestCase):
    def test_unprojected_crs_has_area_of_use(self):
        crs = CRS.from_epsg(4326)
        expected_extent = {'xmin': -180.0, 'ymin': -90.0, 'xmax': 180.0, 'ymax': 90.0}
        actual_extent = best_guess_scale_extent(crs)
        self.assertDictEqual(expected_extent, actual_extent)

    def test_projected_crs_has_area_of_use(self):
        """North Pole LAEA Canada"""
        crs = CRS.from_epsg(3573)
        expected_extent = {
            'xmin': -4859208.992805643,
            'ymin': -4886873.230107171,
            'xmax': 4859208.992805643,
            'ymax': 4886873.230107171,
        }

        actual_extent = best_guess_scale_extent(crs)
        self.assertDictEqual(expected_extent, actual_extent)

    def test_unprojected_crs_has_no_area_of_use(self):
        """Use EPSG 4269 created with a dictionary."""
        crs = CRS.from_dict(
            {'proj': 'longlat', 'datum': 'NAD83', 'no_defs': None, 'type': 'crs'}
        )

        expected_extent = {'xmin': -180.0, 'ymin': -90.0, 'xmax': 180.0, 'ymax': 90.0}

        actual_extent = best_guess_scale_extent(crs)

        self.assertDictEqual(expected_extent, actual_extent)

    def test_unprojected_nonstandard_crs_has_no_area_of_use(self):
        """Use EPSG 4269."""
        crs = CRS.from_epsg(4269)

        #  west=167.65, south=14.92, east=-40.73, north=86.45
        expected_extent = {'xmin': 167.65, 'ymin': 14.92, 'xmax': -40.73, 'ymax': 86.45}
        actual_extent = best_guess_scale_extent(crs)
        self.assertDictEqual(expected_extent, actual_extent)


class TestBestGuessTargetDimensions(TestCase):
    def test_projected_crs(self):
        """A coarse resolution image uses the input granules' height and width
        when guessing the output dimensions.

        """
        # EASE-2 25km North
        with rasterio_test_file(
            height=720,
            width=720,
            crs=CRS.from_epsg(6931),
            transform=Affine(25000.0, 0.0, -9000000.0, 0.0, -25000.0, 9000000.0),
            dtype='uint8',
        ) as tmp_file:
            with rasterio.open(tmp_file) as in_dataset:
                scale_extent = {
                    'xmin': -9000000.0,
                    'ymin': -9000000.0,
                    'xmax': 9000000.0,
                    'ymax': 9000000.0,
                }

                # in_dataset's height and width
                expected_target_dimensions = {'height': 720, 'width': 720}
                crs = MagicMock()
                crs.is_projected = True

                actual_dimensions = best_guess_target_dimensions(
                    in_dataset, scale_extent, crs
                )

                self.assertDictEqual(expected_target_dimensions, actual_dimensions)

    def test_projected_crs_with_high_resolution(self):
        """A high resolution grid will choose a target dimension to match
        mostly closely the GIBS preferred dimension.

        Theoretical EASE-2 700m resolution grid, covering 9M meters in each direction.
        700.01m = (9000000.0 - -9000000.0) / 25714

        """
        with rasterio_test_file(
            height=25714,
            width=25714,
            crs=CRS.from_epsg(6931),
            transform=Affine(
                699.980556095664, 0.0, -9000000.0, 0.0, 699.980556095664, 9000000.0
            ),
            dtype='uint8',
        ) as tmp_file:
            with rasterio.open(tmp_file) as in_dataset:
                scale_extent = {
                    'xmin': -9000000.0,
                    'ymin': -9000000.0,
                    'xmax': 9000000.0,
                    'ymax': 9000000.0,
                }

                # expected resolution is "500m" and the pixel_size is 512m
                # (9000000 - -9000000 ) / 512 = 35156
                expected_target_dimensions = {'height': 35156, 'width': 35156}
                target_crs = MagicMock(is_projected=True)
                expected_x_resolution = 512
                expected_y_resolution = 512

                actual_dimensions = best_guess_target_dimensions(
                    in_dataset, scale_extent, target_crs
                )

                self.assertDictEqual(expected_target_dimensions, actual_dimensions)

                # Assert the resolutions are found in the preferred resolutions.
                self.assertEqual(
                    expected_x_resolution,
                    epsg_3413_resolutions[2].pixel_size,
                    msg='Expected Resolution is incorrect',
                )
                self.assertEqual(
                    expected_y_resolution,
                    epsg_3413_resolutions[2].pixel_size,
                    msg='Expected Resolution is incorrect',
                )

    def test_projected_crs_with_high_resolution_to_preferred_area(self):
        """Repeat previous test with a preferred scale_extent.

        Just show that when the scale extent is preferred we also end up with a
        preferred resolution width from the ICD document.

        Theoretical EASE-2 700m resolution grid
        700.04 m = (4194304.0 - -4194304.0) / 11983

        """
        with rasterio_test_file(
            height=11983,
            width=11983,
            crs=CRS.from_epsg(6931),
            transform=Affine(700.0423, 0.0, -4194304.0, 0.0, 700.0423, 4194304.0),
            dtype='uint8',
        ) as tmp_file:
            with rasterio.open(tmp_file) as in_dataset:
                scale_extent = {
                    'xmin': -4194304.0,
                    'ymin': -4194304.0,
                    'xmax': 4194304.0,
                    'ymax': 4194304.0,
                }

                expected_target_dimensions = {
                    'height': epsg_3413_resolutions[2].width,
                    'width': epsg_3413_resolutions[2].width,
                }
                crs = MagicMock(is_projected=True)

                expected_x_resolution = (
                    scale_extent['xmax'] - scale_extent['xmin']
                ) / expected_target_dimensions['width']
                expected_y_resolution = (
                    scale_extent['ymax'] - scale_extent['ymin']
                ) / expected_target_dimensions['height']

                actual_dimensions = best_guess_target_dimensions(
                    in_dataset, scale_extent, crs
                )

                self.assertDictEqual(expected_target_dimensions, actual_dimensions)

                # Assert the resolutions are found in the preferred resolutions
                self.assertAlmostEqual(
                    expected_x_resolution,
                    epsg_3413_resolutions[2].pixel_size,
                    msg='Expected Resolution is incorrect',
                    delta=1e-6,
                )
                self.assertAlmostEqual(
                    expected_y_resolution,
                    epsg_3413_resolutions[2].pixel_size,
                    msg='Expected Resolution is incorrect',
                    delta=1e-6,
                )

    def test_longlat_crs(self):
        # 36km Mid-Latitude EASE Grid 2
        ml_test_transform = rasterio.transform.from_bounds(
            nsidc_ease2_36km_grid['left'],
            nsidc_ease2_36km_grid['bottom'],
            nsidc_ease2_36km_grid['right'],
            nsidc_ease2_36km_grid['top'],
            nsidc_ease2_36km_grid['width'],
            nsidc_ease2_36km_grid['height'],
        )

        with rasterio_test_file(
            height=406,
            width=964,
            crs=CRS.from_epsg(nsidc_ease2_36km_grid['epsg']),
            transform=ml_test_transform,
            dtype='uint8',
        ) as tmp_file:
            with rasterio.open(tmp_file) as in_dataset:
                scale_extent = {
                    'xmin': -180.0,
                    'ymin': -86.0,
                    'xmax': 180.0,
                    'ymax': 86.0,
                }

                infile_res = 0.31668943359375
                expected_height = round((86 - -86) / infile_res)
                expected_width = round((180 - -180) / infile_res)
                expected_target_dimensions = {
                    'height': expected_height,
                    'width': expected_width,
                }
                target_crs = MagicMock()
                target_crs.is_projected = False

                actual_dimensions = best_guess_target_dimensions(
                    in_dataset, scale_extent, target_crs
                )

                self.assertDictEqual(expected_target_dimensions, actual_dimensions)

    def test_longlat_crs_with_high_resolution(self):
        # 360m Mid-Latitude EASE Grid 2
        # 360m -> 250m preferred
        test_transform = rasterio.transform.from_bounds(
            nsidc_ease2_36km_grid['left'],
            nsidc_ease2_36km_grid['bottom'],
            nsidc_ease2_36km_grid['right'],
            nsidc_ease2_36km_grid['top'],
            nsidc_ease2_36km_grid['width'] * 100,
            nsidc_ease2_36km_grid['height'] * 100,
        )
        with rasterio_test_file(
            height=nsidc_ease2_36km_grid['height'] * 100,
            width=nsidc_ease2_36km_grid['width'] * 100,
            transform=test_transform,
            crs=CRS.from_epsg(6933),
            dtype='uint8',
        ) as tmp_file:
            with rasterio.open(tmp_file) as in_dataset:
                scale_extent = {
                    'xmin': -180.0,
                    'ymin': -86.0,
                    'xmax': 180.0,
                    'ymax': 86.0,
                }

                # resolution is 360 meters, which resolves to 250m preferred.
                target_resolution = epsg_4326_resolutions[3].pixel_size
                expected_height = round((86 - -86) / target_resolution)
                expected_width = round((180 - -180) / target_resolution)
                expected_target_dimensions = {
                    'height': expected_height,
                    'width': expected_width,
                }
                target_crs = MagicMock()
                target_crs.is_projected = False
                expected_x_resolution = (
                    round(scale_extent['xmax'] - scale_extent['xmin'])
                    / expected_target_dimensions['width']
                )
                expected_y_resolution = (
                    round(scale_extent['ymax'] - scale_extent['ymin'])
                    / expected_target_dimensions['height']
                )

                actual_dimensions = best_guess_target_dimensions(
                    in_dataset, scale_extent, target_crs
                )
                self.assertDictEqual(expected_target_dimensions, actual_dimensions)

                # Assert the resolutions are found in the preferred resolutions
                self.assertAlmostEqual(
                    expected_x_resolution,
                    epsg_4326_resolutions[3].pixel_size,
                    msg='Expected Resolution is incorrect',
                    delta=1e-6,
                )
                self.assertAlmostEqual(
                    expected_y_resolution,
                    epsg_4326_resolutions[3].pixel_size,
                    msg='Expected Resolution is incorrect',
                    delta=1e-6,
                )


class TestResolutionInTargetCRS(TestCase):
    """Ensure resolution ends up in target_crs units"""

    def test_dataset_matches_target_crs_meters(self):
        ml_test_transform = rasterio.transform.from_bounds(
            nsidc_ease2_36km_grid['left'],
            nsidc_ease2_36km_grid['bottom'],
            nsidc_ease2_36km_grid['right'],
            nsidc_ease2_36km_grid['top'],
            nsidc_ease2_36km_grid['width'],
            nsidc_ease2_36km_grid['height'],
        )
        with rasterio_test_file(
            crs=CRS.from_epsg(nsidc_ease2_36km_grid['epsg']),
            transform=ml_test_transform,
        ) as test_file:
            with rasterio.open(test_file) as test_dataset:
                target_crs = CRS.from_epsg(3413)
                expected_x_res = ml_test_transform.a
                expected_y_res = -ml_test_transform.e

                actual_x_res, actual_y_res = resolution_in_target_crs_units(
                    test_dataset, target_crs
                )

                self.assertEqual(expected_x_res, actual_x_res)
                self.assertEqual(expected_y_res, actual_y_res)

    def test_dataset_matches_target_crs_degrees(self):
        """Input dataset and target unprojected."""
        global_one_degree_transform = rasterio.transform.from_bounds(
            -180, -90, 180, 90, 360, 180
        )
        with rasterio_test_file(
            crs=CRS.from_string(PREFERRED_CRS['global']),
            transform=global_one_degree_transform,
        ) as test_file:
            with rasterio.open(test_file) as test_dataset:
                target_crs = CRS.from_string(PREFERRED_CRS['global'])
                expected_x_res = global_one_degree_transform.a
                expected_y_res = -global_one_degree_transform.e

                actual_x_res, actual_y_res = resolution_in_target_crs_units(
                    test_dataset, target_crs
                )

                self.assertEqual(expected_x_res, actual_x_res)
                self.assertEqual(expected_y_res, actual_y_res)

    def test_dataset_meters_target_crs_degrees(self):
        ml_test_transform = rasterio.transform.from_bounds(
            nsidc_ease2_36km_grid['left'],
            nsidc_ease2_36km_grid['bottom'],
            nsidc_ease2_36km_grid['right'],
            nsidc_ease2_36km_grid['top'],
            nsidc_ease2_36km_grid['width'],
            nsidc_ease2_36km_grid['height'],
        )
        with rasterio_test_file(
            crs=CRS.from_epsg(nsidc_ease2_36km_grid['epsg']),
            transform=ml_test_transform,
        ) as test_file:
            with rasterio.open(test_file) as test_dataset:
                target_crs = CRS.from_epsg(4326)
                expected_x_res = ml_test_transform.a / METERS_PER_DEGREE
                expected_y_res = -ml_test_transform.e / METERS_PER_DEGREE

                actual_x_res, actual_y_res = resolution_in_target_crs_units(
                    test_dataset, target_crs
                )

                self.assertEqual(expected_x_res, actual_x_res)
                self.assertEqual(expected_y_res, actual_y_res)

    def test_dataset_degrees_target_crs_meters(self):
        global_one_degree_transform = rasterio.transform.from_bounds(
            -180, -90, 180, 90, 360, 180
        )
        with rasterio_test_file(
            crs=CRS.from_string(PREFERRED_CRS['global']),
            transform=global_one_degree_transform,
        ) as test_file:
            with rasterio.open(test_file) as test_dataset:
                target_crs = CRS.from_string(PREFERRED_CRS['north'])
                expected_x_res = global_one_degree_transform.a * METERS_PER_DEGREE
                expected_y_res = -global_one_degree_transform.e * METERS_PER_DEGREE

                actual_x_res, actual_y_res = resolution_in_target_crs_units(
                    test_dataset, target_crs
                )

                self.assertEqual(expected_x_res, actual_x_res)
                self.assertEqual(expected_y_res, actual_y_res)


class TestFindClosestResolution(TestCase):
    """Ensure we abide by GIBS preferred resolutions."""

    @classmethod
    def setUpClass(cls):
        cls.global_info = epsg_4326_resolutions
        cls.north_info = epsg_3413_resolutions
        cls.south_info = epsg_3031_resolutions

    def test_coarser_than_2km_degrees(self):
        """Normal usage prevents this function from being called with a
        resolution larger than the coarsest value in the resolution table, but
        if it is, it will still return the closest resolution.

        """
        # tenth of a degree resolution
        resolution = [360.0 / 3600]
        expected_resolution = self.global_info[0].pixel_size
        actual_resolution = find_closest_resolution(resolution, self.global_info)
        self.assertEqual(expected_resolution, actual_resolution.pixel_size)

    def test_matches_preferred_degrees(self):
        # 500m resolution.
        resolution = [360.0 / 81920]
        expected_resolution = self.global_info[2].pixel_size
        actual_resolution = find_closest_resolution(resolution, self.global_info)
        self.assertEqual(expected_resolution, actual_resolution.pixel_size)

    def test_resolution_halfway_between_preferred_degrees(self):
        """Exactly half way should choose larger resolution."""
        # 1.5km resolution
        resolution = [0.01318359375]
        expected_resolution = self.global_info[0].pixel_size
        actual_resolution = find_closest_resolution(resolution, self.global_info)
        self.assertEqual(expected_resolution, actual_resolution.pixel_size)

    def test_chooses_closest_resolution_degrees(self):
        width = self.global_info[4].width
        resolutions = [360.0 / (width + 1), 360.0 / (width + 100)]
        expected_resolution = self.global_info[4].pixel_size
        actual_resolution = find_closest_resolution(resolutions, self.global_info)
        self.assertEqual(expected_resolution, actual_resolution.pixel_size)

    def test_coarser_than_2km_meters(self):
        """Normal usage prevents this function from being called with a
        resolution larger than the coarsest value in the resolution table, but
        if it is, it will still return the closest resolution which is the
        coarsest.

        """
        # 25km resolution
        resolutions = [25000.0, 25000.0]
        expected_resolution = self.north_info[0].pixel_size
        actual_resolution = find_closest_resolution(resolutions, self.north_info)
        self.assertEqual(expected_resolution, actual_resolution.pixel_size)

    def test_matches_preferred_meters(self):
        # 500m resolution.
        resolution = [128]
        expected_resolution = self.south_info[4].pixel_size
        actual_resolution = find_closest_resolution(resolution, self.south_info)
        self.assertEqual(expected_resolution, actual_resolution.pixel_size)

    def test_resolution_halfway_between_preferred_meters(self):
        """Exactly half way should choose larger resolution."""
        # 48m resolution
        resolution = [48]
        expected_resolution = self.north_info[5].pixel_size
        actual_resolution = find_closest_resolution(resolution, self.north_info)
        self.assertEqual(expected_resolution, actual_resolution.pixel_size)

    def test_chooses_closest_resolution_meters(self):
        resolutions = [65, 540]
        expected_resolution = self.south_info[5].pixel_size
        actual_resolution = find_closest_resolution(resolutions, self.south_info)
        self.assertEqual(expected_resolution, actual_resolution.pixel_size)
