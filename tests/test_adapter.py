""" End-to-end tests of the Harmony Browse Image Generator (HyBIG). """
from os.path import exists, join as path_join
from shutil import rmtree
from tempfile import mkdtemp
from unittest import TestCase
from unittest.mock import call, patch

from harmony.message import Message
from harmony.util import config
from pystac import Catalog

from harmony_browse_image_generator.adapter import BrowseImageGeneratorAdapter

from tests.utilities import create_stac, Granule


class TestAdapter(TestCase):
    """ A class testing the harmony_browse_image_generator.adapter module. """
    @classmethod
    def setUpClass(cls):
        """ Define test fixtures that can be shared between tests. """
        cls.access_token = 'fake-token'
        cls.granule_url = 'https://www.example.com/input.tiff'
        cls.input_stac = create_stac(Granule(cls.granule_url,
                                             'image/tiff',
                                             ['data']))
        cls.staging_location = 's3://example-bucket'
        cls.user = 'blightyear'

    def setUp(self):
        """ Define test fixtures that are not shared between tests. """
        self.temp_dir = mkdtemp()
        self.config = config(validate=False)

    def tearDown(self):
        if exists(self.temp_dir):
            rmtree(self.temp_dir)

    def assert_expected_output_catalog(self, catalog: Catalog,
                                       expected_browse_href: str,
                                       expected_browse_title: str,
                                       expected_browse_media_type: str,
                                       expected_world_href: str,
                                       expected_world_title: str,
                                       expected_world_media_type: str):
        """ Check the contents of the Harmony output STAC. It should have a
            single data item. The URL, title and media type for this asset will
            be compared to supplied values.

        """
        items = list(catalog.get_items())
        self.assertEqual(len(items), 1)
        self.assertListEqual(list(items[0].assets.keys()), ['data', 'metadata'])
        self.assertDictEqual(
            items[0].assets['data'].to_dict(),
            {'href': expected_browse_href,
             'title': expected_browse_title,
             'type': expected_browse_media_type,
             'roles': ['data']}
        )

        self.assertDictEqual(
            items[0].assets['metadata'].to_dict(),
            {'href': expected_world_href,
             'title': expected_world_title,
             'type': expected_world_media_type,
             'roles': ['metadata']}
        )

    @patch('harmony_browse_image_generator.adapter.rmtree')
    @patch('harmony_browse_image_generator.adapter.mkdtemp')
    @patch('harmony_browse_image_generator.adapter.download')
    @patch('harmony_browse_image_generator.adapter.stage')
    def test_valid_request(self, mock_stage, mock_download, mock_mkdtemp,
                           mock_rmtree):
        """ Ensure a request with a correctly formatted message is fully
            processed.

            This test will need updating when the service functions fully.

        """
        expected_downloaded_file = f'{self.temp_dir}/input.tiff'

        # TODO: These 4 lines will change when service is in operation:
        expected_browse_basename = 'input.png'
        expected_browse_full_path = f'{self.temp_dir}/input.png'
        expected_world_basename = 'input.wld'
        expected_world_full_path = f'{self.temp_dir}/input.wld'

        expected_browse_url = path_join(self.staging_location,
                                        expected_browse_basename)
        expected_world_url = path_join(self.staging_location,
                                       expected_world_basename)

        expected_browse_mime = 'image/png'
        expected_world_mime = 'text/plain'

        mock_mkdtemp.return_value = self.temp_dir
        mock_download.return_value = expected_downloaded_file
        mock_stage.side_effect = [expected_browse_url, expected_world_url]

        message = Message({
            'accessToken': self.access_token,
            'callback': 'https://example.com/',
            'sources': [{'collection': 'C1234-EEDTEST', 'shortName': 'test'}],
            'stagingLocation': self.staging_location,
            'user': self.user,
        })

        hybig = BrowseImageGeneratorAdapter(message, config=self.config,
                                            catalog=self.input_stac)

        _, output_catalog = hybig.invoke()

        # Ensure the output catalog contains the single, expected item:
        self.assert_expected_output_catalog(output_catalog,
                                            expected_browse_url,
                                            expected_browse_basename,
                                            expected_browse_mime,
                                            expected_world_url,
                                            expected_world_basename,
                                            expected_world_mime)

        # Ensure a download was requested via harmony-service-lib:
        mock_download.assert_called_once_with(self.granule_url, self.temp_dir,
                                              logger=hybig.logger,
                                              cfg=hybig.config,
                                              access_token=self.access_token)

        # Ensure the browse image and ESRI world file were staged as expected:
        # TODO: "expected_downloaded_files" arguments will need updating when
        # the service processes anything.
        mock_stage.assert_has_calls([
            call(expected_browse_full_path,
                 expected_browse_basename,
                 expected_browse_mime,
                 logger=hybig.logger,
                 location=self.staging_location,
                 cfg=self.config),
            call(expected_world_full_path,
                 expected_world_basename,
                 expected_world_mime,
                 logger=hybig.logger,
                 location=self.staging_location,
                 cfg=self.config)
        ])

        # Ensure container clean-up was requested:
        mock_rmtree.assert_called_once_with(self.temp_dir)
