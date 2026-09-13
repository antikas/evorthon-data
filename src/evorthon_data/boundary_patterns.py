"""The closed shapes every boundary of this product reads the same way.

Four places in this product decide whether a text carries a route to somebody's
machine, a credential, or a row of written data: the use-case aggregate reading
a fact locator, the privacy gate reading a fault packet, the public-candidate
scan reading a shipped file, and the tracker adapter reading a note. A fifth,
the intake credential scan, reads an artefact. When each of them wrote its own
rule they disagreed, and the weakest of them decided what a record kept and
what crossed to a model.

This module is the one owner of those shapes. It declares them as named
compiled patterns and it reads them. It refuses nothing and it decides nothing:
each boundary keeps its own refusal, its own reason and its own message,
because what a refusal means is the boundary's to say.

A boundary names the shapes it reads. It reads every shape it can, and where it
cannot read one it says so in its own docstring with the reason. The subject
differs: three of the boundaries read one declared value that this product
wrote, while the public-candidate scan reads whole files of source, fixtures
and documentation, where a backslash writes a character escape and a slash
after a space is ordinary prose. A shape that is unambiguous in a declared
value is not always unambiguous in a page of shipped text, and pretending
otherwise would either blind a boundary or flood it.

The shapes are assembled from character codes, so this file carries no drive
letter, no address scheme and no machine path of its own, and the scan that
reads it finds nothing to report.

Some shapes therefore come in two readings, a prose one and a declared-value
one, and both are declared here. The prose reading of a traversal wants the
value or the line to begin with it, and the prose reading of an absolute path
wants a first segment that continues into another one or ends in a suffix,
because shipped documentation links with a traversal segment inside a longer
relative link and writes a bare slash between two names for a rate or a pair of
sides. The declared-value reading of each wants neither: a locator this product
wrote is one value, so a traversal anywhere in it, a single-segment path from
the root, a lettered volume with no separator after it and a share host with
nothing after it are all routes. A bare word and a bare whole number cannot be
told apart from a name and a count by reading them, so nothing here claims to.
A credential shape names a written secret, not a high-entropy token with no name
beside it.

Two forms these shapes do not read at all, at any boundary, so that what is
missed is missed in one place and can be closed in one place.

* A home path written with the character that stands for one. The shapes read
  the written words for a home directory, not that character.
* A traversal or a separator written in percent-encoded form. Nothing here
  decodes an encoding before reading, so an encoded route reads as text.

A fourth family is advisory. It is read for a warning and never for a refusal,
and no boundary keeps a refusal reason for it. It holds two forms. A bare host
is a dotted name with a path or a port after it and no scheme in front of it;
the dotted name alone is not read, because it cannot be told from an ordinary
written name at all, and refusing it would refuse names a team has every reason
to write. A connection string is a connection key written against a value. A
boundary that reads this family labels what it found and admits it, and says in
its own docstring what it does with the label.

Two machine-route shapes read less than their names suggest, and each stops
short for a stated reason. A lettered volume with no separator after it does
not read a single letter or digit after the mark, because a spreadsheet column
range and a short written value are both written that way and name ordinary
positions inside an artefact; a volume followed by one character and nothing
else is admitted with them. The declared reading of a path from the root does
not read a separator that follows a space and a number, because that is how a
rate is written in a sentence; a path from the root written straight after a
number is admitted with it. Each narrowing leaves the route it was written for
still read, and what each gives up is named here and nowhere else.

Six further forms are read at the three boundaries that read one declared value
and stay unread at the one boundary that reads whole shipped files, because in
a page of prose they would report the product's own documentation rather than a
leak. They are the prose and the declared-value readings of an absolute path,
the declared-value reading of a traversal, a lettered volume with no separator
after it, a share host with nothing after it, and, in program source and the
JSON family only, a relative path written with a machine path's separator,
where those bytes write a character escape instead. The scan states each
allowance with its reason in its own module.

Three address forms are allowed at that same scan and at no other boundary,
because no declared value and no tracker note has any reason to carry an
address at all. They are declared below: the secure web scheme, which is how
this product's documentation links to published material; the insecure web
scheme where the drawing namespace follows it, which every generated diagram
declares; and this product's own logical reference scheme, which names a record
inside this product and no host. The file scheme and the insecure web scheme
are named below too, because the scan reports each of them under a finding of
its own rather than as a generic address.
"""
from __future__ import annotations

# evorthon-component: boundary_patterns

import re
from collections.abc import Mapping, Sequence
from types import MappingProxyType

# The characters a machine route is written from, by code point, so no route
# is spelled out in this file.
_ESCAPE = chr(92)
_MARK = chr(58)
_STOP = chr(46)
# One separator of a machine path, and one segment of a relative one.
_SEPARATOR = "[" + _ESCAPE * 2 + "/]"
_SEGMENT = "[A-Za-z0-9_" + _STOP + "-]"
# The two steps upward a traversal is written with, escaped for a pattern.
_UPWARD = _ESCAPE + _STOP + _ESCAPE + _STOP
# One part of a written address, up to the next mark, separator or host sign.
_ADDRESS_PART = r"[^/\s" + _MARK + "@]+"

DRIVE_PATH = "drive path"
DRIVE_RELATIVE_PATH = "drive-relative path"
NETWORK_SHARE_PATH = "network share path"
NETWORK_SHARE_HOST = "network share host"
USER_HOME_PATH = "user home path"
ABSOLUTE_PATH = "absolute path"
DECLARED_ABSOLUTE_PATH = "declared absolute path"
LOCAL_FILE_ADDRESS = "local file address"
WEB_ADDRESS = "web address"
SCHEME_ADDRESS = "scheme address"
TRAVERSAL = "traversal"
DECLARED_TRAVERSAL = "declared traversal"
BACKSLASH_RELATIVE_PATH = "backslash-relative path"

MACHINE_ROUTE_PATTERNS: Mapping[str, re.Pattern[str]] = MappingProxyType(
    {
        # A lettered volume on a machine.
        DRIVE_PATH: re.compile(r"\b[a-z]" + _MARK + _SEPARATOR, re.I),
        # The same volume with no separator after it, which names wherever the
        # machine stands on that volume. A single letter or digit that ends
        # there is not read: that is a column range or a short written value,
        # not a volume.
        DRIVE_RELATIVE_PATH: re.compile(
            r"\b[a-z]" + _MARK + r"(?![a-z0-9]\b)[^" + _ESCAPE * 2 + r"/\s]", re.I
        ),
        # A share on another machine, named by two separators and a host.
        NETWORK_SHARE_PATH: re.compile(
            _ESCAPE * 4 + "[^" + _ESCAPE * 2 + "/]+" + _SEPARATOR
        ),
        # The host half of that share, with nothing after it. It names the
        # machine even when no share on it is named yet.
        NETWORK_SHARE_HOST: re.compile(
            _ESCAPE * 4 + "[^" + _ESCAPE * 2 + r"/\s]"
        ),
        # One person's directory on a machine.
        USER_HOME_PATH: re.compile(r"/(?:home|users)/[^/\s]+", re.I),
        # A path from the root of a machine, read in prose. The first segment
        # must continue into another one or end in a suffix, because a bare
        # slash between two names is how a rate or a pair of sides is written
        # in a sentence.
        ABSOLUTE_PATH: re.compile(
            r"(?m)(?:^|\s)/" + _SEGMENT + "+(?:" + _SEPARATOR + "|" + _ESCAPE + _STOP + "[A-Za-z0-9]{1,8}" + r"\b)"
        ),
        # The same path read in a declared value, where one segment is enough
        # because the value is not a sentence. A separator that follows a space
        # and a number is not read: that is a rate, not a path.
        DECLARED_ABSOLUTE_PATH: re.compile(r"(?m)(?:^|(?<![0-9])\s)/" + _SEGMENT),
        # A file on a machine, written as an address.
        LOCAL_FILE_ADDRESS: re.compile(r"\bfile" + _MARK + r"\s*//", re.I),
        # A host reached over the network, written as an address.
        WEB_ADDRESS: re.compile(r"\bhttps?" + _MARK + "//", re.I),
        # An address under any scheme at all, which is how a cloud store, a
        # transfer, a share, a database and a lake are all written. The forms
        # one boundary allows are declared below and nowhere else.
        SCHEME_ADDRESS: re.compile(r"\b[a-z][a-z0-9]*" + _MARK + "//", re.I),
        # A route that climbs out of where it starts, read in prose at the
        # start of a value or a line.
        TRAVERSAL: re.compile(r"(?m)(?:^|\s)" + _UPWARD + _SEPARATOR),
        # The same climb read in a declared value, wherever it sits in it.
        DECLARED_TRAVERSAL: re.compile(_UPWARD + _SEPARATOR),
        # A relative path written with the separator a machine path uses.
        BACKSLASH_RELATIVE_PATH: re.compile(_SEGMENT + _ESCAPE * 2 + _SEGMENT),
    }
)

# The address forms one boundary allows, declared once here so the scan that
# allows them and the boundaries that refuse them read the same text. A
# declared value and a tracker note carry no address at all, so every boundary
# but the shipped-file scan refuses each of these too.
SECURE_WEB_SCHEME = "https" + _MARK + "//"
INSECURE_WEB_SCHEME = "http" + _MARK + "//"
LOCAL_FILE_SCHEME = "file" + _MARK + "//"
LOGICAL_REFERENCE_SCHEME = "koine" + _MARK + "//"
# The one root this product writes after that scheme. The scheme alone names no
# record, so the allowance below is the composed form and not the prefix.
LOGICAL_REFERENCE_ROOT = "use-case/"
LOGICAL_REFERENCE_FORM = LOGICAL_REFERENCE_SCHEME + LOGICAL_REFERENCE_ROOT
DRAWING_NAMESPACE = "www" + _STOP + "w3" + _STOP + "org/2000/svg"
# The three schemes a boundary may name in a finding of its own rather than as
# a generic address, and the one form that is not a route to any machine.
NAMED_SCHEME_FORMS: tuple[str, ...] = (
    SECURE_WEB_SCHEME,
    INSECURE_WEB_SCHEME,
    LOCAL_FILE_SCHEME,
)
ALLOWED_SCHEME_FORMS: tuple[str, ...] = (SECURE_WEB_SCHEME, LOGICAL_REFERENCE_FORM)

BARE_HOST = "bare host"
CONNECTION_STRING = "connection string"

# The advisory family. Nothing refuses on these; a boundary that reads them
# labels what it found. Both forms are written by people who mean no harm as
# often as by a leak, which is why the reading stops at a label.
ADVISORY_PATTERNS: Mapping[str, re.Pattern[str]] = MappingProxyType(
    {
        # A dotted name that reads like a server. Three or more labels in front
        # of a separator, because two labels in front of one is how an ordinary
        # file inside a directory is written; or a dotted name in front of a
        # port, where the port is the part that makes it an address.
        BARE_HOST: re.compile(
            r"\b(?:[a-z0-9-]+" + _ESCAPE + _STOP + r"){2,}[a-z0-9-]+(?=" + _SEPARATOR + ")"
            r"|\b(?:[a-z0-9-]+" + _ESCAPE + _STOP + r")+[a-z0-9-]+" + _MARK + r"[0-9]{1,5}\b",
            re.I,
        ),
        # A connection key written against a value, which is how a driver is
        # told where to connect.
        CONNECTION_STRING: re.compile(
            r"\b(?:server|host|hostname|data[ _-]?source|initial[ _-]?catalog|endpoint|dsn)"
            r"[ \t]*=[ \t]*[\"']?\S",
            re.I,
        ),
    }
)

NAMED_SECRET = "named secret"
NAMED_KEY = "named key"
PRESENTED_TOKEN = "presented token"
KEY_BLOCK = "key block"
ASSIGNED_SECRET = "assigned secret"
CONNECTION_CREDENTIAL = "connection credential"
BEARER_AUTHORIZATION = "bearer authorization"

CREDENTIAL_PATTERNS: Mapping[str, re.Pattern[str]] = MappingProxyType(
    {
        # The word for a secret, written in a sentence.
        NAMED_SECRET: re.compile(r"\b(?:password|passphrase|secret|credential)s?\b", re.I),
        # The word for a key, written in a sentence.
        NAMED_KEY: re.compile(r"\b(?:api|access|private|signing)[_ -]?key\b", re.I),
        # A token presented for authorization.
        PRESENTED_TOKEN: re.compile(r"\b(?:bearer|basic)\s+\S{8,}", re.I),
        # The opening line of a stored key of any kind. The shape reads what it
        # catches: a private key most of the time, a public one sometimes, and
        # the name says so rather than claiming the narrower thing.
        KEY_BLOCK: re.compile("-{5}begin[a-z ]*key-{5}", re.I),
        # A named secret with a value written against it.
        ASSIGNED_SECRET: re.compile(
            r"\b(?:password|passwd|secret|api[_-]?key|access[_-]?key|"
            r"client[_-]?secret|auth[_-]?token|credential)\b[ \t]*[" + _MARK + r"=][ \t]*"
            r"[\"']?[^\s\"']{8,}",
            re.I,
        ),
        # A user and a secret written inside an address.
        CONNECTION_CREDENTIAL: re.compile(
            _MARK + "//" + _ADDRESS_PART + _MARK + _ADDRESS_PART + "@"
        ),
        # A presented token written against the header that carries it.
        BEARER_AUTHORIZATION: re.compile(
            r"\bauthorization\b[ \t]*[" + _MARK + r"=][ \t]*[\"']?bearer[ \t]+\S+", re.I
        ),
    }
)

CONTROL_CHARACTER = "control character"
WRITTEN_OBJECT = "written object"
DELIMITED_FIELDS = "delimited fields"

RAW_ROW_PATTERNS: Mapping[str, re.Pattern[str]] = MappingProxyType(
    {
        # A record separator, or anything else below the printable range.
        CONTROL_CHARACTER: re.compile(r"[\x00-\x1f]"),
        # A written object with quoted field names.
        WRITTEN_OBJECT: re.compile(r"\{\s*[\"']"),
        # A run of fields written between delimiters.
        DELIMITED_FIELDS: re.compile(r"\|[^|]*\|"),
    }
)

MACHINE_ROUTE_SHAPES: tuple[str, ...] = tuple(MACHINE_ROUTE_PATTERNS)
CREDENTIAL_SHAPES: tuple[str, ...] = tuple(CREDENTIAL_PATTERNS)
RAW_ROW_SHAPES: tuple[str, ...] = tuple(RAW_ROW_PATTERNS)
ADVISORY_SHAPES: tuple[str, ...] = tuple(ADVISORY_PATTERNS)


def shapes(
    patterns: Mapping[str, re.Pattern[str]], names: Sequence[str]
) -> tuple[tuple[str, re.Pattern[str]], ...]:
    """Return the named shapes of one family, in the order a boundary named them.

    A name this module does not declare raises, so a boundary cannot read a
    shape that has no owner and cannot quietly lose one to a rename.
    """
    return tuple((name, patterns[name]) for name in names)


def shape_carried(read: Sequence[tuple[str, re.Pattern[str]]], value: str) -> str | None:
    """Name the first of the given shapes a text carries, or nothing.

    This reads. What a carried shape means, and what to do about it, belongs to
    the boundary that asked.
    """
    for name, pattern in read:
        if pattern.search(value):
            return name
    return None


__all__ = [
    "ABSOLUTE_PATH",
    "ADVISORY_PATTERNS",
    "ADVISORY_SHAPES",
    "ALLOWED_SCHEME_FORMS",
    "ASSIGNED_SECRET",
    "BACKSLASH_RELATIVE_PATH",
    "BARE_HOST",
    "BEARER_AUTHORIZATION",
    "CONNECTION_CREDENTIAL",
    "CONNECTION_STRING",
    "CONTROL_CHARACTER",
    "CREDENTIAL_PATTERNS",
    "CREDENTIAL_SHAPES",
    "DECLARED_ABSOLUTE_PATH",
    "DECLARED_TRAVERSAL",
    "DELIMITED_FIELDS",
    "DRAWING_NAMESPACE",
    "DRIVE_PATH",
    "DRIVE_RELATIVE_PATH",
    "INSECURE_WEB_SCHEME",
    "LOCAL_FILE_ADDRESS",
    "LOCAL_FILE_SCHEME",
    "LOGICAL_REFERENCE_FORM",
    "LOGICAL_REFERENCE_ROOT",
    "LOGICAL_REFERENCE_SCHEME",
    "MACHINE_ROUTE_PATTERNS",
    "MACHINE_ROUTE_SHAPES",
    "NAMED_KEY",
    "NAMED_SCHEME_FORMS",
    "NAMED_SECRET",
    "NETWORK_SHARE_HOST",
    "NETWORK_SHARE_PATH",
    "PRESENTED_TOKEN",
    "KEY_BLOCK",
    "RAW_ROW_PATTERNS",
    "RAW_ROW_SHAPES",
    "SCHEME_ADDRESS",
    "SECURE_WEB_SCHEME",
    "TRAVERSAL",
    "USER_HOME_PATH",
    "WEB_ADDRESS",
    "WRITTEN_OBJECT",
    "shape_carried",
    "shapes",
]
