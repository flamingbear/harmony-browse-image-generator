"""Color Utility module.

This contains a collection of functions related to color tables/maps/palettes
that are used to generate browse images.

"""

import requests
from harmony.message import Source as HarmonySource
from osgeo_utils.auxiliary.color_palette import ColorPalette
from pystac import Item
from rasterio.io import DatasetReader

from harmony_browse_image_generator.exceptions import (
    HyBIGError,
    HyBIGNoColorInformation,
)


def palette_from_remote_colortable(url: str) -> ColorPalette:
    """Return a gdal ColorPalette from a remote colortable."""
    response = requests.get(url, timeout=10)
    if not response.ok:
        raise HyBIGError(f'Failed to retrieve color table at {url}')

    palette = ColorPalette()
    palette.read_file_txt(lines=response.text.split('\n'))
    return palette


def get_color_palette_from_item(item: Item) -> ColorPalette | None:
    """Return a color palete

    If the input Item has an associated color information, fetch the data from
    the location and read into a ColorPalette

    """
    palette_asset = next(
        (
            item_asset
            for item_asset in item.assets.values()
            if 'palette' in (item_asset.roles or [])
        ),
        None,
    )
    if palette_asset is not None:
        return palette_from_remote_colortable(palette_asset.href)
    return None


def get_color_palette(
    dataset: DatasetReader,
    source: HarmonySource = None,
    item_color_palette: ColorPalette | None = None,
) -> ColorPalette | None:
    """Get a color palette for the single band image

    Order of operations for getting a color palette:

    1. Color Infomration was found in the stac Item's `palette` asset.
    2. Color information is provided in the HarmonySource.
    3. input GeoTIFF has a colormap
    4. Return None and the image will default to greyscale.

    """
    if item_color_palette is not None:
        return item_color_palette

    try:
        return get_remote_palette_from_source(source)
    except HyBIGNoColorInformation:
        try:
            return convert_colormap_to_palette(dataset.colormap(1))
        except ValueError:
            return None


def get_remote_palette_from_source(source: HarmonySource) -> dict:
    """Get a colormap from a remote url

    Checks the HarmonySource object for a URL to download a color map for the
    input raster.

    """
    try:
        if len(source.variables) != 1:
            raise TypeError('Palette must come from a single variable')
        variable = source.variables[0]
        remoteColortableUrl = next(
            r_url.url
            for r_url in variable.relatedUrls
            if (
                r_url.urlContentType == 'VisualizationURL' and r_url.type == 'Color Map'
            )
        )
        return palette_from_remote_colortable(remoteColortableUrl)

    except HyBIGError as hybig_exc:
        raise HyBIGError(
            f'Failed to retrieve color table at {remoteColortableUrl}'
        ) from hybig_exc
    except Exception as exc:
        raise HyBIGNoColorInformation('No color in source') from exc


def convert_colormap_to_palette(colormap: dict) -> ColorPalette:
    """Convert a GeoTIFF palette to GDAL ColorPalette.

    Reformats a palette as dictionary and loads it into a ColorPalette.

    a GeoTIFF's colormap looks like a dictionary of tiff's value to (r,g,b,[a])
    {0: (9, 60, 112, 255),
     1: (9, 65, 122, 255),
     2: (9, 80, 132, 255),
     3: (9, 100, 142, 255),...}

    """
    list_of_key_rgba = [list((key, *rgba)) for key, rgba in colormap.items()]
    strings_of_key_r_g_b_a = [
        ' '.join([str(item) for item in line]) for line in list_of_key_rgba
    ]
    palette = ColorPalette()
    palette.read_file_txt(lines=strings_of_key_r_g_b_a)
    return palette
