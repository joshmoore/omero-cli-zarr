import argparse
import sys
import os

import omero.clients
from omero.rtypes import unwrap
import numpy
import zarr


def image_to_zarr(image, args):

    cache_numpy = args.cache_numpy
    target_dir = args.output

    size_c = image.getSizeC()
    size_z = image.getSizeZ()
    size_x = image.getSizeX()
    size_y = image.getSizeY()
    size_t = image.getSizeT()

    # dir for caching .npy planes
    if cache_numpy:
        os.makedirs(
            os.path.join(target_dir, str(image.id)), mode=511, exist_ok=True
        )
    name = os.path.join(target_dir, "%s.zarr" % image.id)
    za = None
    pixels = image.getPrimaryPixels()

    zct_list = []
    for t in range(size_t):
        for c in range(size_c):
            for z in range(size_z):
                # We only want to load from server if not cached locally
                filename = os.path.join(
                    target_dir,
                    str(image.id),
                    "{:03d}-{:03d}-{:03d}.npy".format(z, c, t),
                )
                if not os.path.exists(filename):
                    zct_list.append((z, c, t))

    def planeGen():
        planes = pixels.getPlanes(zct_list)
        for p in planes:
            yield p

    planes = planeGen()

    for t in range(size_t):
        for c in range(size_c):
            for z in range(size_z):
                filename = os.path.join(
                    target_dir,
                    str(image.id),
                    "{:03d}-{:03d}-{:03d}.npy".format(z, c, t),
                )
                if os.path.exists(filename):
                    print(f"plane (from disk) c:{c}, t:{t}, z:{z}")
                    plane = numpy.load(filename)
                else:
                    print(f"loading plane c:{c}, t:{t}, z:{z}")
                    plane = next(planes)
                    if cache_numpy:
                        print(f"cached at {filename}")
                        numpy.save(filename, plane)
                if za is None:
                    # store = zarr.NestedDirectoryStore(name)
                    # root = zarr.group(store=store, overwrite=True)
                    root = zarr.open_group(name, mode="w")
                    za = root.create(
                        "0",
                        shape=(size_t, size_c, size_z, size_y, size_x),
                        chunks=(1, 1, 1, size_y, size_x),
                        dtype=plane.dtype,
                    )
                za[t, c, z, :, :] = plane
        add_group_metadata(root, image)
    print("Created", name)


def add_group_metadata(zarr_root, image, resolutions=1):

    image_data = {
        "id": 1,
        "channels": [channelMarshal(c) for c in image.getChannels()],
        "rdefs": {
            "model": (
                image.isGreyscaleRenderingModel() and "greyscale" or "color"
            ),
            "defaultZ": image._re.getDefaultZ(),
            "defaultT": image._re.getDefaultT(),
        },
    }
    multiscales = [
        {
            "version": "0.1",
            "datasets": [{"path": str(r)} for r in range(resolutions)],
        }
    ]
    zarr_root.attrs["multiscales"] = multiscales
    zarr_root.attrs["omero"] = image_data


def channelMarshal(channel):
    return {
        "label": channel.getLabel(),
        "color": channel.getColor().getHtml(),
        "inverted": channel.isInverted(),
        "family": unwrap(channel.getFamily()),
        "coefficient": unwrap(channel.getCoefficient()),
        "window": {
            "min": channel.getWindowMin(),
            "max": channel.getWindowMax(),
            "start": channel.getWindowStart(),
            "end": channel.getWindowEnd(),
        },
        "active": channel.isActive(),
    }
