import yaml

# noinspection PyUnresolvedReferences
import owlready2 as owl2
from owlready2 import Thing, FunctionalProperty, Imp, sync_reasoner_pellet, get_ontology, SymmetricProperty,\
    TransitiveProperty, set_render_func

from ipydex import IPS, activate_ips_on_exception
activate_ips_on_exception()


def render_using_label(entity):
    repr_str1 = entity.label.first() or entity.name
    return f"<{type(entity).name} '{repr_str1}'>"


set_render_func(render_using_label)


class Container(object):
    def __init__(self, dict):
        self.__dict__.update(dict)


class Ontology(object):
    def __init__(self, iri, fpath):
        self.new_classes = []
        self.concepts = []
        self.roles = []
        self.individuals = []
        self.rules = []

        # will be a Container later
        self.n = None

        # "http://onto.ackrep.org/pandemic_rule_ontology.owl"
        self.onto = get_ontology(iri)

        self.name_mapping = {
            "Thing": Thing,
            "FunctionalProperty": FunctionalProperty,
            "SymmetricProperty": SymmetricProperty,
            "TransitiveProperty": TransitiveProperty,
            "Imp": Imp,
        }

        self.load_ontology(fpath)

    def get_named_objects_from_sequence(self, seq):
        """

        :param seq: list of strings (coming from an yaml list)
        :return:    list of matching objects from the `self.name_mapping`
        """

        res = []
        for elt in seq:
            # assume elt is a string
            if elt not in self.name_mapping:
                raise ValueError(f"unknown name: {elt}")
            else:
                res.append(self.name_mapping[elt])
        return res

    def get_named_object(self, data_dict, key_name):
        """

        :param data_dict:   source dict (part of the parsed yaml data)
        :param key_name:    name (str) for the desired object
        :return:            the matching object from `self.name_mapping`
        """

        if key_name not in data_dict:
            return None

        value_name = data_dict[key_name]

        if value_name not in self.name_mapping:
            raise ValueError(f"unknown name: {value_name} (value for {key_name})")

        return self.name_mapping[value_name]

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

        isA = self.get_named_object(data_dict, "isA")
        for key, value in data_dict.items():
            if key == "isA":
                continue
            if key == "name":
                name = data_dict[key]
            elif key == "label":
                label.append(data_dict[key])
            else:
                property_object = self.name_mapping.get(key)
                if not property_object:
                    # key_name was not found
                    continue
                property_values = self.get_named_objects_from_sequence(value)
                kwargs[key] = property_values
        if name is None:
            name = i_name

        new_individual = isA(name=name, label=label, **kwargs)
        self.individuals.append(new_individual)
        self.name_mapping[i_name] = new_individual

        return new_individual

    def make_concept(self, name, data):

        self.ensure_is_new_name(name)

        # owl_concepts is a dict like {'GeographicEntity': {'subClassOf': 'Thing'}, ...}
        sco = self.get_named_object(data, "subClassOf")

        # now define the class
        new_class = type(name, (sco,), {})

        self.name_mapping[name] = new_class
        self.new_classes.append(new_class)
        self.concepts.append(new_class)

    # noinspection PyPep8Naming
    def make_role(self, name, data):

        self.ensure_is_new_name(name)

        # owl_roles: dict like {'hasDirective': [{'mapsFrom': 'GeographicEntity'}, {'mapsTo': 'Directive'}]}
        try:
            mapsFrom = self.name_mapping[data.get("mapsFrom")]
            mapsTo = self.name_mapping[data.get("mapsTo")]
        except KeyError:
            msg = f"Unknown concept name for `mapsFrom` or mapsTo in : {name}"
            raise ValueError(msg)

        assert issubclass(mapsFrom, Thing)
        assert issubclass(mapsTo, Thing)
        from_to_type = mapsFrom >> mapsTo

        additional_properties = self.get_named_objects_from_sequence(data.get("properties", []))
        kwargs = {}
        inverse_property = self.get_named_object(data, "inverse_property")
        if inverse_property:
            kwargs["inverse_property"] = inverse_property

        new_class = type(name, (from_to_type, *additional_properties), kwargs)
        self.name_mapping[name] = new_class
        self.new_classes.append(new_class)
        self.roles.append(new_class)

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

        for ind_name, seq in data.items():
            self.ensure_is_known_name(ind_name)
            individual = self.name_mapping[ind_name]
            ind_seq = self.get_named_objects_from_sequence(seq)

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
    def load_ontology(self, fpath):

        with open(fpath, 'r') as myfile:
            d = yaml.load(myfile)

        # provide namespace for classes via `with` statement
        with self.onto:
            for name, data in d.get("owl_concepts", {}).items():
                self.make_concept(name, data)

            for name, data in d.get("owl_roles", {}).items():
                self.make_role(name, data)

            for name, data in d.get("owl_individuals", {}).items():
                self.make_individual(name, data)

            for name, data in d.get("owl_stipulations", {}).items():
                self.process_stipulation(name, data)

            for name, data in d.get("swrl_rules", {}).items():
                self.process_swrl_rule(name, data)

        # shortcut for quic access to the name of the ontology
        self.n = Container(self.name_mapping)

    @staticmethod
    def sync_reasoner(**kwargs):
        sync_reasoner_pellet(**kwargs)


def main(fpath):
    o = Ontology(iri="test", fpath=fpath)
    return o

