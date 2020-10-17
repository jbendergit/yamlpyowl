from collections import defaultdict

import re
import yaml

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
    def __init__(self, data_dict):
        self.__dict__.update(data_dict)


class Ontology(object):
    def __init__(self, fpath, world=None):
        """

        :param fpath:   path of the yaml-file containing the ontology
        :param world:   owl2 world object holding all the RDF-data (default: None)
        """
        if world is None:
            world = owl2.default_world

        self.world = world
        self.raw_data = None
        self.new_classes = []
        self.concepts = []
        self.roles = []
        self.individuals = []
        self.rules = []

        # class Name which has a special meaning if defined
        self._RelationConcept = None
        self.relation_concept_main_roles = []  # list of all subclasses of self._Relation_Concept
        self.auto_generated_name_numbers = defaultdict(lambda: 0)

        # we cannot store arbitrary python attributes in owl-objects directly, hence we use this dict
        # keys will be tuples of the form: (obj, <attribute_name_as_str>)
        self.custom_attribute_store = {}

        # will be a Container later
        self.n = None
        self.quoted_string_re = re.compile("(^\".*\"$)|(^'.*'$)")

        self._load_yaml(fpath)

        # extract the internationalized ressource identifier or use default
        self.iri = self.raw_data.get("iri", "https://w3id.org/yet/undefined/ontology#")
        self.onto = self.world.get_ontology(self.iri)

        self.name_mapping = {
            "Thing": Thing,
            "FunctionalProperty": FunctionalProperty,
            "SymmetricProperty": SymmetricProperty,
            "TransitiveProperty": TransitiveProperty,
            "Imp": Imp,
            "int": int,
            "float": float,
            "str": str,

        }

        self.load_ontology()

    def get_objects_from_sequence(self, seq, accept_unquoted_strs=False):
        """
        If an element of the sequence is a number or a string literal delimited by `"` it is unchanged.
        Other strings are interpreted as names from `self.name_mapping`.

        :param seq: list of objects (coming from an yaml list)
        :return:    list of matching objects from the `self.name_mapping`
        :param accept_unquoted_strs:
        """

        res = []
        for elt in seq:
            res.append(self.resolve_name(elt, accept_unquoted_strs))

        return res

    def get_named_object(self, data_dict, key_name, default="<raise exception>"):
        """

        :param data_dict:   source dict (part of the parsed yaml data)
        :param key_name:    name (str) for the desired object
        :return:            the matching object from `self.name_mapping`
        :param default:     value which should be returned, if the key is not found.
                            This parameter defaults to a special string literal which results
                            in an exception being raised instead returning that literal.
        """

        if key_name not in data_dict:
            return None

        # `data_dict[key_name]` could be a single value or a list
        # temporarily ensure list and later squeeze this list if necessary
        value_name_list = data_dict[key_name]
        if not isinstance(value_name_list, list):
            assert isinstance(value_name_list, str)
            value_name_list = [value_name_list]
            list_flag = False
        else:
            list_flag = True

        res = []
        for value_name in value_name_list:
            if value_name not in self.name_mapping:
                if default == "<raise exception>":
                    raise ValueError(f"unknown name: {value_name} (value for {key_name})")
                else:
                    # !! TODO: is this still needed/useful?
                    res.append(default)
            else:
                res.append(self.name_mapping[value_name])

        if list_flag:
            return res
        else:
            # there was no list -> return the only value
            return res[0]

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

    # noinspection PyPep8Naming
    def make_individual(self, i_name, data_dict):

        kwargs = {}
        label = []
        name = None

        # store relation-concept-role-data and process it after the creation of the individual
        relation_concept_role_mappings = {}

        is_a_type = self.get_named_object(data_dict, "isA")
        for key, value in data_dict.items():
            if key == "isA":
                continue
            if key == "name":
                name = data_dict[key]
            elif key == "label":
                label_object = ensure_list(data_dict[key])
                label.extend(label_object)
                if any(not isinstance(elt, str) for elt in label):
                    msg = f"Invalid type ({type(label_object)}) for label of individual '{i_name}'." \
                          f"Expected str or list of str."
                    raise TypeError(msg)

            else:

                res = self._handle_key_for_individual(key, value, i_name, relation_concept_role_mappings)
                if res is None:
                    continue
                else:
                    assert isinstance(res, dict)
                    kwargs.update(res)

        if name is None:
            name = i_name

        new_individual = self._create_individual(is_a_type, name, i_name, label, kwargs)

        self._handle_relation_concept_roles(new_individual, relation_concept_role_mappings)
        return new_individual

    def _handle_key_for_individual(self, key, value, i_name, relation_concept_role_mappings):
        """

        :param key:
        :param value:
        :param relation_concept_role_mappings:  dict or None; see make_individual
                                                None -> ignore this

        :return:    None ore dict
        """

        # get the role (also called property)
        property_object = self.name_mapping.get(key)
        if not property_object:
            # key_name was not found
            return None

        if isinstance(value, str):
            value_object = self.name_mapping.get(value)
        else:
            value_object = None
        accept_unquoted_strs = (str in property_object.range)

        if property_object in self.relation_concept_main_roles:
            if relation_concept_role_mappings is not None:
                # save the relevant information for later processing
                relation_concept_role_mappings[property_object] = value
            return None
        elif isinstance(value, list):
            property_values = self.get_objects_from_sequence(value, accept_unquoted_strs)
        elif isinstance(value, str) and value_object:
            property_values = value_object
        elif isinstance(value, (float, int, str)):
            # todo: raise exception for unallowed unquoted strings here
            property_values = value
        else:
            msg = f"Invalid type ({type(value)}) for property '{key}' of individual '{i_name}'." \
                f"Expected int, float, str or list."
            raise TypeError(msg)

        return {key: property_values}

    def _create_individual(self, is_a_type, name, i_name, label, kwargs):
        """

        :param is_a_type:
        :param name:
        :param i_name:
        :param label:
        :param kwargs:      dict like {'hasPart': [indv1, indv2, ...]}
        :return:
        """

        new_individual = is_a_type(name=name, label=label, **kwargs)
        self.individuals.append(new_individual)
        self.name_mapping[i_name] = new_individual

        return new_individual

    def _handle_relation_concept_roles(self, individual, rcr_mappings):
        """
        There might be yaml-attributes like "hasDocumentReference_RC" which refer to a RelationConcept ("RC")

        yaml-soruce:
        ```yaml

        dir_rule1:
            isA: Directive
            hasDocumentReference_RC:                        # <- this is the relation concept role
                hasDocument: law_book_of_germany
                hasSection: "§ 1.1"
        ```

        :param individual:
        :param rcr_mappings:    dict ("relation_concept_role_mapping"); key: role, value: dict
        :return:
        """

        for rc_role, data_dict in rcr_mappings.items():

            assert len(rc_role.range) == 1  # currently not clear what to do otherwise
            relation_concept = rc_role.range[0]

            # now create an instance of this type
            relation_individual = self._create_new_relation_concept(relation_concept, data_dict)

            # now perform something like `indv1.hasDocumentReference_RC.append(relation_individual)`
            getattr(individual, rc_role.name).append(relation_individual)

    def _create_new_relation_concept(self, rc_type, data_dict):
        # generate name, create individual with role assignments
        i = self.auto_generated_name_numbers[rc_type]
        self.auto_generated_name_numbers[rc_type] += 1
        relation_name = f"i{rc_type.name}_{i}"

        kwargs = {}
        for key, value in data_dict.items():
            res = self._handle_key_for_individual(key, value, relation_name, None)
            if res is not None:
                kwargs.update(res)

        relation_individual = self._create_individual(rc_type, relation_name, relation_name, label=None, kwargs=kwargs)

        return relation_individual

    def make_concept(self, name, data):

        self.ensure_is_new_name(name)
        sco = self._get_sco(data)

        # auto-create a generic individual (which is useful to be referenced in roles)
        # noinspection PyTypeChecker
        cgi = self._get_cgi_flag(data, sco)

        new_concept = self._create_concept(name, sco, cgi)

        # see docs for backgorund information on "RelationConcept"
        if name == "X_RelationConcept":
            assert self._RelationConcept is None
            self._RelationConcept = new_concept
        elif self._RelationConcept in sco:
            # this is a subclass of X_RelationConcept - automatically create roles
            if not name.startswith("X_"):
                msg = "Names of subclasses of `X_RelationConcept` are expected to start with `X_`."
                raise ValueError(msg)
            self._create_rc_roles(new_concept, name, data)

    def _create_rc_roles(self, relation_concept, concept_name, concept_data):
        """
        Automatically create roles for relation concept
        :param concept_name:
        :param concept_data:
        :return:
        """
        assert self._RelationConcept in relation_concept.is_a

        # create the main role for this RelationConcept
        assert concept_name[:2] == "X_"
        main_role_name = f"X_has{concept_name[2:]}"
        main_role_domain = self.get_named_object(concept_data, "X_associatedWithClasses")

        main_role = self._create_role(main_role_name, mapsFrom=main_role_domain, mapsTo=[relation_concept])
        self.relation_concept_main_roles.append(main_role)

        # create furhter roles
        further_roles_dict = concept_data.get("X_associatedRoles")

        for further_role_name in further_roles_dict.keys():
            further_role_range = self.get_named_object(further_roles_dict, further_role_name)

            # all these roles are functional
            further_role = self._create_role(further_role_name, mapsFrom=relation_concept, mapsTo=further_role_range,
                                             additional_properties=(FunctionalProperty, ))

    def _create_concept(self, name, sco, cgi):
        """
        Actually create a concept

        :param name:
        :param sco:
        :param cgi:     cgi_flag
        :return:
        """

        # now define the class
        new_class = type(name, sco, {})

        self.name_mapping[name] = new_class
        self.new_classes.append(new_class)
        self.concepts.append(new_class)

        if cgi:
            # store that property in the class-object (available for look-up of child classes)
            self.custom_attribute_store[(new_class, "X_createGenericIndividual")] = True

            # create the generic individual:
            gi_name = f"i{name}"
            gi = new_class(name=gi_name)
            self.individuals.append(gi)
            self.name_mapping[gi_name] = gi

        return new_class

    def _get_sco(self, data):
        """
        extract parent class(es) from data-dict and ensure thats a tuple

        :param data:
        :return:        None
        """

        # owl_concepts is a dict like {'GeographicEntity': {'subClassOf': 'Thing'}, ...}
        sco = self.get_named_object(data, "subClassOf")

        if not isinstance(sco, (list, tuple)):
            sco = (sco,)
        else:
            sco = tuple(sco)

        return sco

    def _get_cgi_flag(self, data, parent_classes):
        """
        Look for `_createGenericIndividual` attribute in data-dict. If not found, look in parent class(es).
        If not found set to `False` (default). Raise error for inconsistency.

        :param data:            data-dict
        :param parent_classes:  sequence of parent classes
        :return:
        """

        cgi = data.get("X_createGenericIndividual")

        if cgi is None:
            # look at the parent classes (could be more than one)
            cgi_flags = []
            for parent_class in parent_classes:
                cgi_flags.append(self.custom_attribute_store.get((parent_class, "X_createGenericIndividual"), False))

            # check for inconsistency
            assert len(cgi_flags) > 0
            if not cgi_flags.count(cgi_flags[0]) == len(cgi_flags):
                msg = f"Inconsistency found wrt the createGenericIndividual Option deduced from the following " \
                      f"parent classes: {parent_classes} ({cgi_flags})"
                raise ValueError(msg)

            # now we can assume that all flags are identical
            cgi = cgi_flags[0]
        return cgi

    # noinspection PyPep8Naming
    def make_role(self, name, data):

        self.ensure_is_new_name(name)

        # owl_roles: dict like {'hasDirective': [{'mapsFrom': 'GeographicEntity'}, {'mapsTo': 'Directive'}]}
        try:
            mapsFrom = self.name_mapping[data.get("mapsFrom")]

            mapping_target = data.get("mapsTo")
            if not isinstance(mapping_target, list):
                mapsTo = [self.name_mapping[mapping_target]]
            else:
                mapsTo = [self.name_mapping[elt] for elt in mapping_target]
        except KeyError:
            msg = f"Unknown concept name for `mapsFrom` or mapsTo in : {name}"
            raise ValueError(msg)

        assert issubclass(mapsFrom, Thing)

        for elt in mapsTo:
            assert issubclass(elt, (Thing, int, float, str))

        additional_properties = self.get_objects_from_sequence(data.get("properties", []))
        inverse_property = self.get_named_object(data, "inverse_property")

        self._create_role(name, mapsFrom, mapsTo, inverse_property, additional_properties)

    # noinspection PyPep8Naming
    def _create_role(self, name, mapsFrom, mapsTo, inverse_property=None, additional_properties=None):
        """

        :param name:
        :param mapsFrom:
        :param mapsTo:
        :param inverse_property:
        :param additional_properties:
        :return:
        """
        mapsTo = ensure_list(mapsTo)
        mapsFrom = ensure_list(mapsFrom)

        kwargs = {"domain": mapsFrom, "range": mapsTo}
        if inverse_property:
            kwargs["inverse_property"] = inverse_property
        # choose the right base class for the property and check consistency
        basic_types = {int, float, str}

        if set(mapsTo).intersection(basic_types):
            # the range contains basic data types
            # assert that it *only* contains basic types
            assert set(mapsTo).union(basic_types) == basic_types
            PropertyBaseClass = DataProperty
        else:
            PropertyBaseClass = ObjectProperty

        if additional_properties is None:
            additional_properties = []

        new_role = type(name, (PropertyBaseClass, *additional_properties), kwargs)
        self.name_mapping[name] = new_role
        self.new_classes.append(new_role)
        self.roles.append(new_role)
        return new_role

    def process_stipulation(self, role_name, data):
        """
        A stipulation is a piece of knowledge which is added after the initial creation of a knowledge base.
        This method assigns roles to exisiting individuals. Example: ind_1.hasPart.extend(ind_x, ind_y)

        :param role_name:   name of the role (like 'hasPart')
        :param data:        dict like: {'ind_1': ['ind_x', 'ind_y'], ...}
                            the occuring strings are assumed to be valid names
        :return:
        """
        self.ensure_is_known_name(role_name)
        role = self.name_mapping[role_name]
        if not issubclass(role, owl2.ObjectProperty):
            msg = f"{role_name} should have been a role-name. Instead it is a {type(role)}"
            raise ValueError(msg)

        self._process_ordinary_stipulation(role_name, data)

    def _process_ordinary_stipulation(self, role_name, data):
        """
        handle cases like:
        ```yaml
        owl_stipulations:
            hasDirective:
                germany:
                  - dir_rule1
                  - dir_rule2
        ```

        :param role_name:
        :param data:
        :return:
        """

        for ind_name, seq in data.items():
            self.ensure_is_known_name(ind_name)
            individual = self.name_mapping[ind_name]
            ind_seq = self.get_objects_from_sequence(seq)

            # apply this role to the individual
            getattr(individual, role_name).extend(ind_seq)

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

    def load_ontology(self):

        # provide namespace for classes via `with` statement
        with self.onto:

            # class _createGenericIndividual(Thing >> bool, FunctionalProperty):
            #     pass

            for name, data in self.raw_data.get("owl_concepts", {}).items():
                self.make_concept(name, data)

            for name, data in self.raw_data.get("owl_roles", {}).items():
                self.make_role(name, data)

            for name, data in self.raw_data.get("owl_individuals", {}).items():
                self.make_individual(name, data)

            for name, data in self.raw_data.get("owl_stipulations", {}).items():
                self.process_stipulation(name, data)

            for name, data in self.raw_data.get("swrl_rules", {}).items():
                self.process_swrl_rule(name, data)

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
    if isinstance(obj, list):
        return obj

    elif allow_tuple and isinstance(obj, tuple):
        return obj
    elif not allow_tuple and isinstance(obj, tuple):
        return list(obj)
    else:
        return [obj]
