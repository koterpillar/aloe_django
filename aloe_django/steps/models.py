"""
Step definitions and utilities for working with Django models.
"""

from __future__ import print_function
# pylint:disable=redefined-builtin
from builtins import str
# pylint:disable=redefined-builtin

import warnings
from functools import partial

from django.apps import apps
from django.core.management.color import no_style
from django.db import connection

from aloe import step
from aloe.tools import guess_types

__all__ = ('writes_models', 'write_models',
           'tests_existence', 'test_existence',
           'reset_sequence')


STEP_PREFIX = r'(?:Given|And|Then|When) '


def _models_generator():
    """
    Build a hash of model verbose names to models
    """

    for app in apps.get_app_configs():
        for model in app.get_models():
            yield (str(model._meta.verbose_name).lower(), model)
            yield (str(model._meta.verbose_name_plural).lower(), model)


try:
    MODELS = dict(_models_generator())
except:  # pylint:disable=bare-except
    warnings.warn("Models not loaded!")


_WRITE_MODEL = {}


def writes_models(model):
    """
    Register a model-specific create and update function.

    This can then be accessed via the steps:

    .. code-block:: gherkin

        And I have foos in the database:
            | name | bar  |
            | Baz  | Quux |

        And I update existing foos by pk in the database:
            | pk | name |
            | 1  | Bar  |

    A method for a specific model can define a function ``write_badgers(data,
    field)``, which creates and updates the Badger model and decorating it with
    the ``writes_models(model_class)`` decorator:

    .. code-block:: python

        @writes_models(Profile)
        def write_profile(data, field):
            '''Creates a Profile model'''

            for hash_ in data:
                if field:
                    profile = Profile.objects.get(**{field: hash_[field]})
                else:
                    profile = Profile()

                ...

            reset_sequence(Profile)

    The function must accept a list of data hashes and a field name. If field
    is not None, it is the field that must be used to get the existing objects
    out of the database to update them; otherwise, new objects must be created
    for each data hash.

    Follow up model creation with a call to :func:`reset_sequence` to
    update the database sequences.

    If you only want to modify the hash, you can make modifications and then
    pass it on to :func:`write_models`.

    .. code-block:: python

        @writes_models(Profile)
        def write_profile(data, field):
            '''Creates a Profile model'''

            for hash_ in data:

                # modify hash

            return write_models(Profile, data, field)
    """

    def decorated(func):
        """
        Decorator for the creation function.
        """
        _WRITE_MODEL[model] = func
        return func

    return decorated


_TEST_MODEL = {}


def tests_existence(model):
    """
    Register a model-specific existence test.

    This can then be accessed via the steps:

    .. code-block:: gherkin

        Then foos should be present in the database:
            | name   | bar |
            | badger | baz |

        Then foos should not be present in the database:
            | name   | bar |
            | badger | baz |

    A method for a specific model can define a function
    ``test_badgers(queryset, data)`` and decorating it with the
    ``tests_existence(model_class)`` decorator:

    .. code-block:: python

        @tests_existence(Profile)
        def test_profile(queryset, data):
            '''Test a Profile model'''

            # modify data ...

            return test_existence(queryset, data)

    If you only want to modify the hash, you can make modifications then pass
    it on to test_existence().
    """

    def decorated(func):
        """
        Decorator for the existence function.
        """
        _TEST_MODEL[model] = func
        return func

    return decorated


def get_model(name):
    """
    Convert a model's verbose name to the model class. This allows us to
    use the models verbose name in steps.
    """

    model = MODELS.get(name.lower(), None)

    assert model, "Could not locate model by name '%s'" % name

    return model


def reset_sequence(model):
    """
    Reset the ID sequence for a model.
    """
    sql = connection.ops.sequence_reset_sql(no_style(), [model])
    for cmd in sql:
        connection.cursor().execute(cmd)


def _dump_model(model, attrs=None):
    """
    Dump the model fields for debugging.
    """

    fields = []

    for field in model._meta.fields:
        fields.append((field.name, str(getattr(model, field.name))))

    if attrs is not None:
        for attr in attrs:
            fields.append((attr, str(getattr(model, attr))))

    for field in model._meta.many_to_many:
        vals = getattr(model, field.name)
        fields.append((field.name, '{val} ({count})'.format(
            val=', '.join(map(str, vals.all())),
            count=vals.count(),
        )))

    print(', '.join(
        u'{0}={1}'.format(field, value)
        for field, value in fields
    ))


def test_existence(queryset, data):
    """
    :param queryset: a Django queryset
    :param data: a single model to check for
    :returns: True if the model exists

    Test existence of a given hash in a `queryset` (or among all model
    instances if a model is given).

    Useful when registering custom tests with :func:`tests_existence`.
    """

    fields = {}
    extra_attrs = {}
    for key, value in data.items():
        if key.startswith('@'):
            # this is an attribute
            extra_attrs[key[1:]] = value
        else:
            fields[key] = value

    filtered = queryset.filter(**fields)

    if filtered.exists():
        return any(
            all(getattr(obj, k) == v for k, v in extra_attrs.items())
            for obj in filtered.all()
        )

    return False


def _model_exists_step(self, model, should_exist):
    """
    Test for the existence of a model matching the given data.
    """

    model = get_model(model)
    data = guess_types(self.hashes)

    queryset = model.objects

    try:
        existence_check = _TEST_MODEL[model]
    except KeyError:
        existence_check = test_existence

    failed = 0
    try:
        for hash_ in data:
            match = existence_check(queryset, hash_)

            if should_exist:
                assert match, \
                    "%s does not exist: %s" % (model.__name__, hash_)
            else:
                assert not match, \
                    "%s exists: %s" % (model.__name__, hash_)

    except AssertionError as exc:
        print(exc)
        failed += 1

    if failed:
        print("Rows in DB are:")
        for model in queryset.all():
            _dump_model(model,
                        attrs=[k[1:]
                               for k in data[0].keys()
                               if k.startswith('@')])

        if should_exist:
            raise AssertionError("%i rows missing" % failed)
        else:
            raise AssertionError("%i rows found" % failed)


@step(STEP_PREFIX +
      r'(?:an? )?([A-Z][a-z0-9_ ]*) should be present in the database')
def _model_exists_positive_step(self, model):
    """
    Test for the existence of a model matching the given data.

    Column names are included in a query to the database. To check model
    attributes that are not database columns (i.e. properties) prepend the
    column with an ``@`` sign.

    Example:

    .. code-block:: gherkin

        Then foos should be present in the database:
            | name   | @bar |
            | badger | baz  |

    See :func:`tests_existence`.
    """
    return _model_exists_step(self, model, True)


@step(STEP_PREFIX +
      r'(?:an? )?([A-Z][a-z0-9_ ]*) should not be present in the database')
def _model_exists_negative_step(self, model):
    """
    Tests for the existence of a model matching the given data.

    Column names are included in a query to the database. To check model
    attributes that are not database columns (i.e. properties). Prepend the
    column with an ``@`` sign.

    Example:

    .. code-block:: gherkin

        Then foos should not be present in the database:
            | name   | @bar |
            | badger | baz  |

    See :func:`tests_existence`.
    """
    return _model_exists_step(self, model, False)


def write_models(model, data, field):
    """
    :param model: a Django model class
    :param data: a list of hashes to build models from
    :param field: a field name to match models on, or None
    :returns: a list of models written

    Create or update models for each data hash.

    `field` is the field that is used to get the existing models out of
    the database to update them; otherwise, if ``field=None``, new models are
    created.

    Useful when registering custom tests with :func:`writes_models`.
    """
    written = []

    for hash_ in data:
        if field:
            if field not in hash_:
                raise KeyError(("The \"%s\" field is required for all update "
                                "operations") % field)

            model_kwargs = {field: hash_[field]}
            model_obj = model.objects.get(**model_kwargs)

            for to_set, val in hash_.items():
                setattr(model_obj, to_set, val)

            model_obj.save()

        else:
            model_obj = model.objects.create(**hash_)

        written.append(model_obj)

    reset_sequence(model)
    return written


def _write_models_step(self, model, field=None):
    """
    Write or update a model.
    """

    model = get_model(model)
    data = guess_types(self.hashes)

    try:
        func = _WRITE_MODEL[model]
    except KeyError:
        func = partial(write_models, model)

    func(data, field)


@step(r'I have(?: an?)? ([a-z][a-z0-9_ ]*) in the database:')
def _write_models_step_new(self, model):
    """
    Create models in the database.

    Syntax:

        I have `model` in the database:

    Example:

    .. code-block:: gherkin

        And I have foos in the database:
            | name | bar  |
            | Baz  | Quux |

    See :func:`writes_models`.
    """
    return _write_models_step(self, model)


@step(r'I update(?: an?)? existing ([a-z][a-z0-9_ ]*) by ([a-z][a-z0-9_]*) '
      'in the database:')
def _write_models_step_update(self, model, field):
    """
    Update existing models in the database, specifying a column to match on.

    Syntax:

        I update `model` by `key` in the database:

    Example:

    .. code-block:: gherkin

        And I update existing foos by pk in the database:
            | pk | name |
            | 1  | Bar  |

    See :func:`writes_models`.
    """
    return _write_models_step(self, model, field=field)


@step(STEP_PREFIX + r'([A-Z][a-z0-9_ ]*) with ([a-z]+) "([^"]*)"' +
      r' has(?: an?)? ([A-Z][a-z0-9_ ]*) in the database:')
def _create_models_for_relation_step(self, rel_model_name,
                                     rel_key, rel_value, model):
    """
    Create a new model linked to the given model.

    Syntax:

        And `model` with `field` "`value`" has `new model` in the database:

    Example:

    .. code-block:: gherkin

        And project with name "Ball Project" has goals in the database:
            | description                             |
            | To have fun playing with balls of twine |
    """

    model = get_model(model)
    lookup = {rel_key: rel_value}
    rel_model = get_model(rel_model_name).objects.get(**lookup)

    data = guess_types(self.hashes)

    for hash_ in data:
        hash_['%s' % rel_model_name] = rel_model

    try:
        func = _WRITE_MODEL[model]
    except KeyError:
        func = partial(write_models, model)

    func(data, None)


@step(STEP_PREFIX + r'([A-Z][a-z0-9_ ]*) with ([a-z]+) "([^"]*)"' +
      r' is linked to ([A-Z][a-z0-9_ ]*) in the database:')
def _create_m2m_links_step(self, rel_model_name,
                           rel_key, rel_value, relation_name):
    """
    Link many-to-many models together.

    Syntax:

        And `model` with `field` "`value`" is linked to `other model` in the
        database:

    Example:

    .. code-block:: gherkin

        And article with name "Guidelines" is linked to tags in the database:
            | name   |
            | coding |
            | style  |
    """

    lookup = {rel_key: rel_value}
    rel_model = get_model(rel_model_name).objects.get(**lookup)
    relation = None
    for m2m in rel_model._meta.many_to_many:
        if relation_name in (m2m.name, m2m.verbose_name):
            relation = getattr(rel_model, m2m.name)
            break
    if not relation:
        try:
            relation = getattr(rel_model, relation_name)
        except AttributeError:
            pass
    assert relation, \
        "%s does not have a many-to-many relation named '%s'" % (
            rel_model._meta.verbose_name.capitalize(),
            relation_name,
        )
    m2m_model = relation.model

    for hash_ in self.hashes:
        relation.add(m2m_model.objects.get(**hash_))


@step(r'There should be (\d+) ([a-z][a-z0-9_ ]*) in the database')
def _model_count_step(self, count, model):
    """
    Count the number of models in the database.

    Example:

    .. code-block:: gherkin

        Then there should be 0 goals in the database
    """

    model = get_model(model)

    expected = int(count)
    found = model.objects.count()
    assert found == expected, "Expected %d %s, found %d." % \
        (expected, model._meta.verbose_name_plural, found)
