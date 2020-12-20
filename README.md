[![Build Status](https://cloud.drone.io/api/badges/cknoll/yamlpyowl/status.svg)](https://cloud.drone.io/cknoll/yamlpyowl)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

# General Information

This tool (yamlpyowl) aims to read an ontology (including individuals and SWRL rules) specified via the simple and widespread data-serialization language [YAML](https://en.wikipedia.org/wiki/YAML) and represent it as collection of python-objects via the package [`owlready2`](https://owlready2.readthedocs.io). From there, a reasoner can be used or the ontology can be exported to standard-owl format *rdfxml*.

# Motivation

Almost all existing OWL2-syntax-dialects (RDF-XML, Turtle, Manchester) seem more or less unpractical for **manual authoring**. On the other hand, to encourage contributions, e.g. from students, the requirement to learn a sophisticated tool like [Protégé](http://protege.stanford.edu/) or at least some *exotic* syntax like Manchester seems to be a significant hurdle. See also [this blog post](https://keet.wordpress.com/2020/04/10/a-draft-requirements-catalogue-for-ontology-languages/) from knowledge engineering expert Maria Keet, and especially requirement HU-3: *"Have at least one compact, human-readable syntax defined so that it can be easily typed up in emails."* The tool yamlpyowl aims to explore in that direction. It relies on the widespread human-readable data-serialization language [YAML](https://en.wikipedia.org/wiki/YAML).

The project is part of the authors endeavour to simplify the understanding and the usage of semantic technologies for humans without much experience in this field, e.g. from engineering. 

# Examples

## Overview

- [examples/pizza-ontology.yml](examples/pizza-ontology.yml) (Simple example, see also below) 
- [examples/einsteins_zebra_riddle.owl.yaml](examples/einsteins_zebra_riddle.owl.yaml)
    - Understandable OWL-Representation of a famous logical puzzle, posed by A. Einstein. The reasoner solves this puzzle (see unittests).  
- [examples/regional-rules-ontology.yml](examples/regional-rules-ontology.yml) 

More examples can be found in the directory.
## Pizza Ontology Preview 

The following example is a strongly simplified fragment of the "Pizza-Ontology" which is often used as introduction, e.g. in Protégé tutorials.

```yaml
# shortcut to define multiple classes
- multiple_owl_classes:
      - Food:
          SubClassOf: "owl:Thing"
      - PizzaBase:
          SubClassOf: Food
      # ---
      - ThinAndCrispyBase:
          SubClassOf: PizzaBase
      # ---
      - PizzaTopping:
          SubClassOf: Food
      - CheezeTopping:
          SubClassOf: PizzaTopping
      - MozzarellaTopping:
          SubClassOf: CheezeTopping

      # ...

- owl_object_property:
    hasSpiciness:
        Domain:
          - "owl:Thing"
        Range:
          - Spiciness
        Characteristics:
            - Functional

- owl_object_property:
    hasIngredient:
        # shortcut: use plain string instead of len1-list
        Domain: Food
        Range: Food
        Characteristics:
            - Transitive
# ...


# create an individual 
- owl_individual:
    mypizza1:
      types:
        - Pizza

# assert some facts 
- property_facts:
    hasTopping:
        Facts:
            - mypizza1:
                - iTomatoTopping
                - iMozzarellaTopping
    hasBase:
        Facts:
            - mypizza1: iThinAndCrispyBase 
```


# Features

*yamlpyowl* implements some "magic" convenience features, i.e. extensions to OWL2. To be easily recognizable the corresponding keywords all start with `X_`.


## RelationConcepts to Simplify n-ary Relations

The concept name `X_RelationConcept` has a special meaning. It is used to simplify the creation of n-ary relations. In OWL it is typically required to create a own concept for such relations and an instance (individual) for each concrete relation, see this [W3C Working Group Note](https://www.w3.org/TR/swbp-n-aryRelations/#pattern1).

The parser of *yamlpyowl* simplifies this: For every subclass of `X_RelationConcept` (which must start with `X_`and by convention should end with `_RC`, e.g. `X_DocumentReference_RC`)) the parser automatically creates a role `X_hasDocumentReference_RC`. Its domain can be specified with the attribute `X_associatedWithClasses`. The roles which can be applied to this concept are defined as usual. The application to individuals is done by `relation_concept_facts`.

Short Example:

```yaml
- multiple_owl_classes:

      # ...

      - X_RelationConcept:
          # base class
          SubClassOf: "owl:Thing"

      - X_CombinedTasteValue_RC:
          SubClassOf: X_RelationConcept
          X_associatedWithClasses:
            - PizzaTopping


- owl_object_property:
    hasCombinationPartner:
        Domain: X_CombinedTasteValue_RC
        Range: Food

- owl_data_property:
    hasFunctionValue:
        Domain: "owl:Thing"
        Range:
            - float
        Characteristics:
            - Functional

# model two ternary relations: Mozzarella tastes 95%-good in
# combination with tomatos but only 50%-good in combination with meat.
- relation_concept_facts:
    iMozzarellaTopping:
        X_hasCombinedTasteValue_RC:
            - hasCombinationPartner: iTomatoTopping
              hasFunctionValue: 0.95
            - hasCombinationPartner: iMeatTopping
              hasFunctionValue: 0.5
```

Further example: see [regional-rules-ontology.yml](examples/regional-rules-ontology.yml)

## SWRL Rules

Semantic Web Rule Language (SWRL) rules can be defined with the keyword `swrl_rule`.
See [regional-rules-ontology.yml](examples/regional-rules-ontology.yml) for example usages.

# Documentation
... is still in preparation. However, the unittests and the docstrings might be somewhat useful.

# Requirements

- python >= 3.8
- java
- <requirements.txt> (installed automatically via pip)

The docker container which provides the runtime environment for unittests is available here: [carvk/java_python](https://hub.docker.com/repository/docker/carvk/java_python).

# Installation

- Clone the repo
- Run `pip install -e .`
    - This installs in "editable mode" best suited for experimenting and hacking.


# Development Status

Yamlpyowl is currently an early prototype and will likely be expanded (and changed) in the future. If you are interested in  using this package in your project as a dependency or in contributing to Yamlpyowl please open an issue or contact the author. The same holds for feature requests and bug reports.

# Misc remarks

-  There exists at least one earlier similar tool: [yaml2owl](https://github.com/leifw/yaml2owl), written in haskel. 
