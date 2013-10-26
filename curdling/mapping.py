from __future__ import absolute_import, unicode_literals, print_function
from collections import defaultdict
from distlib.version import LegacyMatcher, LegacyVersion

from . import util
from .exceptions import BrokenDependency, VersionConflict


def wheel_version(path):
    """Retrieve the version inside of a package data slot

    If there's no key `version` inside of the data dictionary, we'll
    try to guess the version number from the file name:

    ['forbiddenfruit', '0.1.1', 'cp27', 'none', 'macosx_10_8_x86_64.whl']
                          ^
    this is the guy we get in that crazy split!
    """
    return path.split('-')[1]


class Mapping(object):

    def __init__(self):
        # This is the structure that saves all the meta-data about all the
        # requested packages. You should take a look in the file
        # `tests/unit/test_mapping.py`. It contains all the possible
        # combinations of values stored in this structure.
        self.requirement_structure = lambda: {
            'dependency_of': [],
            'wheel': None,
            'exception': None,
        }

        self.mapping = {}

    def file_requirement(self, requirement, dependencies=None):
        entry = self.mapping.get(requirement, None)
        if not entry:
            entry = self.requirement_structure()
            self.mapping[requirement] = entry
        entry['dependency_of'].extend(dependencies or [None])

    def set_data(self, requirement, field, value):
        self.mapping[requirement][field] = value

    def get_data(self, requirement, field):
        return self.mapping[requirement][field]

    def filed_packages(self):
        return list(set(util.parse_requirement(r).name for r in self.mapping.keys()))

    def get_requirements_by_package_name(self, package_name):
        return [x for x in self.mapping.keys()
            if util.parse_requirement(x).name == util.parse_requirement(package_name).name]

    def available_versions(self, package_name):
        return sorted(set(wheel_version(self.get_data(requirement, 'wheel'))
            for requirement in self.mapping.keys()
                if util.parse_requirement(requirement).name == package_name),
                      reverse=True)

    def matching_versions(self, requirement):
        matcher = LegacyMatcher(requirement.replace('-', '_'))
        package_name = util.parse_requirement(requirement).name
        versions = self.available_versions(package_name)
        return [version for version in versions
            if matcher.match(version)]

    def broken_versions(self, requirement):
        package_name = util.parse_requirement(requirement).name
        versions = self.available_versions(package_name)
        return [version for version in versions
            if self.get_data(requirement, 'exception')
                is not None]

    def is_primary_requirement(self, requirement):
        return bool(self.mapping[requirement]['dependency_of'].count(None))

    def best_version(self, requirement_or_package_name, debug=False):
        package_name = util.parse_requirement(requirement_or_package_name).name
        requirements = self.get_requirements_by_package_name(package_name)

        # Used to remember in which requirement we found each version
        requirements_by_version = {}
        get_requirement = lambda v: (v, requirements_by_version[v])

        # A helper that sorts the versions putting the newest ones first
        newest = lambda versions: sorted(versions, key=LegacyVersion, reverse=True)[0]

        # Gather all version info available inside of all requirements
        all_versions = []
        all_constraints = []
        primary_versions = []
        for requirement in requirements:
            version = wheel_version(self.get_data(requirement, 'wheel'))
            requirements_by_version[version] = requirement
            if self.is_primary_requirement(requirement):
                primary_versions.append(version)

            versions = self.matching_versions(requirement)
            all_versions.extend(versions)
            all_constraints.append(util.safe_constraints(requirement))

        # List that will gather all the primary versions. This catches
        # duplicated first level requirements with different versions.
        if primary_versions:
            return get_requirement(newest(primary_versions))

        # Find all the versions that appear in all the requirements
        compatible_versions = [v for v in all_versions
            if all_versions.count(v) == len(requirements)]

        if not compatible_versions:
            raise VersionConflict(
                'Requirement: {0} ({1}), Available versions: {2}'.format(
                    package_name,
                    ', '.join(sorted(filter(None, all_constraints), reverse=True)),
                    ', '.join(sorted(self.available_versions(package_name), reverse=True)),
                ))

        return get_requirement(newest(compatible_versions))
