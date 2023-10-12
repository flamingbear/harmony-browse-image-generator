from unittest import TestCase

from harmony.message import Message

from harmony_browse_image_generator.message_utility import (
    _has_all_attributes,
    _has_consistent_dimension,
    has_crs,
    has_dimensions,
    has_scale_extents,
    has_scale_sizes,
    rgetattr,
)


class TestMessageUtility(TestCase):
    """Test Harmony Message utilities."""

    def test_message_has_crs(self):
        message = Message({"format": {"crs": "EPSG:4326"}})
        self.assertTrue(has_crs(message))

    def test_message_has_garbage_crs(self):
        message = Message({"format": {"crs": "garbage"}})
        self.assertTrue(has_crs(message))

    def test_message_has_no_crs(self):
        message = Message({})
        self.assertFalse(has_crs(message))

    def test_has_consistent_dimension(self):
        """Ensure, given a scale size (resolution), scale extent (range) and
        dimension size, the function can correctly determine if all three
        values are consistent with one another.

        """
        valid_scale_extents = {
            'x': {'min': -180, 'max': 180},
            'y': {'min': -90, 'max': 90},
        }

        valid_scale_sizes = {'x': 0.5, 'y': 1.0}
        valid_height = 180
        valid_width = 720

        with self.subTest('Consistent x dimension returns True'):
            test_message = Message(
                {
                    'format': {
                        'scaleExtent': valid_scale_extents,
                        'scaleSize': valid_scale_sizes,
                        'width': valid_width,
                    }
                }
            )
            self.assertTrue(_has_consistent_dimension(test_message, 'x'))

        with self.subTest('Consistent y dimension returns True'):
            test_message = Message(
                {
                    'format': {
                        'scaleExtent': valid_scale_extents,
                        'scaleSize': valid_scale_sizes,
                        'height': valid_height,
                    }
                }
            )
            self.assertTrue(_has_consistent_dimension(test_message, 'y'))

        with self.subTest('Inconsistent x dimension returns False'):
            test_message = Message(
                {
                    'format': {
                        'scaleExtent': valid_scale_extents,
                        'scaleSize': valid_scale_sizes,
                        'width': valid_width + 100,
                    }
                }
            )
            self.assertFalse(_has_consistent_dimension(test_message, 'x'))

        with self.subTest('Inconsistent y dimension returns False'):
            test_message = Message(
                {
                    'format': {
                        'scaleExtent': valid_scale_extents,
                        'scaleSize': valid_scale_sizes,
                        'height': valid_height + 100,
                    }
                }
            )
            self.assertFalse(_has_consistent_dimension(test_message, 'y'))

    def test_has_all_attributes(self):
        """Ensure that the function returns the correct boolean value
        indicating if all requested attributes are present in the supplied
        object, and have non-None values.

        """
        test_message = Message({'format': {'scaleSize': {'x': 0.5, 'y': 0.5}}})

        with self.subTest('All attributes present returns True'):
            self.assertTrue(
                _has_all_attributes(
                    test_message, ['format.scaleSize.x', 'format.scaleSize.y']
                )
            )

        with self.subTest('Some attributes present returns False'):
            self.assertFalse(
                _has_all_attributes(
                    test_message, ['format.scaleSize.x', 'format.height']
                )
            )

        with self.subTest('No attributes present returns False'):
            self.assertFalse(
                _has_all_attributes(test_message, ['format.height', 'format.width'])
            )

    def test_has_scale_sizes(self):
        """Ensure the function correctly identifies whether the supplied
        Harmony message contains both an x and y scale size.

        """
        with self.subTest('Scale sizes present returns True'):
            test_message = Message({'format': {'scaleSize': {'x': 0.5, 'y': 0.5}}})
            self.assertTrue(has_scale_sizes(test_message))

        with self.subTest('scaleSize.x = None returns False'):
            test_message = Message({'format': {'scaleSize': {'y': 0.5}}})
            self.assertFalse(has_scale_sizes(test_message))

        with self.subTest('scaleSize.y = None returns False'):
            test_message = Message({'format': {'scaleSize': {'x': 0.5}}})
            self.assertFalse(has_scale_sizes(test_message))

        with self.subTest('Both scaleSizes = None returns False'):
            test_message = Message({'format': {'scaleSize': {}}})
            self.assertFalse(has_scale_sizes(test_message))

        with self.subTest('format = None returns False'):
            test_message = Message({})
            self.assertFalse(has_scale_sizes(test_message))

    def test_has_scale_extents(self):
        """Ensure the function correctly identifies whether the supplied
        Harmony message contains all required elements in the
        `format.scaleExtent` attribute. This includes minima and maxima for
        both the x and y horizontal spatial dimensions of the target grid.

        """
        x_extents = {'min': -180, 'max': 180}
        y_extents = {'min': -90, 'max': 90}

        with self.subTest('Scale extents present returns True'):
            test_message = Message(
                {'format': {'scaleExtent': {'x': x_extents, 'y': y_extents}}}
            )
            self.assertTrue(has_scale_extents(test_message))

        with self.subTest('scaleExtent.x.min = None returns False'):
            test_message = Message(
                {'format': {'scaleExtent': {'x': {'max': 180}, 'y': y_extents}}}
            )
            self.assertFalse(has_scale_extents(test_message))

        with self.subTest('scaleExtent.x.max = None returns False'):
            test_message = Message(
                {'format': {'scaleExtent': {'x': {'min': -180}, 'y': y_extents}}}
            )
            self.assertFalse(has_scale_extents(test_message))

        with self.subTest('scaleExtent.x min and max = None returns False'):
            test_message = Message(
                {'format': {'scaleExtent': {'x': {}, 'y': y_extents}}}
            )
            self.assertFalse(has_scale_extents(test_message))

        with self.subTest('scaleExtent.y.min = None returns False'):
            test_message = Message(
                {'format': {'scaleExtent': {'x': x_extents, 'y': {'max': 90}}}}
            )
            self.assertFalse(has_scale_extents(test_message))

        with self.subTest('scaleExtent.y.max = None returns False'):
            test_message = Message(
                {'format': {'scaleExtent': {'x': x_extents, 'y': {'min': -90}}}}
            )
            self.assertFalse(has_scale_extents(test_message))

        with self.subTest('scaleExtent.y min and max = None returns False'):
            test_message = Message(
                {'format': {'scaleExtent': {'x': x_extents, 'y': {}}}}
            )
            self.assertFalse(has_scale_extents(test_message))

        with self.subTest('All scaleExtent values = None returns False'):
            test_message = Message({'format': {'scaleExtent': {'x': {}, 'y': {}}}})
            self.assertFalse(has_scale_extents(test_message))

        with self.subTest('scaleExtent.x and scaleExtent.y = None returns False'):
            test_message = Message({'format': {'scaleExtent': {}}})
            self.assertFalse(has_scale_extents(test_message))

        with self.subTest('format = None returns False'):
            test_message = Message({})
            self.assertFalse(has_scale_extents(test_message))

    def test_has_dimensions(self):
        """Ensure the function correctly validates whether the supplied
        Harmony message contains both a height an width for the target
        grid.

        """
        with self.subTest('height and width present returns True'):
            test_message = Message({'format': {'height': 100, 'width': 50}})
            self.assertTrue(has_dimensions(test_message))

        with self.subTest('height = None returns False'):
            test_message = Message({'format': {'width': 50}})
            self.assertFalse(has_dimensions(test_message))

        with self.subTest('width = None returns False'):
            test_message = Message({'format': {'height': 100}})
            self.assertFalse(has_dimensions(test_message))

        with self.subTest('height = None and width = None returns False'):
            test_message = Message({'format': {}})
            self.assertFalse(has_dimensions(test_message))

        with self.subTest('format = None returns False'):
            test_message = Message({})
            self.assertFalse(has_dimensions(test_message))

    def test_rgetattr(self):
        """Ensure that the recursive function can retrieve nested attributes
        and uses the default argument when required.

        """

        class Child:
            def __init__(self, name):
                self.name = name

        class Parent:
            def __init__(self, name, child_name):
                self.name = name
                self.child = Child(child_name)

        test_parent = Parent('parent_name', 'child_name')

        with self.subTest('Parent level attribute'):
            self.assertEqual(rgetattr(test_parent, 'name'), 'parent_name')

        with self.subTest('Nested attribute'):
            self.assertEqual(rgetattr(test_parent, 'child.name'), 'child_name')

        with self.subTest('Missing parent with default'):
            self.assertEqual(rgetattr(test_parent, 'absent', 'default'), 'default')

        with self.subTest('Missing child attribute with default'):
            self.assertEqual(
                rgetattr(test_parent, 'child.absent', 'default'), 'default'
            )

        with self.subTest('Child requested, parent missing, default'):
            self.assertEqual(
                rgetattr(test_parent, 'none.something', 'default'), 'default'
            )

        with self.subTest('Missing parent, with no default'):
            self.assertIsNone(rgetattr(test_parent, 'absent'))

        with self.subTest('Missing child, with no default'):
            self.assertIsNone(rgetattr(test_parent, 'child.absent'))

        with self.subTest('Child requested, parent missing, no default'):
            self.assertIsNone(rgetattr(test_parent, 'absent.something'))
