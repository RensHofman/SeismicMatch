# -*- coding: utf-8 -*-

from setuptools import setup

setup(
    name='SeismicMatch',
    version='0.1',
    packages=[],
    py_modules=['common', 'data_handler'],
    install_requires=[
        # 'numpy<=1.23.5',
        # 'scipy==1.4.1',
        # 'cupy==9.6.0',
        # 'obspy==1.2.2',
        # 'pyyaml'
    ],
    entry_points={
        'console_scripts': [
            'create_config=scripts.create_config:main',
            'create_templates=scripts.create_templates:main',
            'match_templates=scripts.match_templates:main',
            'create_event_families=scripts.create_event_families:main'
        ]
    },
)
