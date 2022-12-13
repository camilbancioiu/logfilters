import re
from typing import List, Dict, Callable
from functools import partial


Aliases = Dict[str, str]
AliasSource = List[str]
AliasBuilder = Callable[[Aliases, AliasSource, str], str]
AliasResolver = Callable[[str], str]
AliasReplacer = Callable[[str], str]


def make_alias_replacer(alias_re: re.Pattern,
                        match_group_index: int,
                        alias_builder: AliasBuilder,
                        alias_source: AliasSource) -> AliasReplacer:

    resolver = make_alias_resolver(alias_source, alias_builder)

    return partial(replace_with_aliases,
                   alias_re,
                   match_group_index,
                   resolver)


def make_alias_resolver(alias_source: AliasSource,
                        alias_builder: AliasBuilder) -> AliasResolver:

    aliases: Aliases = dict()

    # TODO replace with functools.partial()
    def resolver(original_string: str) -> str:
        try:
            alias = aliases[original_string]
        except KeyError:
            alias = alias_builder(aliases, alias_source, original_string)
            aliases[original_string] = alias
        return alias

    return resolver


def replace_with_aliases(alias_re: re.Pattern,
                         match_group_index: int,
                         alias_resolver: AliasResolver,
                         line: str) -> str:
    matches = alias_re.finditer(line)
    for match in matches:
        original_string = match[match_group_index]
        if original_string is not None:
            alias = alias_resolver(original_string)
            line = line.replace(original_string,
                                alias)
    return line
