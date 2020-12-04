# type: ignore
"""Package deployment script."""

import setuptools

with open('README.md') as readme:
    long_description = readme.read()

setuptools.setup(name='tlru-cache',
                 version='0.1.0a1',
                 author='Leonhard S.',
                 author_email='leonhard-sei@outlook.com',
                 description='A time-aware version of functools.lru_cache.',
                 long_description=long_description,
                 long_description_content_type='text/markdown',
                 keywords='cache lru tlru lifetime',
                 url='https://github.com/leonhard-s/tlru-cache',
                 packages=setuptools.find_packages(),
                 package_data={'auraxium': ['py.typed']},
                 classifiers=['Development Status :: 3 - Alpha',
                              'Programming Language :: Python :: 3.8',
                              'License :: OSI Approved :: MIT License',
                              'Operating System :: OS Independent'],
                 license='MIT',
                 include_package_data=True,
                 zip_safe=False)
