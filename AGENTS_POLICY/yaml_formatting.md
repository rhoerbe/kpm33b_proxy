For better human readability and possibility to edit text following rules are defined for YAML files in this directory:

1. Multi-line strings use the vertical bar option, such as:
    expert_sample_answer: |
      In Zero Trust, accounts serve as the authoritative identity anchor tied to vetted real-world entities. Credentials are cryptographic material bound to accounts through secure enrollment ceremonies. Authenticators are the presentation layer that proves credential possession.
      Critical relationships:                                                                                                                                          │
2. attributes are sorted alphabetically except id and name fields which always come first:
   id fields are those the start or end with 'id', name fields are those that start or end with 'name' or 'names'.
3. Each record is separated by a single blank line, followed by a comment line with 3 dashes (---).
4. Lists are indented with 2 spaces.
5. No tabs are used, only spaces.
6. No line wrapping, each line is a single logical line.
7. In multi-line text blocks avoid blank lines within the block.
8. Always remove blank lines at the end of a multi-line text block.