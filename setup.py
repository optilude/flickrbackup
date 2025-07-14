from setuptools import setup, find_packages

import os
here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, 'README.rst'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name="flickrbackup",
    version="0.11.3",
    packages=find_packages(),
    scripts=['flickrbackup.py'],
    install_requires=['flickrapi', 'threadpool', 'python-dateutil'],
    package_data={
        # If any package contains *.txt or *.rst files, include them:
        '': ['*.txt', '*.rst', '*.md'],
    },

    # metadata for upload to PyPI
    author="Martin Aspeli",
    author_email="optilude@gmail.com",
    description="Flickr backup utility",
    long_description=long_description,
    long_description_content_type="text/x-rst",
    license="BSD",
    keywords="flickr backup",
    url="http://github.com/optilude/flickrbackup",
)
