# General Information

This tool (yamlpyowl) arises from the lack of a *fast and simple* way to define an ontology "by hand", i.e. in an ordinary text editor. Its purpose is to read a yaml-file and convert it to datastructures of the package [`owlready2`](https://owlready2.readthedocs.io). From there, a reasoner can be used or the ontology can be exported to standard-owl format *rdfxml*.

Note, there is at least one similar tool already existing: [yaml2owl](https://github.com/leifw/yaml2owl), written in haskel.

# Motivation

All existing OWL2-syntax-dialects (RDF-XML, Turtle, Manchester) seem unpractical for manual authoring. On the other hand, to encourage contributions, e.g. from students, the requirement to learn a sophisticated tool like [Protégé](http://protege.stanford.edu/) seems to be a significant hurdle. See also [this blog post](https://keet.wordpress.com/2020/04/10/a-draft-requirements-catalogue-for-ontology-languages/) from knowledge engineering expert Maria Keet, and especially requirement HU-3: *"Have at least one compact, human-readable syntax defined so that it can be easily typed up in emails."* The tool yamlpyowl aims to explore in that direction. It relies on the  human-readable data-serialization language [YAML](https://en.wikipedia.org/wiki/YAML) 

# Example

The following example is a strongly simplified fragment of the "Pizza-Ontology" which is often used as introduction.

```yaml
owl_concepts:
    Food:
        subClassOf: Thing
    # ---
    Pizza:
        subClassOf: Food
    # ---
    PizzaTopping:
        subClassOf: Food
        _createGenericIndividual: True
    MozarellaTopping:
        subClassOf: PizzaTopping
    TomatoTopping:
        subClassOf: PizzaTopping
    # ---
    Spiciness:
        subClassOf: Thing

owl_roles:
    hasSpiciness:
        mapsFrom: Thing
        mapsTo: Spiciness
        properties:
              - FunctionalProperty

    hasTopping:
        mapsFrom: Pizza
        mapsTo: Food

owl_individuals:
    iTomatoTopping:
        # note: this could be omited by autogeneration of generic individuals
        isA: TomatoTopping
    mypizza1:
        isA: Pizza
        hasTopping:
            - iTomatoTopping
```

More examples can be found in the [examples](examples) directory.


# Convenience Features

*yamlpyowl* implements some "magic" convenience features. To be easily recognizable the corresponding keywords all start with an underscore `_`. 

## Automatic Creation of "Generic Individuals"

If a concept *SomeConcept* specifies `_createGenericIndividual=True` in yaml, then there will be a individual named *iSomeConcept* which is an instance of *SomeConcept* automatically added to the ontology. This allows to easily reference concepts like *MozarellaTopping* where the individual does not carry significant information.

Example: see [pizza-ontology.yml](examples/pizza-ontology.yml)

## RelationConcepts to Simplify n-ary Relations

The concept name `_RelationConcept` has a special meaning. It is used to simplify the creation of n-ary relations. In OWL it is typically required to create a own concept for such relations and an instance (individual) for each concrete relation, see this [W3C Working Group Note](https://www.w3.org/TR/swbp-n-aryRelations/#pattern1).

The paser of *yamlpyowl* simplifies this: For every subclass of `_RelationConcept` which ends with `_RC` (e.g. `DocumentReference_RC`) the parser automatically creates a functional `hasDocumentReference_RC`. Its domain can be specified with the attribute `associatedWithClasses`. The roles which can be applied to this concept are conveniently specified with the attribute `associatedRoles`. These roles are also created automatically. They are assumed to be functional.

Short Example:

```yaml
DocumentReference_RC:
    subClassOf: _RelationConcept
    # note: yamlpyowl will automatically create a role `hasDocumentReference_RC`
    _associatedWithClasses:
        - Directive
    _associatedRoles:
        # FunctionalRoles; key-value pairs (<role name>: <range type>)
        hasDocument: Document 
        hasSection: str 
```


In the definition of an individual one can then use
```yaml
myindividual1:
    isA: Direcitve
    _hasDocumentReference_RC:
            hasDocument: law_book_of_germany
            hasSection: "§ 1.1"

```

This construction automatically creates an individual of class `_DocumentReference_RC` and endows it with the roles  `hasDocument` and `hasSection` 

Example: see [regional-rules-ontology.yml](examples/regional-rules-ontology.yml)

