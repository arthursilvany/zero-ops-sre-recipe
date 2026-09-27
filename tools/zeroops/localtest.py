"""`zeroops test --local`: the offline suite, run so that offline is proved.

The command exists because US-1's independent test is performed by a person on
a machine with no Azure login, and telling that person to reconstruct a
`python -m unittest discover` incantation with the right `-t` and the right
`PYTHONPATH` is how the test stops being performed.

Three properties are enforced rather than claimed, because each of them is the
kind of thing a suite can stop having without anyone noticing:

Credential-free (NFR-12). The child process runs with every credential-shaped
variable removed from its environment. A test that quietly depends on an
ambient token passes on the author's machine and fails on a reviewer's, and the
failure arrives far from its cause. Scrubbing makes that failure happen here.

Offline (NFR-12, US-1 AC1). The child forbids outbound sockets before it
imports anything of ours. The original acceptance criterion proposed asserting
this by blocking egress at the network layer, which requires privileges the
person running the independent test may not have. Refusing the connect call is
available everywhere and fails with a message that says what was attempted.

Non-vacuous. A discovery that finds nothing satisfies every assertion it does
not run. Zero tests is a failure here, not a pass with an empty report: a
suite that silently stopped being discovered is indistinguishable from a suite
that passed, and only one of those is worth reporting.
"""

import os
import re
import subprocess
import sys
import unittest

REPO_MARKERS = (
    os.path.join("contracts", "core-paths.json"),
    "tests",
    "tools",
)

CHILD_FLAG = "ZEROOPS_LOCAL_TEST_CHILD"

# Set by the child before it runs anything. A module global rather than only
# the environment variable, because the environment can be edited by the very
# suite the child is running, and a re-entrancy guard that the guarded code can
# switch off is not a guard. Both signals are checked: the variable crosses the
# process boundary, the global survives anything done to the variable.
IN_CHILD = False


class LocalTestError(Exception):
    """Raised when the command cannot run, as opposed to when tests fail."""


# A total registry, in the pattern the rest of this codebase uses: every
# variable the command scrubs appears here exactly once with the reason it is
# scrubbed. A name removed silently is a name nobody can argue with later, and
# a name that ought to be here but is not looks identical to a name that was
# considered and rejected.
CREDENTIAL_ENVIRONMENT = (
    ("AZURE_", "prefix", "Azure SDK and CLI credential material, including "
                         "AZURE_CLIENT_SECRET and AZURE_FEDERATED_TOKEN_FILE."),
    ("ARM_", "prefix", "The variable family Terraform and several CI templates "
                       "use for service-principal credentials."),
    ("MSI_", "prefix", "Managed-identity endpoint and secret, which would let a "
                       "test acquire a token without any variable named secret."),
    ("IDENTITY_", "prefix", "The App Service and Container Apps spelling of the "
                            "same managed-identity endpoint."),
    ("AZURE_CLIENT_ID", "exact", "Named explicitly as well as by prefix, so the "
                                 "registry reads as a list of what is removed."),
    ("GITHUB_TOKEN", "exact", "Present in every GitHub Actions job. A test that "
                              "reaches the API is not a local test."),
    ("GH_TOKEN", "exact", "The CLI's spelling of the same token."),
    ("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "exact",
     "The OIDC exchange token. It is short-lived, which makes a dependency on "
     "it pass today and fail tomorrow for reasons nobody connects to this."),
    ("ACTIONS_ID_TOKEN_REQUEST_URL", "exact", "The endpoint the token is spent at."),
)

EXTRA_SCRUB_PATTERN = re.compile(
    r"(SECRET|PASSWORD|TOKEN|CREDENTIAL|APIKEY|API_KEY)", re.IGNORECASE
)


def scrub_environment(environ):
    """Return a copy of environ with credential-shaped variables removed.

    The pattern sweep is deliberately broader than the registry. The registry
    names what is known to matter; the sweep catches what a future CI template
    introduces. Removing a harmless variable costs nothing, and the asymmetry
    runs the other way.
    """
    prefixes = tuple(n for n, kind, _ in CREDENTIAL_ENVIRONMENT if kind == "prefix")
    exact = {n for n, kind, _ in CREDENTIAL_ENVIRONMENT if kind == "exact"}
    kept = {}
    for name, value in environ.items():
        if name in exact or name.startswith(prefixes):
            continue
        if EXTRA_SCRUB_PATTERN.search(name):
            continue
        kept[name] = value
    return kept


def scrubbed_names(environ):
    """What scrubbing removed, so the command can say so rather than imply it."""
    return sorted(set(environ) - set(scrub_environment(environ)))


def forbid_network():
    """Make an outbound connection raise instead of succeeding.

    Patched at the socket layer rather than higher up, because anything higher
    is one library away from being bypassed. Everything in the standard library
    that opens an outbound connection, `socket.create_connection` and `urllib`
    included, reaches `connect` or `connect_ex`, so those two are the whole
    surface. An additional override on `create_connection` was written first
    and then removed: it could not be reached without `connect` having already
    refused, which made it a branch no test could tell apart from its absence.

    The scope is honest and limited: this process and nothing it shells out to.
    Git is invoked by the core declaration checks and is unaffected, which is
    stated in docs/commands.md rather than left for a reader to discover.
    """
    import socket

    def refuse(self, address, *args, **kwargs):
        raise OSError(
            "outbound network refused by 'zeroops test --local'. The offline "
            "suite reaches nothing; a test that needs a service belongs behind "
            "a different command (NFR-12)."
        )

    socket.socket.connect = refuse
    socket.socket.connect_ex = refuse


def repository_root(start=None):
    """Walk up until a checkout is recognisable, or refuse.

    Refusing loudly matters more than it looks. The shims put tools/ on the
    path from wherever they sit, so the command is reachable from a directory
    that holds no tests, and a runner that found no tests there would report
    success having established nothing.
    """
    here = os.path.abspath(start or os.getcwd())
    while True:
        if all(os.path.exists(os.path.join(here, m)) for m in REPO_MARKERS):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            raise LocalTestError(
                "no repository checkout found at or above the current "
                "directory. 'zeroops test --local' runs this repository's "
                "suite, so it has to be run from inside a clone. Looked for: "
                + ", ".join(REPO_MARKERS)
            )
        here = parent


def count_tests(suite):
    total = 0
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            total += count_tests(item)
        else:
            total += 1
    return total


def run_in_process(root, pattern="test_*.py", stream=None):
    """Discover and run. Returns (exit code, tests run).

    Zero discovered is a non-zero exit. So is a discovery error: unittest
    represents an unimportable test module as a synthetic failing test, which
    keeps it from vanishing, but only if the count is not the sole thing
    checked.
    """
    stream = stream or sys.stderr
    loader = unittest.TestLoader()
    try:
        suite = loader.discover(
            start_dir=os.path.join(root, "tests"), pattern=pattern, top_level_dir=root
        )
    except ImportError as exc:
        # Discovery that cannot start is the same failure as discovery that
        # finds nothing, and it arrives as a traceback rather than a result, so
        # it would otherwise be the one way to get an exit code that says
        # neither pass nor fail.
        stream.write(
            "error: test discovery could not start under tests/: %s\n" % exc
        )
        return 2, 0
    discovered = count_tests(suite)
    if discovered == 0:
        stream.write(
            "error: discovery found no tests under tests/. A suite that is not "
            "discovered is indistinguishable from a suite that passed, so this "
            "is a failure rather than an empty report.\n"
        )
        return 2, 0

    runner = unittest.TextTestRunner(stream=stream, verbosity=1)
    result = runner.run(suite)
    return (0 if result.wasSuccessful() else 1), discovered


def _child(argv):
    """The scrubbed, network-refusing side. Entered only via run_local."""
    global IN_CHILD
    IN_CHILD = True
    forbid_network()
    root = argv[0]
    pattern = argv[1] if len(argv) > 1 else "test_*.py"
    code, _ = run_in_process(root, pattern)
    return code


def already_running(environ=None):
    """Whether this process is, or is inside, a local test run.

    A pure function over a mapping so it can be exercised without touching the
    real environment. A test that proved this guard by editing os.environ would
    be editing the thing the guard reads, in a process that may itself be the
    child, which is how the guard came to be needed in the first place.
    """
    if IN_CHILD:
        return True
    environ = os.environ if environ is None else environ
    return bool(environ.get(CHILD_FLAG))


def run_local(pattern="test_*.py", start=None, out=None, err=None):
    """Spawn the child with a scrubbed environment and report what was removed.

    A subprocess rather than an in-process run, because the environment has to
    be scrubbed for the whole run and a process cannot un-inherit its own.
    """
    out = out or sys.stdout
    err = err or sys.stderr
    if already_running():
        # The child runs the whole suite, and the suite exercises this command.
        # Without this, a nested invocation spawns another child that spawns
        # another, and the symptom is a machine that stops responding rather
        # than a message. It happened once during development, at four hundred
        # processes, which is why the guard does not rely on a single signal.
        raise LocalTestError(
            "'zeroops test --local' is already running. It cannot run inside "
            "its own test process: the child runs the suite, and the suite "
            "exercises this command."
        )
    root = repository_root(start)

    environ = scrub_environment(os.environ)
    removed = scrubbed_names(os.environ)
    tools = os.path.join(root, "tools")
    existing = environ.get("PYTHONPATH")
    environ["PYTHONPATH"] = (
        tools + os.pathsep + existing if existing else tools
    )
    environ[CHILD_FLAG] = "1"

    out.write("Running the offline suite from %s\n" % root)
    out.write(
        "Credential-shaped variables removed from the child environment: %s\n"
        % (", ".join(removed) if removed else "none present")
    )
    out.write("Outbound network refused inside the test process.\n")
    out.flush()

    completed = subprocess.run(
        [sys.executable, "-m", "zeroops.localtest", root, pattern],
        cwd=root,
        env=environ,
    )
    if completed.returncode == 0:
        out.write("Offline suite passed with no credentials and no network.\n")
        out.flush()
    else:
        err.write(
            "Offline suite failed. The run had no credentials and no network, "
            "so a failure here is a failure of the code and not of the "
            "environment.\n"
        )
    return completed.returncode


if __name__ == "__main__":
    sys.exit(_child(sys.argv[1:]))
