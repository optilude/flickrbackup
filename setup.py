from setuptools import setup, find_packages
setup(
    name="flickrbackup",
    version="0.10",
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
    long_description=open('README.rst').read(),
    license="BSD",
    keywords="flickr backup",
    url="http://github.com/optilude/flickrbackup",
)
