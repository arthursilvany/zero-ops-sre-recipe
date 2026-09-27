"""Canonicalisation and hashing produce the same bytes everywhere, or stop.

The digest is evidence. Its dangerous failure is not an exception but a value
that looks right and is not, so the expected digests below are written as
literal constants. A test that recomputes the expected value with the code under
test proves only that the code agrees with itself, and would pass on both
runners while they disagreed with each other. These constants are what makes
NEG-J a real cross-platform check: the suite runs on ubuntu-latest and
windows-latest, and both must reproduce these exact strings.

The conformance cases below were authored against RFC 8785 section 3.2 rather
than copied from the reference implementation's test data, whose licence is
unstated.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from zeroops import canonical

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def canon(document):
    return canonical.canonicalise(document).decode("utf-8")


class SerialisationFollowsTheSpec(unittest.TestCase):
    def test_members_are_sorted_and_whitespace_is_removed(self):
        self.assertEqual(
            '[56,{"1":[],"10":null,"d":true}]',
            canon([56, {"d": True, "10": None, "1": []}]),
        )

    def test_sorting_is_by_code_unit_not_by_locale(self):
        # RFC 8785 section 3.2.3. French collation would order these differently;
        # canonicalisation must ignore locale entirely.
        self.assertEqual(
            '{"peach":1,"p\u00e9ch\u00e9":2,"p\u00eache":3,"sin":4}',
            canon({"peach": 1, "p\u00eache": 3, "sin": 4, "p\u00e9ch\u00e9": 2}),
        )

    def test_sorting_is_by_utf16_code_unit_not_by_code_point(self):
        # The distinguishing case. U+1F602 is supplementary, so in UTF-16 it
        # begins with the surrogate U+D83D and sorts *below* U+FFFD. Ordering by
        # code point puts it above. Both orders agree across the whole BMP, so
        # only a supplementary character can tell the two apart.
        emoji, bmp = "\U0001F602", "\uFFFD"
        self.assertLess(bmp, emoji, "code point order, for contrast")
        self.assertEqual(
            '{"%s":1,"%s":2}' % (emoji, bmp),
            canon({bmp: 2, emoji: 1}),
            "members were ordered by code point instead of UTF-16 code unit",
        )

    def test_empty_key_sorts_first(self):
        self.assertEqual('{"":1,"a":2}', canon({"a": 2, "": 1}))

    def test_short_escapes_are_used_where_the_spec_defines_them(self):
        self.assertEqual(
            '"\\b\\t\\n\\f\\r\\"\\\\"', canon("\b\t\n\f\r\"\\")
        )

    def test_other_control_characters_use_lowercase_four_digit_escapes(self):
        self.assertEqual('"\\u0000\\u001f"', canon("\u0000\u001f"))

    def test_non_ascii_is_emitted_literally_not_escaped(self):
        # JCS output is UTF-8. Escaping here would still parse, but would be a
        # different byte sequence and therefore a different digest.
        self.assertEqual('"\u20ac"', canon("\u20ac"))

    def test_forward_slash_is_not_escaped(self):
        self.assertEqual('"</script>"', canon("</script>"))

    def test_structures_nest_without_whitespace(self):
        self.assertEqual(
            '{"":"empty","1":{"\\n":56,"f":{"F":5,"f":"hi"}},"10":{},'
            '"111":[{"E":"no","e":"yes"}],"A":{},"a":{}}',
            canon(
                {
                    "1": {"f": {"f": "hi", "F": 5}, "\n": 56.0},
                    "10": {},
                    "": "empty",
                    "a": {},
                    "111": [{"e": "yes", "E": "no"}],
                    "A": {},
                }
            ),
        )

    def test_there_is_no_trailing_newline(self):
        # ADR-0004 pins the digest input as the canonical byte sequence itself.
        # A trailing newline would change every digest in the system.
        self.assertFalse(canonical.canonicalise({"a": 1}).endswith(b"\n"))

    def test_output_is_utf8_bytes(self):
        self.assertIsInstance(canonical.canonicalise({"a": "\u20ac"}), bytes)
        self.assertEqual(b'{"a":"\xe2\x82\xac"}', canonical.canonicalise({"a": "\u20ac"}))


class NumbersStayInsideTheProvenDomain(unittest.TestCase):
    def test_integers_are_emitted_plainly(self):
        self.assertEqual("[0,1,-1,42]", canon([0, 1, -1, 42]))

    def test_an_integral_float_is_emitted_as_an_integer(self):
        # JSON Schema accepts 56.0 as an integer, so a valid document can carry
        # one. ECMAScript renders it "56", and so must this.
        self.assertEqual("56", canon(56.0))

    def test_negative_zero_is_emitted_as_zero(self):
        # RFC 8785 appendix B, "Minus zero", gives the JSON representation 0.
        # Emitting "-0" would be a plausible-looking digest divergence against
        # any conforming implementation.
        self.assertEqual("0", canon(-0.0))

    def test_booleans_are_not_treated_as_numbers(self):
        # bool is a subclass of int in Python, so an ordering mistake here emits
        # 1 and 0 where true and false belong.
        self.assertEqual("[true,false]", canon([True, False]))

    def test_the_largest_exact_integer_is_accepted(self):
        self.assertEqual("9007199254740991", canon(canonical.MAX_SAFE_INTEGER))

    def test_an_integer_beyond_exact_double_range_is_refused(self):
        # A JavaScript implementation would serialise a different value here.
        # Both sides would believe they agreed.
        with self.assertRaises(canonical.CanonicalisationError):
            canonical.canonicalise(canonical.MAX_SAFE_INTEGER + 1)
        with self.assertRaises(canonical.CanonicalisationError):
            canonical.canonicalise(-canonical.MAX_SAFE_INTEGER - 1)

    def test_a_fractional_number_is_refused_rather_than_approximated(self):
        with self.assertRaises(canonical.CanonicalisationError) as caught:
            canonical.canonicalise({"ratio": 0.1})
        self.assertIn("/ratio", str(caught.exception))

    def test_nan_and_infinity_are_refused(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(canonical.CanonicalisationError):
                canonical.canonicalise([value])

    def test_a_type_with_no_json_form_is_refused_not_coerced(self):
        with self.assertRaises(canonical.CanonicalisationError):
            canonical.canonicalise({"when": object()})

    def test_the_refusal_names_the_location(self):
        with self.assertRaises(canonical.CanonicalisationError) as caught:
            canonical.canonicalise({"a": [{"b": 1.5}]})
        self.assertIn("/a/0/b", str(caught.exception))


class NormalisationMakesTheCrossPlatformClaimTrue(unittest.TestCase):
    def test_composed_and_decomposed_text_hash_identically(self):
        # The NEG-J premise. A scope contract authored where text arrives
        # decomposed must match one authored where it arrives composed.
        composed = {"name": "\u00c5ngstr\u00f6m"}
        decomposed = {"name": "A\u030angstro\u0308m"}
        self.assertNotEqual(composed["name"], decomposed["name"])
        self.assertEqual(canonical.digest(composed), canonical.digest(decomposed))

    def test_keys_are_normalised_as_well_as_values(self):
        self.assertEqual(
            canonical.digest({"\u00e9": 1}), canonical.digest({"e\u0301": 1})
        )

    def test_normalisation_is_nfc_not_nfkc(self):
        # NFKC would fold these together and silently erase a distinction the
        # author made. Canonical equivalence is the contract; compatibility
        # equivalence is not.
        self.assertNotEqual(canonical.digest({"a": "\uFF21"}), canonical.digest({"a": "A"}))

    def test_keys_colliding_under_normalisation_are_reported(self):
        # Keeping either one would drop the other from the digest silently.
        with self.assertRaises(canonical.CanonicalisationError):
            canonical.normalise({"\u00e9": 1, "e\u0301": 2})

    def test_normalisation_reaches_nested_values(self):
        self.assertEqual(
            canonical.digest({"a": [{"b": "\u00e9"}]}),
            canonical.digest({"a": [{"b": "e\u0301"}]}),
        )


class ParsingRefusesDocumentsThatDoNotSayWhatTheyMean(unittest.TestCase):
    def test_a_duplicated_member_is_refused(self):
        # Python keeps the last occurrence. Which one survives would decide the
        # digest, so the document must not be given a confident answer.
        with self.assertRaises(canonical.CanonicalisationError):
            canonical.load('{"a":1,"a":2}')

    def test_a_duplicate_nested_deeper_is_refused(self):
        with self.assertRaises(canonical.CanonicalisationError):
            canonical.load('{"outer":{"a":1,"a":2}}')

    def test_malformed_json_is_reported_as_such(self):
        with self.assertRaises(canonical.CanonicalisationError):
            canonical.load("{not json")

    def test_a_valid_document_round_trips(self):
        self.assertEqual({"a": [1, 2]}, canonical.load('{"a":[1,2]}'))


class TheDigestIsDefinedNotIncidental(unittest.TestCase):
    def test_digest_is_lowercase_hex_sha256(self):
        value = canonical.digest({"a": 1})
        self.assertEqual(64, len(value))
        self.assertEqual(value.lower(), value)
        self.assertTrue(all(c in "0123456789abcdef" for c in value))

    def test_digest_is_sha256_over_the_canonical_bytes(self):
        document = {"b": 2, "a": 1}
        self.assertEqual(
            hashlib.sha256(canonical.canonicalise(document)).hexdigest(),
            canonical.digest(document),
        )

    def test_member_order_in_the_source_does_not_change_the_digest(self):
        self.assertEqual(
            canonical.digest({"a": 1, "b": 2}), canonical.digest({"b": 2, "a": 1})
        )

    def test_the_hash_field_is_excluded_from_its_own_computation(self):
        # A document carrying its own digest could never reproduce it otherwise.
        without = {"scope": "x"}
        with_hash = {"scope": "x", "hash": "whatever was there before"}
        self.assertEqual(
            canonical.digest(without), canonical.digest(with_hash, hash_field="hash")
        )

    def test_the_recorded_digest_reproduces_after_it_is_written_back(self):
        document = {"scope": "x", "hash": None}
        recorded = canonical.digest(document, hash_field="hash")
        document["hash"] = recorded
        self.assertEqual(recorded, canonical.digest(document, hash_field="hash"))

    def test_excluding_a_field_only_applies_at_the_top_level(self):
        # A nested member of the same name is part of the scope being attested
        # and must not silently vanish from the digest.
        self.assertNotEqual(
            canonical.digest({"inner": {"hash": "a"}}, hash_field="hash"),
            canonical.digest({"inner": {}}, hash_field="hash"),
        )

    def test_excluding_from_a_non_object_is_refused(self):
        with self.assertRaises(canonical.CanonicalisationError):
            canonical.digest([1, 2], hash_field="hash")

    def test_a_changed_value_changes_the_digest(self):
        self.assertNotEqual(canonical.digest({"a": 1}), canonical.digest({"a": 2}))


class CrossPlatformDeterminism(unittest.TestCase):
    """NEG-J. These constants must hold identically on every runner.

    They are written literally on purpose. Recomputing them with the code under
    test would let both runners agree with themselves while disagreeing with
    each other, which is the exact failure this check exists to catch.
    """

    VECTORS = [
        (
            {},
            b"{}",
            "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
        ),
        (
            [],
            b"[]",
            "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        ),
        (
            {"a": 1},
            b'{"a":1}',
            "015abd7f5cc57a2dd94b7590f04ad8084273905ee33ec5cebeae62276a97f862",
        ),
        (
            {
                "schemaVersion": "1.0.0",
                "workloads": ["aks", "app-service"],
                "minimumApprovers": 2,
                "readOnly": True,
                "note": None,
            },
            b'{"minimumApprovers":2,"note":null,"readOnly":true,'
            b'"schemaVersion":"1.0.0","workloads":["aks","app-service"]}',
            "f797db258d276a7a73e39dbad08b67758c87dfd723964ceecd4e975de816b2aa",
        ),
        (
            # UTF-8 output and NFC together, which is where a platform
            # difference would actually surface.
            {"sign": "\u20ac", "owner": "A\u030angstro\u0308m"},
            b'{"owner":"\xc3\x85ngstr\xc3\xb6m","sign":"\xe2\x82\xac"}',
            "bff2c720aaa61840a13d075f6970db5f74c1a514772509b4a7d040d47df6add0",
        ),
        (
            # If a platform translated newlines on the way in, this moves.
            {"body": "a\nb"},
            b'{"body":"a\\nb"}',
            "000543480df7b315fa5be5322b2aef0ca6453c3efe070c94cab81c3fa2d4e825",
        ),
    ]

    def test_every_vector_produces_its_recorded_bytes_and_digest(self):
        for document, expected_bytes, expected_digest in self.VECTORS:
            with self.subTest(document=document):
                self.assertEqual(expected_bytes, canonical.canonicalise(document))
                self.assertEqual(expected_digest, canonical.digest(document))

    def test_the_recorded_digests_are_sha256_of_the_recorded_bytes(self):
        # Checks the table against hashlib directly, so a transcription error in
        # the constants above cannot pass as agreement.
        for _document, expected_bytes, expected_digest in self.VECTORS:
            with self.subTest(expected_bytes=expected_bytes):
                self.assertEqual(
                    hashlib.sha256(expected_bytes).hexdigest(), expected_digest
                )


class ShippedScopeContractsHashIdentically(unittest.TestCase):
    """NEG-J, FR-19 and FR-23, acceptance criterion 8 of US-1.

    The vectors above are synthetic documents. The criterion is about a real
    scope contract, and the two differ in the ways that actually break
    cross-platform reproducibility: a shipped file is read from disk, so it
    carries whatever line endings git checked out and whatever encoding the
    editor wrote.

    Pinning the digest here is what makes the CI matrix load-bearing. The
    suite runs on windows-latest and ubuntu-latest; if a CRLF checkout or a
    BOM changed the bytes, one leg would produce a different digest and this
    constant would fail on that leg alone. Computing the digest on both
    runners and comparing it to itself would agree everywhere and prove
    nothing.
    """

    EXPECTED = {
        os.path.join("examples", "minimal", "scope-contract.json"):
            "9d551f1d10fb5fed5058511185585ffe28723efd756a0a37da12ceb3258c8e9a",
        os.path.join("examples", "two-environments", "scope-contract.json"):
            "b95af70c23e6ee17c842442963af993b3ba73e5ac92b932663cc39449a9862f4",
    }

    def load(self, relative):
        with open(os.path.join(REPO_ROOT, relative), "r", encoding="utf-8") as handle:
            return json.load(handle)

    def test_every_shipped_scope_contract_has_a_pinned_digest(self):
        """A count guard in the form that matters here: a contract added later
        without a pin would make this class quietly cover less than it claims."""
        found = sorted(
            os.path.join("examples", name, "scope-contract.json")
            for name in sorted(os.listdir(os.path.join(REPO_ROOT, "examples")))
            if os.path.isdir(os.path.join(REPO_ROOT, "examples", name))
        )
        self.assertEqual(sorted(self.EXPECTED), found)

    def test_each_digest_matches_the_pin(self):
        for relative, expected in sorted(self.EXPECTED.items()):
            with self.subTest(path=relative):
                self.assertEqual(expected, canonical.digest(self.load(relative)))

    def test_the_two_contracts_do_not_share_a_digest(self):
        """The control case. Two different documents hashing alike would mean
        the digest was not a function of the content, and every equality above
        would still pass."""
        self.assertEqual(2, len(set(self.EXPECTED.values())))

    def test_each_digest_is_lowercase_hex(self):
        for relative, expected in sorted(self.EXPECTED.items()):
            with self.subTest(path=relative):
                self.assertRegex(expected, r"\A[0-9a-f]{64}\Z")


class TheCommandLineSurface(unittest.TestCase):
    def run_cli(self, *args, stdin=None):
        return subprocess.run(
            [sys.executable, "-m", "zeroops"] + list(args),
            capture_output=True,
            cwd=REPO_ROOT,
            env=dict(os.environ, PYTHONPATH="tools"),
        )

    def write(self, name, text):
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory, True)
        path = os.path.join(directory, name)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        return path

    def test_hash_prints_the_digest_and_exits_zero(self):
        path = self.write("doc.json", '{"a":1}')
        result = self.run_cli("hash", path)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(canonical.digest({"a": 1}), result.stdout.decode().strip())

    def test_hash_honours_the_excluded_field(self):
        path = self.write("doc.json", '{"a":1,"hash":"stale"}')
        result = self.run_cli("hash", path, "--hash-field", "hash")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(canonical.digest({"a": 1}), result.stdout.decode().strip())

    def test_canonical_output_has_no_trailing_newline_on_any_platform(self):
        # Written through the byte stream so Windows cannot translate it.
        path = self.write("doc.json", '{"b":2,"a":1}')
        result = self.run_cli("hash", path, "--canonical")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(b'{"a":1,"b":2}', result.stdout)

    def test_a_document_outside_the_domain_exits_one(self):
        path = self.write("doc.json", '{"ratio":0.5}')
        result = self.run_cli("hash", path)
        self.assertEqual(1, result.returncode)
        self.assertIn(b"/ratio", result.stderr)

    def test_a_missing_file_exits_two(self):
        result = self.run_cli("hash", "no-such-file.json")
        self.assertEqual(2, result.returncode)

    def test_diagnostics_are_ascii(self):
        # Non-ASCII renders as '?' on the Windows console, which turns a
        # diagnostic pasted into an issue into a false trail.
        path = self.write("doc.json", '{"ratio":0.5}')
        result = self.run_cli("hash", path)
        result.stderr.decode("ascii")


if __name__ == "__main__":
    unittest.main()
