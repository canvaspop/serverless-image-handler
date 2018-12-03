#!/usr/bin/python
# -*- coding: utf-8 -*-

# thumbor imaging service
# https://github.com/thumbor/thumbor/wiki

from setuptools import setup
from canvaspop_thumbor_plugins import __version__

setup(name="canvaspop_thumbor_plugins",
      version=__version__,
      description="Thumbor plugins for canvaspop",
      url="",
      author="Chris Taggart",
      author_email="taggart@canvaspop.com",
      license="All rights reserved.",
      install_requires=["thumbor"],
      packages=["canvaspop_thumbor_plugins"],
      package_dir={"canvaspop_thumbor_plugins": "canvaspop_thumbor_plugins"},
      include_package_data=True,
      zip_safe=False)