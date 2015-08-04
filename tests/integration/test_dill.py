# -*- coding: utf-8 -*-
# Aloe-Django - Package for testing Django applications with Aloe
# Copyright (C) <2010-2012>  Gabriel Falcão <gabriel@nacaolivre.org>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import unicode_literals

from nose.tools import (
    assert_equals,
    assert_in,
    assert_not_equals,
)

from tests.util import in_directory, run_scenario


@in_directory(__file__, 'django', 'dill')
def test_model_creation():
    'Models are created through Lettuce steps'

    status, out = run_scenario('leaves', 'create')
    assert_equals(status, 0, out)


@in_directory(__file__, 'django', 'dill')
def test_model_update():
    'Models are updated through Lettuce steps'

    status, out = run_scenario('leaves', 'update', 1)
    assert_equals(status, 0, out)

    status, out = run_scenario('leaves', 'update', 2)
    assert_not_equals(status, 0, out)
    assert_in("IntegrityError", out)

    status, out = run_scenario('leaves', 'update', 3)
    assert_not_equals(status, 0, out)
    assert_in("The \"pk\" field is required for all update operations", out)

    status, out = run_scenario('leaves', 'update', 4)
    assert_equals(status, 0, out)


@in_directory(__file__, 'django', 'dill')
def test_model_existence_check():
    'Model existence is checked through Lettuce steps'

    status, out = run_scenario('leaves', 'existence', 1)
    assert_equals(status, 0, out)

    status, out = run_scenario('leaves', 'existence', 2)
    assert_not_equals(status, 0)
    assert_in(
        "Garden does not exist: {0}".format(
            {'name': 'Botanic Gardens'}
        ),
        out
    )
    gardens = "\n".join([
        "Rows in DB are:",
        "id=1, name=Secret Garden, area=45, raining=False",
        "id=2, name=Octopus's Garden, area=120, raining=True",
        "id=3, name=Covent Garden, area=200, raining=True",
    ])

    assert_in(gardens, out)
    assert_in("AssertionError: 1 rows missing", out)

    status, out = run_scenario('leaves', 'existence', 3)
    assert_not_equals(status, 0)
    # Cannot check exact string because the order isn't stable
    assert_in("Garden does not exist: ", out)
    assert_in(str({'name': 'Secret Garden'})[1:-1], out)
    assert_in(str({'@howbig': 'huge'})[1:-1], out)
    gardens = "\n".join([
        "Rows in DB are:",
        "id=1, name=Secret Garden, area=45, raining=False, howbig=small",
        "id=2, name=Octopus's Garden, area=120, raining=True, howbig=medium",
        "id=3, name=Covent Garden, area=200, raining=True, howbig=big",
    ])
    assert_in(gardens, out)
    assert_in("AssertionError: 1 rows missing", out)

    status, out = run_scenario('leaves', 'existence', 4)
    assert_not_equals(status, 0)
    assert_in("Expected 2 geese, found 1", out)

    status, out = run_scenario('leaves', 'existence', 5)
    assert_not_equals(status, 0)
    # Cannot check exact string because the order isn't stable
    assert_in("Garden exists: ", out)
    assert_in(str({'name': 'Secret Garden'})[1:-1], out)
    assert_in(str({'@howbig': 'small'})[1:-1], out)
    assert_in("AssertionError: 1 rows found", out)
    gardens = "\n".join([
        "Rows in DB are:",
        "id=1, name=Secret Garden, area=45, raining=False, howbig=small",
        "id=2, name=Octopus's Garden, area=120, raining=True, howbig=medium",
        "id=3, name=Covent Garden, area=200, raining=True, howbig=big",
    ])
    assert_in(gardens, out)
