from collections import defaultdict

import re
import yaml
import pydantic
from typing import Union, List, Dict, Callable, Any

# noinspection PyUnresolvedReferences
import owlready2 as owl2
from owlready2 import Thing, FunctionalProperty, Imp, sync_reasoner_pellet, SymmetricProperty,\
    TransitiveProperty, set_render_func, ObjectProperty, DataProperty

# noinspection PyUnresolvedReferences
from ipydex import IPS, activate_ips_on_exception
activate_ips_on_exception()


def render_using_label(entity):
    repr_str1 = entity.label.first() or entity.name
    return f"<{type(entity).name} '{repr_str1}'>"


set_render_func(render_using_label)


class Container(object):
    def __init__(self, arg=None, **data_dict):
        if isinstance(arg, dict) and not data_dict:
            data_dict = arg
        self.__dict__.update(data_dict)

    def __repr__(self):
        name = getattr(self, "name", "<unnamed>")
        data = getattr(self, "data")

        return f"<{name}-Container: {data}"


class OntologyManager(object):
    def __init__(self, fpath, world=None):
        """

        :param fpath:   path of the yaml-file containing the ontology
        :param world:   owl2 world object holding all the RDF-data (default: None)
        """
        if world is None:
            world = owl2.default_world

        self.world = world
        self.raw_data = None
        self.new_python_classes = []
        self.concepts = []
        self.roles = []
        self.individuals = []
        self.rules = []

        # we cannot store arbitrary python attributes in owl-objects directly, hence we use this dict
        # keys will be tuples of the form: (obj, <attribute_name_as_str>)
        self.custom_attribute_store = {}

        # will be a Container later for quick access to the names of the ontology
        self.n = None
        self.quoted_string_re = re.compile("(^\".*\"$)|(^'.*'$)")

        self._load_yaml(fpath)

        # extract the internationalized ressource identifier or use default
        # self.iri = "https://w3id.org/yet/undefined/ontology#"# self.raw_data.get("iri", "https://w3id.org/yet/undefined/ontology#")
        self.iri = self._get_from_all_dicts("iri", "https://w3id.org/yet/undefined/ontology#")
        self.onto = self.world.get_ontology(self.iri)

        self.name_mapping = {
            "owl:Thing": Thing,
            "FunctionalProperty": FunctionalProperty,
            "SymmetricProperty": SymmetricProperty,
            "TransitiveProperty": TransitiveProperty,
            "Imp": Imp,
            "int": int,
            "float": float,
            "str": str,

        }

        self.logic_functions = {
            "Or": owl2.Or,
            "And": owl2.And,
            "Not": owl2.Not,
        }
        self.name_mapping.update(self.logic_functions)

        self.top_level_parse_functions = {}
        self.normal_parse_functions = {}
        self.create_tl_parse_function("owl_individual", self.make_individual_from_dict)
        self.create_tl_parse_function("owl_multiple_individuals", self.make_multiple_individuals_from_dict)
        self.create_tl_parse_function("owl_class", self.make_class_from_dict)

        self.create_nm_parse_function("types")
        self.create_nm_parse_function("EquivalentTo", outer_func=self.containerFactoryFactory("EquivalentTo"))

        self.create_nm_parse_function("OneOf", outer_func=owl2.OneOf)

        self.excepted_non_function_keys = [
            "iri",
        ]

        self.load_ontology()

    def _dbg(self, args):
        IPS()
        return args

        # ensure that obj is a class
        assert isinstance(obj, Thing)
        return obj

    def atom_or_And(self, arg: list):
        if len(arg) == 1:
            return arg[0]
        else:
            return owl2.And(arg)

    def containerFactoryFactory(self, container_ame: str) -> callable:

        class OntoContainer(Container):
            def __init__(self):
                super().__init__(self)
                self.name = container_ame
                self.data = None

        def outer_func(arg: list) -> OntoContainer:

            res = OntoContainer()
            res.data = self.atom_or_And(arg)

            return res

        return outer_func

    def create_tl_parse_function(self, name: str, func: callable) -> None:
        assert name not in self.top_level_parse_functions
        self.top_level_parse_functions[name] = func

    def create_nm_parse_function(self, name: str, outer_func=None, inner_func=None) -> None:
        if outer_func is None:
            outer_func = lambda x: x
        if inner_func is None:
            inner_func = lambda x: x
        assert name not in self.top_level_parse_functions
        self.normal_parse_functions[name] = TreeParseFunction(name, outer_func, inner_func, self)

    def cas_get(self, key, default=None):
        return self.custom_attribute_store.get(key, default)

    def cas_set(self, key, value):
        self.custom_attribute_store[key] = value

    def resolve_name(self, object_name, accept_unquoted_strs=False):
        """
        Try to find object_name in `self.name_mapping` if it is not a number or a string literal.
        Raise Exception if not found.

        :param object_name:
        :param accept_unquoted_strs:    boolean (default=False). Specify whether unquoted strings which are no valid
                                        names should provoke an error (default) or should be returned as they are
        :return:
        """

        # assume elt is a string
        if isinstance(object_name, (float, int)):
            return object_name
        elif isinstance(object_name, str) and self.quoted_string_re.match(object_name):
            # quoted strings are not interpreted as names
            return object_name

        elif isinstance(object_name, str) and object_name in self.name_mapping:
            return self.name_mapping[object_name]
        else:
            if accept_unquoted_strs:
                return object_name
            else:
                raise ValueError(f"unknown name (or type): {object_name}")

    def ensure_is_known_name(self, name):
        if name not in self.name_mapping:
            msg = f"The name {name} was not found in the name space"
            raise ValueError(msg)

    def ensure_is_new_name(self, name):
        if name in self.name_mapping:
            msg = f"This concept name was declared more than once: {name}"
            raise ValueError(msg)

    def make_individual_from_dict(self, data_dict: dict) -> dict:
        """
        :param data_dict:
        :return:
        """

        assert len(data_dict) == 1
        assert check_type(data_dict, Dict[str, dict])

        individual_name, inner_dict = list(data_dict.items())[0]
        self.ensure_is_new_name(individual_name)

        types = self.process_tree({"types": inner_dict.get("types")}, squeeze=True)

        main_type = types[0]
        ind = main_type(name=individual_name)

        if len(types) > 1:
            # !! maybe handle multiple types
            raise NotImplementedError

        self.name_mapping[individual_name] = ind

        return ind

    def make_multiple_individuals_from_dict(self, data_dict: dict) -> dict:
        """
        :param data_dict:
        :return:
        """

        try:
            names = data_dict.pop("names")
        except KeyError:
            msg = f"Statement `owl_multiple_individuals` must have attribute `names`. {data_dict}"
            raise KeyError(msg)

        for name in names:
            self.make_individual_from_dict({name: dict(data_dict)})

    def make_class_from_dict(self, data_dict: dict) -> dict:
        assert len(data_dict) == 1
        assert check_type(data_dict, Dict[str, dict])

        class_name, inner_dict = list(data_dict.items())[0]

        processed_inner_dict = self.process_tree(inner_dict)
        sco = (owl2.Thing,)
        # create the class
        new_class = type(class_name, sco, {})
        self.name_mapping[class_name] = new_class
        self.concepts.append(new_class)

        # !! 3.8 -> use `:=` here

        if equivalent_to := processed_inner_dict["EquivalentTo"]:

            # noinspection PyUnresolvedReferences
            new_class.equivalent_to.extend(ensure_list(equivalent_to.data))

        return new_class

    def process_tree(self, normal_dict: dict, squeeze=False) -> Dict[str, Any]:

        res = {}
        for key, value in normal_dict.items():
            key_func = self._resolve_yaml_key(self.normal_parse_functions, key)
            res[key] = key_func(value)

        if squeeze:
            assert len(res) == 1
            res = res[key]

        return res

    def process_swrl_rule(self, rule_name, data):
        """
        Construnct the swrl-object (Semantic Web Rule Language) from the source code

        :param rule_name:
        :param data:
        :return:
        """
        self.ensure_is_new_name(rule_name)

        type_object = self.get_named_object(data, "isA")

        # TODO find out what Imp actually means and whether it is needed in the yaml-source at all
        assert type_object is Imp

        rule_src = data["rule_src"]

        # create the instance
        new_rule = type_object()
        new_rule.set_as_rule(rule_src)
        self.rules.append(new_rule)

        self.name_mapping[rule_name] = new_rule

    # noinspection PyPep8Naming
    def _load_yaml(self, fpath):
        with open(fpath, 'r') as myfile:
            self.raw_data = yaml.load(myfile)

        assert check_type(self.raw_data, List[dict])

    def _get_from_all_dicts(self, key, default=None):
        # src: https://stackoverflow.com/questions/9819602/union-of-dict-objects-in-python#comment23716639_12926008
        all_dicts = dict(i for dct in self.raw_data for i in dct.items())
        return all_dicts.get(key, default)

    @staticmethod
    def _resolve_yaml_key(data_dict, key):

        if key not in data_dict:
            msg = f"Unknown keyword in yaml-file: {key} \ncomplete data:\n{data_dict}"
            raise KeyError(msg)

        return data_dict[key]

    def load_ontology(self):

        # provide namespace for classes via `with` statement
        res = []
        with self.onto:

            for top_level_dict in self.raw_data:
                assert check_type(top_level_dict, Dict[str, Union[str, dict]])
                assert len(top_level_dict) == 1
                key, inner_dict = list(top_level_dict.items())[0]

                if key in self.excepted_non_function_keys:
                    continue

                # get function or fail gracefully
                tl_parse_function = self._resolve_yaml_key(self.top_level_parse_functions, key)

                # now call the matching function
                res.append(tl_parse_function(inner_dict))

        # shortcut for quic access to the name of the ontology
        self.n = Container(self.name_mapping)

    def make_query(self, qsrc):
        """
        Wrapper arround owlready2.query_owlready(...) which makes the result a set

        :param qsrc:    query source

        :return:        set of results
        """

        g = self.world.as_rdflib_graph()

        r = g.query_owlready(qsrc)
        res_list = []
        for elt in r:
            # ensure that here each element is a sequences of lenght 1
            assert len(elt) == 1
            res_list.append(elt[0])

        # drop duplicates
        return set(res_list)

    def sync_reasoner(self, **kwargs):
        sync_reasoner_pellet(x=self.world, **kwargs)


def ensure_list(obj, allow_tuple=True):
    """
    return [obj] if obj is not already a list (or optionally tuple)

    :param obj:
    :param allow_tuple:
    :return:
    """
    if isinstance(obj, list):
        return obj

    elif allow_tuple and isinstance(obj, tuple):
        return obj
    elif not allow_tuple and isinstance(obj, tuple):
        return list(obj)
    else:
        return [obj]


def check_type(obj, expected_type):
    """
    Use the pydantic package to check for (complex) types from the typing module.
    If type checking passes returns `True`. This allows to use `assert check_type(...)` which allows to omit those
    type checks (together with other assertations) for performance reasons, e.g. with `python -O ...` .


    :param obj:             the object to check
    :param expected_type:   primitive or complex type (like typing.List[dict])
    :return:                True (or raise an TypeError)
    """

    class Model(pydantic.BaseModel):
        data: expected_type

    # convert ValidationError to TypeError if the obj does not match the expected type
    try:
        Model(data=obj)
    except pydantic.ValidationError as ve:
        raise TypeError(str(ve.errors()))

    return True  # allow constructs like assert check_type(x, List[float])


class TreeParseFunction(object):
    # instances = {}

    def __init__(self, name: str, outer_func: callable, inner_func: callable, om: OntologyManager) -> None:
        """

        :param name:
        :param inner_func:
        om: OntologyManager
        """
        self.name = name
        self.inner_func = inner_func
        self.outer_func = outer_func
        self.om = om

        # add this object to the "global" mapping
        # assert name not in self.instances
        # self.instances[name] = self

    def __call__(self, arg, **kwargs):

        if isinstance(arg, list):

            results = [self.inner_func(self.om.resolve_name(elt, True)) for elt in arg]
        elif isinstance(arg, dict):
            results = []
            for key, value in arg.items():
                key_func = self.om.normal_parse_functions.get(key)
                results.append(key_func(value))

        return self.outer_func(results)

