"""Canonical serialisation and hashing for scope contracts and evidence.

The digest is evidence. Its failure mode is not a crash but a value that looks
right and is not, so every rule ADR-0004 pins is implemented explicitly here
rather than inherited from a serialiser's defaults.

The pipeline is NFC normalisation, then RFC 8785 canonicalisation, then SHA-256,
then lowercase hex. The normalisation step is this framework's addition: RFC 8785
deliberately does not normalise, and requires input to be normalised already. A
scope contract can be authored on macOS, where a filesystem-sourced string may
arrive decomposed, and compared on Linux, where the same text is composed. Under
plain JCS those two produce different digests for the same scope, so the
normalisation is what makes FR-19's cross-platform claim true.

Scope of the implementation. Documents reaching this module are validated
against closed schemas that admit only strings, integers, booleans, null, arrays
and objects. The one genuinely difficult part of RFC 8785, ECMAScript number
formatting for non-integral doubles, is therefore outside the input domain. That
part is not implemented, and a value needing it is refused rather than
approximated. A canonicaliser that guessed would produce a digest that is stable,
reproducible, and wrong, which is worse than one that stops.
"""

import hashlib
import json
import unicodedata

# ECMAScript numbers are IEEE 754 doubles. Beyond this magnitude an integer is no
# longer exactly representable, so a conforming implementation on a JavaScript
# runtime would serialise a different value than Python's arbitrary-precision int
# does. The digests would disagree while both sides believed they agreed.
MAX_SAFE_INTEGER = 2**53 - 1

# RFC 8785 section 3.2.2.2: the two-character escapes, and \u00xx for the
# remaining control characters. Everything else is emitted as itself, so the
# output carries literal UTF-8 rather than \u escapes.
_SHORT_ESCAPES = {
    0x08: "\\b",
    0x09: "\\t",
    0x0A: "\\n",
    0x0C: "\\f",
    0x0D: "\\r",
    0x22: '\\"',
    0x5C: "\\\\",
}


class CanonicalisationError(Exception):
    """A document cannot be canonicalised under the pinned rules."""


def _sort_key(name):
    """Order object members by UTF-16 code unit, as RFC 8785 section 3.2.3 requires.

    Python orders strings by code point, which agrees with UTF-16 order across
    the BMP and disagrees above it: a supplementary character encodes to a
    surrogate pair beginning at U+D800, so it sorts *below* U+E000 through
    U+FFFF under UTF-16 and above them under code point order. Comparing
    big-endian UTF-16 bytes reproduces code unit order exactly.
    """
    return name.encode("utf-16-be")


def _escape(text):
    out = ["\""]
    for character in text:
        code = ord(character)
        escape = _SHORT_ESCAPES.get(code)
        if escape is not None:
            out.append(escape)
        elif code < 0x20:
            out.append("\\u%04x" % code)
        else:
            out.append(character)
    out.append("\"")
    return "".join(out)


def _number(value, pointer):
    """Serialise a number, or refuse if it falls outside the proven domain."""
    if isinstance(value, bool):
        raise AssertionError("booleans are handled before numbers")

    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise CanonicalisationError(
                "%s: NaN and Infinity have no JSON representation, so no digest "
                "can be computed over this document." % pointer
            )
        if not value.is_integer():
            raise CanonicalisationError(
                "%s: a non-integral number needs ECMAScript number formatting, "
                "which this canonicaliser does not implement. The schemas admit "
                "only integers, so reaching this means either the schema widened "
                "or validation was skipped. Refusing rather than emitting a "
                "digest that would be stable and wrong." % pointer
            )
        value = int(value)

    if abs(value) > MAX_SAFE_INTEGER:
        raise CanonicalisationError(
            "%s: integer magnitude exceeds 2^53-1, beyond which an IEEE 754 "
            "double cannot hold it exactly. A conforming implementation on a "
            "JavaScript runtime would serialise a different value, so the "
            "digests would disagree while both sides believed they agreed."
            % pointer
        )
    return str(int(value))


def _serialise(value, pointer, out):
    if value is None:
        out.append("null")
    elif value is True:
        out.append("true")
    elif value is False:
        out.append("false")
    elif isinstance(value, str):
        out.append(_escape(value))
    elif isinstance(value, (int, float)):
        out.append(_number(value, pointer))
    elif isinstance(value, list):
        out.append("[")
        for index, item in enumerate(value):
            if index:
                out.append(",")
            _serialise(item, "%s/%d" % (pointer, index), out)
        out.append("]")
    elif isinstance(value, dict):
        out.append("{")
        for index, name in enumerate(sorted(value, key=_sort_key)):
            if index:
                out.append(",")
            out.append(_escape(name))
            out.append(":")
            _serialise(value[name], "%s/%s" % (pointer, name), out)
        out.append("}")
    else:
        raise CanonicalisationError(
            "%s: %s has no JSON representation. Refusing rather than coercing it "
            "into one." % (pointer, type(value).__name__)
        )


def normalise(value):
    """Apply NFC to every string in the document, keys included.

    Keys are normalised too, which can collide two members that were distinct
    before normalisation. That collision is reported rather than resolved: one
    of the two values would otherwise vanish from the digest silently.
    """
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [normalise(item) for item in value]
    if isinstance(value, dict):
        result = {}
        for name, item in value.items():
            composed = unicodedata.normalize("NFC", name)
            if composed in result:
                raise CanonicalisationError(
                    "two members normalise to the same key %r under NFC. Keeping "
                    "either one would drop the other from the digest without "
                    "anyone noticing." % composed
                )
            result[composed] = normalise(item)
        return result
    return value


def canonicalise(document):
    """Return the RFC 8785 canonical form of an NFC-normalised document, as bytes.

    The result carries no trailing newline: the digest input is the canonical
    byte sequence itself, as ADR-0004 pins.
    """
    out = []
    _serialise(normalise(document), "", out)
    return "".join(out).encode("utf-8")


def _reject_duplicate_keys(pairs):
    """Refuse a JSON text that names the same member twice.

    Python's parser keeps the last occurrence. Which one survives would decide
    the digest, so a document that never says what it means must not be given a
    confident answer.
    """
    seen = {}
    for name, value in pairs:
        if name in seen:
            raise CanonicalisationError(
                "the member %r appears more than once. Which occurrence wins "
                "would silently decide the digest." % name
            )
        seen[name] = value
    return seen


def load(text):
    """Parse a JSON text under the rules the digest depends on."""
    try:
        return json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise CanonicalisationError("the document is not valid JSON: %s" % exc.msg)


def text_digest(text):
    """Return the lowercase hex SHA-256 over an NFC-normalised string.

    For a value that is text rather than a document: a catalogued query, for
    instance. The canonicalisation rules above apply to JSON structure and have
    nothing to say about a bare string, but the normalisation step does, and
    for the same reason. A query authored on one platform and verified on
    another must not fail integrity because the two spellings of the same
    characters differ.

    Deliberately not `digest(text)`. Passing a string to the document digest
    would canonicalise it as a JSON string, quotes and escapes included, so the
    two functions would disagree about what was hashed while both returning a
    plausible value.
    """
    if not isinstance(text, str):
        raise CanonicalisationError(
            "a text digest is defined over a string; %s was supplied."
            % type(text).__name__
        )
    return hashlib.sha256(
        unicodedata.normalize("NFC", text).encode("utf-8")
    ).hexdigest()


def digest(document, hash_field=None):
    """Return the lowercase hex SHA-256 over the canonical form.

    `hash_field` is removed from the top level first. A document that carried its
    own digest while it was being computed could never reproduce it, so the
    exclusion is part of the definition rather than a convenience.
    """
    if hash_field is not None:
        if not isinstance(document, dict):
            raise CanonicalisationError(
                "a hash field can only be excluded from an object."
            )
        document = {k: v for k, v in document.items() if k != hash_field}
    return hashlib.sha256(canonicalise(document)).hexdigest()
