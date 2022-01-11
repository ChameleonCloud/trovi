# cc-template
Template Repository to define:

* Coding Style
* Metadata for Publication
* Contribution Guide
* Software License

## Python

### Package Naming


## Metadata For Publishing to PyPI

Set Classifiers as appropriate from https://pypi.org/classifiers/

Openstack Projects tend to specify
- License :: OSI Approved :: Apache Software License

or one of:
- License :: OSI Approved :: MIT License
- License :: OSI Approved :: BSD License

Example setup.cfg

```ini
name = <package-name>
summary = <short-description>
description-file = README.md
author = University of Chicago
author-email = dev@lists.chameleoncloud.org
home-page = https://www.chameleoncloud.org
license_files = LICENSE
python_requires = '>=3.6.2'
classifier =
    Development Status :: 4 - Beta
    Environment :: OpenStack
    Intended Audience :: Science/Research
    Intended Audience :: System Administrators
    Operating System :: POSIX :: Linux
    Programming Language :: Python
    Programming Language :: Python :: 3
    Programming Language :: Python :: 3.6
    Programming Language :: Python :: 3.7
    Programming Language :: Python :: 3.8
```

